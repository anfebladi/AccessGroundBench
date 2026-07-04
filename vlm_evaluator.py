"""
vlm_evaluator.py
----------------
Phase 2 & 3: Targeted VLM Grounding Evaluation & Hit-Test Scoring.

Runs fully offline against the saved dataset (no emulator required).
For each screen x profile x target text element:
  1. Dynamically harvests evaluation targets from the baseline label JSON
  2. Checks if the target element is still visible in the modified profile
  3. Sends the image + grounding prompt to Gemini API
  4. Parses the predicted (x, y) coordinates via regex
  5. Hit-tests against the ground-truth bounding box
  6. Logs every result to dataset/evaluation_results.csv

Experimental conditions (per screen x target):
  A = baseline          : normal layout, image only
  B = <elder profile>   : distorted layout, image only
  C = <elder profile>_tree : distorted layout, image + accessibility tree
The tree-augmented arm (C) is only produced when --with-tree is passed; it
logs rows under the profile name "<profile>_tree" for later B-vs-C analysis.

Usage:
  python vlm_evaluator.py                          # run full evaluation
  python vlm_evaluator.py --screens settings_main   # evaluate specific screens
  python vlm_evaluator.py --model gemini-2.5-pro     # override model
  python vlm_evaluator.py --with-tree               # also run condition C
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    from google import genai
except ImportError:
    print("[ERROR] google-genai package not installed.")
    print("        Run: pip install google-genai")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()  # loads .env from the project root into os.environ
except ImportError:
    pass  # python-dotenv optional; fall back to system env vars

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent
DATASET_DIR = PROJECT_ROOT / "dataset"
IMAGES_DIR = DATASET_DIR / "images"
LABELS_DIR = DATASET_DIR / "labels"
RESULTS_CSV = DATASET_DIR / "evaluation_results.csv"

# ---------------------------------------------------------------------------
# Evaluation constants
# ---------------------------------------------------------------------------
API_PACE_SECONDS: float = 12.0  # 5 calls/minute rate cap
DEFAULT_MODEL: str = "gemini-2.5-flash"

# Regex to extract (x, y) integer coordinates from model response
COORD_REGEX = re.compile(r"(\d+)\s*,\s*(\d+)")

# Prompt template for VLM grounding (image only -- conditions A and B)
PROMPT_TEMPLATE = (
    "You are an autonomous mobile agent navigating an Android user interface. "
    "Look closely at this image. Provide the exact central (x, y) pixel "
    "coordinates needed to click on the text element: '{target_text}'. "
    "Return your response strictly in the bracket format: [x, y]"
)

# Prompt template for the tree-augmented condition C (image + accessibility tree)
PROMPT_TEMPLATE_TREE = (
    "You are an autonomous mobile agent navigating an Android user interface. "
    "Look closely at this image. You are also given the screen's accessibility "
    "tree, listing on-screen elements with their pixel bounds in the format "
    "[x1,y1][x2,y2]:\n{tree_text}\n"
    "Using both the image and the accessibility tree, provide the exact central "
    "(x, y) pixel coordinates needed to click on the text element: '{target_text}'. "
    "Return your response strictly in the bracket format: [x, y]"
)

# Suffix used to tag condition-C rows in the results CSV (profile + suffix).
TREE_SUFFIX = "_tree"

# Accessibility profiles (must match layout_modifier.py keys)
ALL_PROFILES = [
    "baseline",
    "elder_text_heavy",
    "elder_zoom_heavy",
    "elder_combo_max",
    "elder_combo_rtl",
]


# ---------------------------------------------------------------------------
# Target Harvesting
# ---------------------------------------------------------------------------

def harvest_targets(screen_name: str) -> list[dict]:
    """
    Dynamic Target Harvesting: read the baseline label JSON for a screen
    and extract every element with a non-empty text property.

    Returns a list of dicts with 'text' and 'box' keys.
    """
    baseline_path = LABELS_DIR / f"{screen_name}_baseline.json"
    if not baseline_path.is_file():
        print(f"[WARN] Baseline labels not found: {baseline_path}")
        return []

    with open(baseline_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    targets = []
    for rec in records:
        text = rec.get("text")
        if text and text.strip():
            targets.append({"text": text.strip(), "box": rec["box"]})

    print(f"  [HARVEST] {len(targets)} text targets from {baseline_path.name}")
    return targets


def find_element_in_profile(profile_labels: list[dict], target_text: str) -> list[int] | None:
    """
    Look up a target text string in a profile's label JSON.
    Returns the bounding box [x_min, y_min, x_max, y_max] if found, else None.

    If the element is missing, it means the layout modification pushed it
    off-screen.
    """
    for rec in profile_labels:
        if rec.get("text") and rec["text"].strip() == target_text:
            return rec["box"]
    return None


def build_tree_text(profile_labels: list[dict]) -> str:
    """
    Render a profile's label records into a compact accessibility-tree string
    for the condition-C (image + tree) prompt.

    Each line is:  - "<label>" [x1,y1][x2,y2]
    where <label> falls back through text -> content_desc -> resource_id -> class.
    """
    lines = []
    for rec in profile_labels:
        box = rec.get("box")
        if not box:
            continue
        x1, y1, x2, y2 = box
        label = (
            rec.get("text")
            or rec.get("content_desc")
            or rec.get("resource_id")
            or rec.get("class")
            or "?"
        )
        lines.append(f'- "{label}" [{x1},{y1}][{x2},{y2}]')
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Coordinate Parsing & Hit-Testing
# ---------------------------------------------------------------------------

def parse_coordinates(response_text: str) -> tuple[int, int]:
    """
    Extract (x, y) coordinates from the model's text response using
    the strict regex pattern. On failure, returns (-1, -1).
    """
    match = COORD_REGEX.search(response_text)
    if match:
        return int(match.group(1)), int(match.group(2))
    return -1, -1


def hit_test(x_pred: int, y_pred: int, box: list[int]) -> int:
    """
    Mathematical bounding box hit-test.

    Score = 1 if x_min <= x_pred <= x_max AND y_min <= y_pred <= y_max
    Score = 0 otherwise
    """
    x_min, y_min, x_max, y_max = box
    if x_min <= x_pred <= x_max and y_min <= y_pred <= y_max:
        return 1
    return 0


# ---------------------------------------------------------------------------
# CSV Logging
# ---------------------------------------------------------------------------

CSV_COLUMNS = [
    "screen", "target_text", "profile",
    "raw_response", "x_pred", "y_pred",
    "x_min", "y_min", "x_max", "y_max",
    "score",
]


def init_csv() -> None:
    """Create the CSV file with headers if it doesn't exist."""
    if not RESULTS_CSV.is_file():
        RESULTS_CSV.parent.mkdir(parents=True, exist_ok=True)
        with open(RESULTS_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)
        print(f"  [CSV] Created {RESULTS_CSV}")


