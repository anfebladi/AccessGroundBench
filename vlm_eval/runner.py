"""Evaluation loop for VLM grounding benchmark runs."""

import json
import struct
import time
from collections import Counter
from pathlib import Path

from vlm_provider import call_vlm

from .config import ALL_PROFILES, IMAGES_DIR, LABELS_DIR
from .results import (
    STATUS_API_ERROR,
    STATUS_CO_PRESENT,
    STATUS_OFF_SCREEN,
    append_result,
)
from .scoring import PARSE_FAILED, hit_test, parse_coordinates_detailed
from .targets import find_element_in_profile, harvest_targets

PROMPT_TEMPLATE = (
    "You are an autonomous mobile agent navigating an Android user interface. "
    "Look closely at this image. This image is {img_width} x {img_height} pixels. "
    "Provide the exact central pixel (x, y) coordinates "
    "needed to click on the text element: '{target_text}'. "
    "Return your response strictly in the bracket format: [x, y]"
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
    "text element: '{target_text}'. "
    "Return your response strictly in the bracket format: [x, y]"
)


def build_tree_text(
    profile_labels: list[dict],
    exclude_text: str | None = None,
) -> str:
    """Render a profile's label records into a compact accessibility-tree string.

    Each line represents one UI element with its best available label and
    pixel bounding box. Falls back through: text -> content_desc ->
    resource_id -> class.

    When exclude_text is provided, any element whose RENDERED LABEL matches it
    is withheld from the tree. This prevents the tree from leaking the
    target's exact pixel bounds (which would reduce grounding to a parsing
    task): the model still gets the surrounding elements' positions as
    spatial context, but must locate the target itself from the image.

    The exclusion must be checked against the same fallback chain used to
    build the label, not against `text` alone: a node with empty `text` but
    `content_desc == exclude_text` still renders the target's name, so
    checking `text` alone let it through. Measured on the archived dataset,
    this leaked 22 of 168 targets (13.1%) -- typically a parent tab container
    whose bounds enclose the ground-truth box, so the model could score a hit
    by reading the tree instead of looking at the image.
    """
    lines = []
    for rec in profile_labels:
        box = rec.get("box")
        if not box:
            continue
        text = rec.get("text")
        label = (
            text
            or rec.get("content_desc")
            or rec.get("resource_id")
            or rec.get("class")
            or "?"
        )
        if (
            exclude_text is not None
            and label.strip() == exclude_text
        ):
            continue
        x1, y1, x2, y2 = box
        lines.append(f'- "{label}" [{x1},{y1}][{x2},{y2}]')
    return "\n".join(lines)

def get_png_dimensions(image_path: Path) -> tuple[int, int]:
    """Extract width and height from a PNG file without external libraries."""
    with open(image_path, "rb") as f:
        f.read(16)
        width, height = struct.unpack(">II", f.read(8))
        return width, height


def score_one_trial(
    raw_response: str,
    box: list[int],
    baseline_box: list[int],
    img_width: int,
    img_height: int,
) -> tuple[int, int, int, str]:
    """
    Turn one raw model reply into a scored prediction.

    Returns (x_pred, y_pred, score, parse_method). Predictions that cannot be
    parsed, or that land outside the image, are recorded as (-1, -1) misses --
    the model was asked and answered, so this is a genuine grounding failure
    rather than a missing measurement.
    """
    x_coord, y_coord, parse_method = parse_coordinates_detailed(raw_response)

    if (
        x_coord < 0
        or y_coord < 0
        or x_coord > img_width
        or y_coord > img_height
    ):
        return -1, -1, 0, parse_method

    x_pred, y_pred = int(x_coord), int(y_coord)
    return x_pred, y_pred, hit_test(x_pred, y_pred, box, baseline_box), parse_method


