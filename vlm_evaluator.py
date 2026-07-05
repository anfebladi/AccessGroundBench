"""
vlm_evaluator.py
----------------
Phase 2 & 3: Targeted VLM Grounding Evaluation & Hit-Test Scoring.

Runs fully offline against the saved dataset (no emulator required).
For each screen x profile x target text element:
  1. Dynamically harvests evaluation targets from the baseline label JSON
  2. Checks if the target element is still visible in the modified profile
  3. Sends the image + grounding prompt through LiteLLM
  4. Parses the predicted (x, y) coordinates via regex
  5. Hit-tests against the ground-truth bounding box
  6. Logs every result to dataset/evaluation_results.csv

Usage:
  python vlm_evaluator.py                          # run full evaluation
  python vlm_evaluator.py --screens settings_main   # evaluate specific screens
  python vlm_evaluator.py --model openai/gpt-4o-mini # override model
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

from vlm_provider import call_vlm

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

MODEL_ENV_VAR: str = "VLM_MODEL"
PACE_ENV_VAR: str = "VLM_PACE_SECONDS"

# Regex to extract (x, y) integer coordinates from model response
COORD_REGEX = re.compile(r"(\d+)\s*,\s*(\d+)")

# Prompt template for VLM grounding
PROMPT_TEMPLATE = (
    "You are an autonomous mobile agent navigating an Android user interface. "
    "Look closely at this image. Provide the exact central (x, y) pixel "
    "coordinates needed to click on the text element: '{target_text}'. "
    "Return your response strictly in the bracket format: [x, y]"
)

# Accessibility profiles (must match layout_modifier.py keys)
ALL_PROFILES = [
    "baseline",
    "elder_text_heavy",
    "elder_zoom_heavy",
    "elder_combo_max",
    "elder_combo_rtl",
]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def resolve_model(cli_model: str | None) -> str:
    """Resolve model precedence: CLI override, then VLM_MODEL env."""
    if cli_model:
        return cli_model

    env_model = os.environ.get(MODEL_ENV_VAR, "").strip()
    if env_model:
        return env_model

    print(f"[ERROR] {MODEL_ENV_VAR} is not set.")
    print("")
    print("  To fix this, set a LiteLLM model string in .env, for example:")
    print("  VLM_MODEL=openai/gpt-4o-mini")
    print("")
    print("  Or pass a temporary override:")
    print("  python vlm_evaluator.py --model openai/gpt-4o-mini")
    raise SystemExit(1)


def resolve_pace_seconds(cli_pace_seconds: str | None) -> float:
    """Resolve optional per-call pacing: CLI override, env, then 0 seconds."""
    raw_value = cli_pace_seconds
    source = "--pace-seconds"
    if raw_value is None:
        raw_value = os.environ.get(PACE_ENV_VAR, "").strip()
        source = PACE_ENV_VAR

    if raw_value in (None, ""):
        return 0.0

    try:
        pace_seconds = float(raw_value)
    except ValueError:
        print(f"[ERROR] {source} must be a number of seconds, got: {raw_value}")
        raise SystemExit(1)

    if pace_seconds < 0:
        print(f"[ERROR] {source} must be >= 0, got: {raw_value}")
        raise SystemExit(1)

    return pace_seconds


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
# Main Evaluation Loop
# ---------------------------------------------------------------------------

def evaluate_screen(
    model: str,
    screen_name: str,
    pace_seconds: float,
) -> int:
    """
    Evaluate all profiles for a single screen.
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

        print(f"\n  -- {screen_name} / {profile_name} "
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
                    "profile": profile_name,
                    "raw_response": "[OFF-SCREEN]",
                    "x_pred": -1, "y_pred": -1,
                    "x_min": "", "y_min": "", "x_max": "", "y_max": "",
                    "score": 0,
                }
                append_result(row)
                count += 1
                print(f"    [OFF-SCREEN] '{target_text}' -> score=0")
                continue

            # Call the VLM
            try:
                prompt = PROMPT_TEMPLATE.format(target_text=target_text)
                raw_response = call_vlm(model, image_path, prompt)
            except Exception as exc:
                print(f"    [API-ERROR] '{target_text}': {exc}")
                print("    [ABORT] Provider/API error; no CSV row written for this target.")
                raise SystemExit(1) from exc

            # Parse coordinates
            x_pred, y_pred = parse_coordinates(raw_response)

            # Hit-test
            score = hit_test(x_pred, y_pred, box)

            # Log
            row = {
                "screen": screen_name,
                "target_text": target_text,
                "profile": profile_name,
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

            if pace_seconds > 0:
                print(f"    [PACE] Sleeping {pace_seconds}s...")
                time.sleep(pace_seconds)

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
        "--model", default=None,
        help=(
            "LiteLLM model string to use. Overrides VLM_MODEL. "
            "Required if VLM_MODEL is not set."
        ),
    )
    parser.add_argument(
        "--pace-seconds", default=None,
        help=(
            "Optional delay after successful API calls. Overrides "
            "VLM_PACE_SECONDS. Default: 0"
        ),
    )
    args = parser.parse_args()
    model = resolve_model(args.model)
    pace_seconds = resolve_pace_seconds(args.pace_seconds)

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
    print(f"  Model   : {model}")
    print(f"  Pace    : {pace_seconds}s")
    print(f"  Screens : {', '.join(screens)}")
    print(f"  CSV     : {RESULTS_CSV}")
    print("=" * 60)

    init_csv()

    total_rows = 0
    for screen_name in screens:
        print(f"\n{'=' * 60}")
        print(f"  Evaluating screen: {screen_name}")
        print(f"{'=' * 60}")
        rows = evaluate_screen(model, screen_name, pace_seconds)
        total_rows += rows

    print("\n" + "=" * 60)
    print(f"  Evaluation complete!")
    print(f"  Total rows logged: {total_rows}")
    print(f"  Results CSV: {RESULTS_CSV}")
    print("=" * 60)


if __name__ == "__main__":
    main()
