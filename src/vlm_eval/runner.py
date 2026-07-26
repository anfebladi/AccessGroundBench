"""Evaluation loop for VLM grounding benchmark runs."""

import json
import struct
import time
from pathlib import Path

from .provider import call_vlm

from .config import ALL_PROFILES, IMAGES_DIR, LABELS_DIR
from .results import append_result
from .scoring import hit_test, parse_coordinates
from .targets import find_element_in_profile, harvest_targets

PROMPT_TEMPLATE = (
    "You are an autonomous mobile agent navigating an Android user interface. "
    "Look closely at this image. This image is {img_width} x {img_height} pixels. "
    "Provide the exact central pixel (x, y) coordinates "
    "needed to click on the text element: '{target_text}'."
)

PROMPT_TEMPLATE_WITH_TREE = (
    "You are an autonomous mobile agent navigating an Android user interface. "
    "Look closely at this image. This image is {img_width} x {img_height} pixels. "
    "You are also given a partial accessibility tree listing some on-screen "
    "elements with their pixel bounds in the format [x1,y1][x2,y2]:\n"
    "{tree_text}\n"
    "The target element may not appear in this tree; use the surrounding "
    "elements' positions as spatial reference and the image to locate it. "
    "Provide the exact central (x, y) pixel coordinates needed to click on the "
    "text element: '{target_text}'."
)


def build_tree_text(
    profile_labels: list[dict],
    exclude_text: str | None = None,
) -> str:
    """Render a profile's label records into a compact accessibility-tree string.

    Each line represents one UI element with its best available label and
    pixel bounding box. Falls back through: text -> content_desc ->
    resource_id -> class.

    When exclude_text is provided, any element whose text matches it is
    withheld from the tree. This prevents the tree from leaking the target's
    exact pixel bounds (which would reduce grounding to a parsing task): the
    model still gets the surrounding elements' positions as spatial context,
    but must locate the target itself from the image.
    """
    lines = []
    for rec in profile_labels:
        box = rec.get("box")
        if not box:
            continue
        text = rec.get("text")
        if (
            exclude_text is not None
            and text
            and text.strip() == exclude_text
        ):
            continue
        x1, y1, x2, y2 = box
        label = (
            text
            or rec.get("content_desc")
            or rec.get("resource_id")
            or rec.get("class")
            or "?"
        )
        lines.append(f'- "{label}" [{x1},{y1}][{x2},{y2}]')
    return "\n".join(lines)

def get_png_dimensions(image_path: Path) -> tuple[int, int]:
    """Extract width and height from a PNG file without external libraries."""
    with open(image_path, "rb") as f:
        f.read(16)
        width, height = struct.unpack(">II", f.read(8))
        return width, height


def evaluate_screen(
    model: str,
    screen_name: str,
    pace_seconds: float,
    results_csv: Path,
    images_dir: Path = IMAGES_DIR,
    labels_dir: Path = LABELS_DIR,
    profiles: list[str] | None = None,
    use_a11y_tree: bool = False,
) -> int:
    """
    Evaluate all profiles for a single screen.

    When use_a11y_tree is True, injects the accessibility tree into the
    prompt alongside the screenshot. When False, runs vision-only (unchanged).

    Returns the total number of evaluation rows generated.
    """
    targets = harvest_targets(screen_name, labels_dir)
    if not targets:
        print(f"  [SKIP] No targets for screen: {screen_name}")
        return 0

    count = 0
    profiles_to_run = profiles if profiles is not None else ALL_PROFILES

    for profile_name in profiles_to_run:
        image_path = images_dir / f"{screen_name}_{profile_name}.png"
        label_path = labels_dir / f"{screen_name}_{profile_name}.json"

        if not image_path.is_file():
            print(f"  [SKIP] Missing image: {image_path.name}")
            continue
        if not label_path.is_file():
            print(f"  [SKIP] Missing labels: {label_path.name}")
            continue

        try:
            img_width, img_height = get_png_dimensions(image_path)
        except Exception as e:
            print(f"  [SKIP] Failed to read image dimensions for {image_path.name}: {e}")
            continue

        with open(label_path, "r", encoding="utf-8") as f:
            profile_labels = json.load(f)

        mode_tag = " +tree" if use_a11y_tree else ""
        print(f"\n  -- {screen_name} / {profile_name}{mode_tag} "
              f"({len(targets)} targets) --")

        for target in targets:
            target_text = target["text"]
            baseline_box = target["baseline_box"]
            box = find_element_in_profile(profile_labels, target_text)

            if box is None:
                row = {
                    "screen": screen_name,
                    "target_text": target_text,
                    "profile": profile_name,
                    "raw_response": "[OFF-SCREEN]",
                    "x_pred": -1, "y_pred": -1,
                    "x_min": "", "y_min": "", "x_max": "", "y_max": "",
                    "score": 0,
                }
                append_result(results_csv, row)
                count += 1
                print(f"    [OFF-SCREEN] '{target_text}' -> score=0")
                continue

            try:
                if use_a11y_tree:
                    # Withhold the target's own row so the tree provides
                    # spatial context without leaking the answer's bounds.
                    tree_text = build_tree_text(
                        profile_labels, exclude_text=target_text
                    )
                    prompt = PROMPT_TEMPLATE_WITH_TREE.format(
                        img_width=img_width,
                        img_height=img_height,
                        tree_text=tree_text,
                        target_text=target_text,
                    )
                else:
                    prompt = PROMPT_TEMPLATE.format(
                        img_width=img_width,
                        img_height=img_height,
                        target_text=target_text,
                    )
                raw_response = call_vlm(
                    model,
                    image_path,
                    prompt,
                    target_text=target_text,
                )
            except Exception as exc:
                print(f"    [API-ERROR] '{target_text}': {exc}")
                print("    [SKIP] Provider/API error; skipping target and moving to next.")
                row = {
                    "screen": screen_name,
                    "target_text": target_text,
                    "profile": profile_name,
                    "raw_response": f"[API-ERROR: {type(exc).__name__}]",
                    "x_pred": -1, "y_pred": -1,
                    "x_min": box[0], "y_min": box[1],
                    "x_max": box[2], "y_max": box[3],
                    "score": 0,
                }
                append_result(results_csv, row)
                count += 1
                continue

            x_coord, y_coord = parse_coordinates(raw_response)

            if (
                x_coord < 0
                or y_coord < 0
                or x_coord > img_width
                or y_coord > img_height
            ):
                x_pred, y_pred = -1, -1
                score = 0
            else:
                x_pred, y_pred = int(x_coord), int(y_coord)
                score = hit_test(x_pred, y_pred, box, baseline_box)

            row = {
                "screen": screen_name,
                "target_text": target_text,
                "profile": profile_name,
                "raw_response": raw_response.replace("\r", " ").replace("\n", " ").strip(),
                "x_pred": x_pred, "y_pred": y_pred,
                "x_min": box[0], "y_min": box[1],
                "x_max": box[2], "y_max": box[3],
                "score": score,
            }
            append_result(results_csv, row)
            count += 1

            status = "HIT" if score == 1 else "MISS"
            safe_text = target_text.encode('ascii', 'replace').decode('ascii')
            print(f"    [{status}] '{safe_text}' -> pred=({x_pred},{y_pred}) "
                  f"box={box}")

            if pace_seconds > 0:
                print(f"    [PACE] Sleeping {pace_seconds}s...")
                time.sleep(pace_seconds)

    return count