def append_result(row: dict) -> None:
    """Append a single evaluation result row to the CSV."""
    with open(RESULTS_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([row.get(col, "") for col in CSV_COLUMNS])


# ---------------------------------------------------------------------------
# VLM API Interface
# ---------------------------------------------------------------------------

def call_vlm(
    client: genai.Client,
    model: str,
    image_path: Path,
    target_text: str,
    tree_text: str | None = None,
) -> str:
    """
    Send an image + grounding prompt to the Gemini API.
    When tree_text is provided, uses the condition-C prompt that also supplies
    the accessibility tree. Returns the raw text response from the model.
    """
    if tree_text is None:
        prompt = PROMPT_TEMPLATE.format(target_text=target_text)
    else:
        prompt = PROMPT_TEMPLATE_TREE.format(target_text=target_text, tree_text=tree_text)

    # Upload the image file
    uploaded_file = client.files.upload(file=image_path)

    response = client.models.generate_content(
        model=model,
        contents=[uploaded_file, prompt],
    )

    return response.text if response.text else ""


# ---------------------------------------------------------------------------
# Main Evaluation Loop
# ---------------------------------------------------------------------------

def run_pass(
    client: genai.Client,
    model: str,
    screen_name: str,
    logged_profile: str,
    targets: list[dict],
    profile_labels: list[dict],
    image_path: Path,
    tree_text: str | None = None,
) -> int:
    """
    Score every target for a single condition pass and log the rows under
    `logged_profile`. Ground truth (box / off-screen) always comes from
    `profile_labels`; `tree_text` only augments the prompt (condition C).

    Returns the number of rows logged.
    """
    count = 0
    print(f"\n  -- {screen_name} / {logged_profile} "
          f"({len(targets)} targets) --")

    for target in targets:
        target_text = target["text"]

        # Check if the element is still visible in this profile
        box = find_element_in_profile(profile_labels, target_text)

        if box is None:
            # Element pushed off-screen -> immediate failure
            row = {
                "screen": screen_name,
                "target_text": target_text,
                "profile": logged_profile,
                "raw_response": "[OFF-SCREEN]",
                "x_pred": -1, "y_pred": -1,
                "x_min": "", "y_min": "", "x_max": "", "y_max": "",
                "score": 0,
            }
            append_result(row)
            count += 1
            print(f"    [OFF-SCREEN] '{target_text}' -> score=0")
            continue

        # Call the VLM (tree_text=None -> image only; else image + tree)
        try:
            raw_response = call_vlm(client, model, image_path, target_text, tree_text)
        except Exception as exc:
            print(f"    [API-ERROR] '{target_text}': {exc}")
            raw_response = ""

        # Parse coordinates
        x_pred, y_pred = parse_coordinates(raw_response)

        # Hit-test
        score = hit_test(x_pred, y_pred, box)

        # Log
        row = {
            "screen": screen_name,
            "target_text": target_text,
            "profile": logged_profile,
            "raw_response": raw_response.replace("\n", " ").strip(),
            "x_pred": x_pred, "y_pred": y_pred,
            "x_min": box[0], "y_min": box[1],
            "x_max": box[2], "y_max": box[3],
            "score": score,
        }
        append_result(row)
        count += 1

        status = "HIT" if score == 1 else "MISS"
        print(f"    [{status}] '{target_text}' -> pred=({x_pred},{y_pred}) "
              f"box={box}")

        # Rate limiting: 12-second blocking delay
        print(f"    [PACE] Sleeping {API_PACE_SECONDS}s...")
        time.sleep(API_PACE_SECONDS)

    return count


def evaluate_screen(
    client: genai.Client,
    model: str,
    screen_name: str,
    with_tree: bool = False,
) -> int:
    """
    Evaluate all profiles for a single screen.

    Always runs the image-only pass (conditions A/B). When with_tree is set,
    each non-baseline profile also gets a tree-augmented pass (condition C),
    logged under "<profile>_tree".

    Returns the total number of evaluation rows generated.
    """
    # Harvest targets from baseline
    targets = harvest_targets(screen_name)
    if not targets:
        print(f"  [SKIP] No targets for screen: {screen_name}")
        return 0

    count = 0

    for profile_name in ALL_PROFILES:
        image_path = IMAGES_DIR / f"{screen_name}_{profile_name}.png"
        label_path = LABELS_DIR / f"{screen_name}_{profile_name}.json"

        if not image_path.is_file():
            print(f"  [SKIP] Missing image: {image_path.name}")
            continue
        if not label_path.is_file():
            print(f"  [SKIP] Missing labels: {label_path.name}")
            continue

        # Load the profile's label data
        with open(label_path, "r", encoding="utf-8") as f:
            profile_labels = json.load(f)

        # Condition A/B: image only
        count += run_pass(
            client, model, screen_name, profile_name,
            targets, profile_labels, image_path, tree_text=None,
        )

        # Condition C: image + accessibility tree (baseline has no tree arm)
        if with_tree and profile_name != "baseline":
            tree_text = build_tree_text(profile_labels)
            count += run_pass(
                client, model, screen_name, profile_name + TREE_SUFFIX,
                targets, profile_labels, image_path, tree_text=tree_text,
            )

    return count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AccessGroundBench -- VLM Grounding Evaluator"
    )
    parser.add_argument(
        "--screens", nargs="+", default=None,
        help="Override the screen list (e.g., --screens settings_main dialer)",
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"Gemini model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--with-tree", action="store_true",
        help="Also run condition C (image + accessibility tree) per elder profile",
    )
    args = parser.parse_args()

    # Resolve API key — checks .env first (via dotenv), then system env vars
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or api_key == "your-api-key-here":
        print("[ERROR] GOOGLE_API_KEY is not set.")
        print("")
        print("  To fix this:")
        print("  1. Get a free key at: https://aistudio.google.com/apikey")
        print("  2. Open the .env file in the project root")
        print("  3. Replace 'your-api-key-here' with your actual key")
        print("  4. Save the file and re-run this script")
        sys.exit(1)

    # Initialize Gemini client
    client = genai.Client(api_key=api_key)

    # Auto-discover screens from baseline label files if none specified
    if args.screens:
        screens = args.screens
    else:
        screens = []
        if LABELS_DIR.is_dir():
            for f in sorted(LABELS_DIR.glob("*_baseline.json")):
                screen_name = f.stem.replace("_baseline", "")
                screens.append(screen_name)

    if not screens:
        print("[ERROR] No screens found. Run orchestrator.py first to collect data.")
        sys.exit(1)

    print("=" * 60)
    print("  AccessGroundBench -- VLM Grounding Evaluator")
    print(f"  Model   : {args.model}")
    print(f"  Screens : {', '.join(screens)}")
    print(f"  Tree    : {'ON (condition C enabled)' if args.with_tree else 'off'}")
    print(f"  CSV     : {RESULTS_CSV}")
    print("=" * 60)

    init_csv()

    total_rows = 0
    for screen_name in screens:
        print(f"\n{'=' * 60}")
        print(f"  Evaluating screen: {screen_name}")
        print(f"{'=' * 60}")
        rows = evaluate_screen(client, args.model, screen_name, with_tree=args.with_tree)
        total_rows += rows

    print("\n" + "=" * 60)
    print(f"  Evaluation complete!")
    print(f"  Total rows logged: {total_rows}")
    print(f"  Results CSV: {RESULTS_CSV}")
    print("=" * 60)


if __name__ == "__main__":
    main()