def evaluate_screen(
    model: str,
    screen_name: str,
    pace_seconds: float,
    results_csv: Path,
    images_dir: Path = IMAGES_DIR,
    labels_dir: Path = LABELS_DIR,
    profiles: list[str] | None = None,
    use_a11y_tree: bool = False,
    trials: int = 1,
    completed: set[tuple[str, str, str]] | None = None,
) -> int:
    """
    Evaluate all profiles for a single screen.

    When use_a11y_tree is True, injects the accessibility tree into the
    prompt alongside the screenshot. When False, runs vision-only (unchanged).

    When trials > 1 the same query is sent that many times and scored by
    majority vote, which measures rather than assumes the stability of a
    single stochastic draw.

    Targets absent from a profile's layout are recorded with
    status=off_screen and NO score. They are a property of the layout, not a
    grounding failure, and are analysed separately as reachability.

    Returns the total number of evaluation rows generated.
    """
    targets = harvest_targets(screen_name, labels_dir)
    if not targets:
        print(f"  [SKIP] No targets for screen: {screen_name}")
        return 0

    count = 0
    profiles_to_run = profiles if profiles is not None else ALL_PROFILES
    already_done = completed if completed is not None else set()

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
        trial_tag = f" x{trials}" if trials > 1 else ""
        print(f"\n  -- {screen_name} / {profile_name}{mode_tag}{trial_tag} "
              f"({len(targets)} targets) --")

        for target in targets:
            target_text = target["text"]
            baseline_box = target["baseline_box"]

            if (screen_name, target_text, profile_name) in already_done:
                continue

            box = find_element_in_profile(profile_labels, target_text)

            if box is None:
                # Not a model failure: the element does not exist in this
                # layout, so there is nothing to ground. Score is left empty
                # so the analysis cannot mistake it for a wrong answer.
                append_result(results_csv, {
                    "screen": screen_name,
                    "target_text": target_text,
                    "profile": profile_name,
                    "status": STATUS_OFF_SCREEN,
                    "raw_response": "",
                    "x_pred": "", "y_pred": "",
                    "x_min": "", "y_min": "", "x_max": "", "y_max": "",
                    "score": "",
                    "trials": 0, "trial_scores": "", "parse_method": "",
                })
                count += 1
                print(f"    [OFF-SCREEN] '{target_text}' -> no measurement")
                continue

            if use_a11y_tree:
                # Withhold the target's own row so the tree provides
                # spatial context without leaking the answer's bounds.
                tree_text = build_tree_text(profile_labels, exclude_text=target_text)
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

            trial_results = []
            api_error: Exception | None = None

            for _ in range(max(1, trials)):
                try:
                    raw_response = call_vlm(model, image_path, prompt)
                except Exception as exc:
                    api_error = exc
                    break
                trial_results.append(
                    (raw_response,) + score_one_trial(
                        raw_response, box, baseline_box, img_width, img_height
                    )
                )
                if pace_seconds > 0:
                    time.sleep(pace_seconds)

            if api_error is not None:
                print(f"    [API-ERROR] '{target_text}': {api_error}")
                append_result(results_csv, {
                    "screen": screen_name,
                    "target_text": target_text,
                    "profile": profile_name,
                    "status": STATUS_API_ERROR,
                    "raw_response": f"[API-ERROR: {type(api_error).__name__}]",
                    "x_pred": "", "y_pred": "",
                    "x_min": box[0], "y_min": box[1],
                    "x_max": box[2], "y_max": box[3],
                    "score": "",
                    "trials": len(trial_results), "trial_scores": "",
                    "parse_method": "",
                })
                count += 1
                continue

            # Majority vote across trials; ties resolve to a miss.
            scores = [t[3] for t in trial_results]
            score = 1 if sum(scores) * 2 > len(scores) else 0

            # Report the first trial that agrees with the majority, so the
            # logged coordinates match the logged score.
            representative = next(
                (t for t in trial_results if t[3] == score), trial_results[0]
            )
            raw_response, x_pred, y_pred, _, parse_method = representative

            append_result(results_csv, {
                "screen": screen_name,
                "target_text": target_text,
                "profile": profile_name,
                "status": STATUS_CO_PRESENT,
                "raw_response": raw_response.replace("\r", " ").replace("\n", " ").strip(),
                "x_pred": x_pred, "y_pred": y_pred,
                "x_min": box[0], "y_min": box[1],
                "x_max": box[2], "y_max": box[3],
                "score": score,
                "trials": len(scores),
                "trial_scores": "".join(str(s) for s in scores),
                "parse_method": parse_method,
            })
            count += 1

            status = "HIT" if score == 1 else "MISS"
            unstable = " [UNSTABLE]" if len(set(scores)) > 1 else ""
            safe_text = target_text.encode('ascii', 'replace').decode('ascii')
            print(f"    [{status}] '{safe_text}' -> pred=({x_pred},{y_pred}) "
                  f"box={box}{unstable}")

    return count


def summarize_run(results_csv: Path) -> dict:
    """
    Summarise a finished run: status mix, parse failures, and trial flip rate.

    The flip rate is the share of multi-trial targets whose trials disagreed.
    It is what lets a run answer "how do you know this is not sampling noise?"
    with a measurement instead of an assumption.
    """
    import csv as _csv

    if not results_csv.is_file():
        return {}

    statuses: Counter = Counter()
    parse_failures = 0
    multi_trial = 0
    flipped = 0

    with open(results_csv, "r", newline="", encoding="utf-8") as f:
        for row in _csv.DictReader(f):
            statuses[row.get("status", "")] += 1
            if row.get("parse_method") == PARSE_FAILED:
                parse_failures += 1
            trial_scores = row.get("trial_scores", "")
            if len(trial_scores) > 1:
                multi_trial += 1
                if len(set(trial_scores)) > 1:
                    flipped += 1

    return {
        "statuses": dict(statuses),
        "parse_failures": parse_failures,
        "multi_trial_rows": multi_trial,
        "flipped_rows": flipped,
        "flip_rate": (flipped / multi_trial) if multi_trial else None,
    }
