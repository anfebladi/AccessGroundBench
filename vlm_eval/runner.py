"""Evaluation loop for VLM grounding benchmark runs."""

import json
import time
from collections import Counter
from pathlib import Path

from vlm_provider import call_vlm

from .config import ALL_PROFILES, IMAGES_DIR, LABELS_DIR
from .results import (
    PROMPT_MODE_TREE,
    PROMPT_MODE_VISION,
    STATUS_API_ERROR,
    STATUS_CO_PRESENT,
    STATUS_LABEL_CHANGED,
    STATUS_OFF_FRAME,
    STATUS_OFF_SCREEN,
    append_result,
)
from .scoring import PARSE_FAILED, get_png_dimensions, hit_test, parse_coordinates_detailed
from .targets import MATCH_EXACT, harvest_targets, locate_element

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
    "Provide the exact central pixel (x, y) coordinates "
    "needed to click on the text element: '{target_text}'. "
    "Return your response strictly in the bracket format: [x, y]"
)


def collect_tree_rows(
    profile_labels: list[dict],
    exclude_text: str | None = None,
    target_box: list[int] | None = None,
    baseline_box: list[int] | None = None,
) -> list[tuple[str, list[int]]]:
    """Collect a profile's label records into (label, box) rows.

    Each row is one UI element with its best available label and pixel
    bounding box. Falls back through: text -> content_desc -> resource_id ->
    class.

    Two independent exclusions keep the tree from handing the model the answer.
    Both only ever REMOVE rows, so neither can inflate a tree-mode result: a
    withheld row can make the task harder, never easier.

    1. LABEL exclusion (exclude_text). Any element whose RENDERED LABEL matches
       the target is withheld, so the tree never names the thing being asked
       about. This must be checked against the same fallback chain used to
       build the label, not against `text` alone: a node with empty `text` but
       `content_desc == exclude_text` still renders the target's name, so
       checking `text` alone let it through. Measured on the archived dataset,
       that leaked 22 of 168 targets (13.1%).

    2. BOUNDS exclusion (target_box + baseline_box). Any row whose box CENTRE
       would score a hit under scoring.hit_test is withheld, regardless of its
       label. The label exclusion alone does not cover this: a parent
       container labelled e.g. "navigation_bar_item_content_container" never
       renders the target's name, but its centre can sit inside the target's
       scoring box, so a model could score by reading the tree rather than
       looking at the image. Measured on the current dataset, the label
       exclusion alone left 575 of 853 target x profile pairs (67.4%) with at
       least one such row -- mean 2.12 hitting rows out of a ~74-row tree.

       Removing them costs ~3% of spatial context. Without it a tree-mode
       improvement is uninterpretable, because "the tree helped the model
       locate the element" and "the model read a nearby container's centre off
       the tree" predict the same result, and the confound points the same way
       as the hypothesis.

    Both boxes are required for the bounds exclusion, since hit_test scores a
    baseline-sized box centred on the current profile's box (see
    scoring.hit_test). When either is None only the label exclusion applies,
    which keeps existing non-tree callers working unchanged.

    This is the single source of truth for the exclusions; every rendering of
    the tree (per-model prompt formats included) must be built from this
    function's output rather than re-deriving the fallback/exclusion logic,
    or the leak fix can silently regress in one rendering while holding in
    another.
    """
    check_bounds = target_box is not None and baseline_box is not None

    rows = []
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
            and label.strip() == exclude_text.strip()
        ):
            continue
        if check_bounds:
            centre_x = (box[0] + box[2]) // 2
            centre_y = (box[1] + box[3]) // 2
            if hit_test(centre_x, centre_y, target_box, baseline_box):
                continue
        rows.append((label, list(box)))
    return rows


def build_tree_text(
    profile_labels: list[dict],
    exclude_text: str | None = None,
    target_box: list[int] | None = None,
    baseline_box: list[int] | None = None,
) -> str:
    """Render a profile's label records into a compact accessibility-tree string.

    See collect_tree_rows for the fallback/exclusion rules this builds on.
    """
    lines = [
        f'- "{label}" [{x1},{y1}][{x2},{y2}]'
        for label, (x1, y1, x2, y2) in collect_tree_rows(
            profile_labels, exclude_text, target_box, baseline_box
        )
    ]
    return "\n".join(lines)

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

            match = locate_element(profile_labels, target_text)

            if match is None:
                # Not a model failure: nothing in this layout plausibly
                # corresponds to the target, exact or relaxed. Score is left
                # empty so the analysis cannot mistake it for a wrong answer.
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
                    "prompt_mode": PROMPT_MODE_TREE if use_a11y_tree else PROMPT_MODE_VISION,
                    "tree_rows_sent": 0,
                })
                count += 1
                print(f"    [OFF-SCREEN] '{target_text}' -> no measurement")
                continue

            box, matched_text, match_kind = match

            box_cx = (box[0] + box[2]) / 2.0
            box_cy = (box[1] + box[3]) / 2.0
            if not (0 <= box_cx <= img_width and 0 <= box_cy <= img_height):
                # The element is genuinely present in the layout, but its
                # recorded box's center falls outside the screenshot -- a
                # clipped/partially-off-screen node whose extent exceeds the
                # crop (see bound_extractor.extract's clamping, which
                # prevents this for newly-extracted labels; this is a
                # defensive check for label files extracted before that fix,
                # or any other source of an out-of-frame box). hit_test
                # cannot score a point that is not on the image, so this is
                # unscoreable rather than a grounding failure -- it must not
                # be silently counted as a miss.
                append_result(results_csv, {
                    "screen": screen_name,
                    "target_text": target_text,
                    "profile": profile_name,
                    "status": STATUS_OFF_FRAME,
                    "raw_response": "",
                    "x_pred": "", "y_pred": "",
                    "x_min": box[0], "y_min": box[1],
                    "x_max": box[2], "y_max": box[3],
                    "score": "",
                    "trials": 0, "trial_scores": "", "parse_method": "",
                    "prompt_mode": PROMPT_MODE_TREE if use_a11y_tree else PROMPT_MODE_VISION,
                    "tree_rows_sent": 0,
                })
                count += 1
                print(f"    [OFF-FRAME] '{target_text}' -> box center outside "
                      f"image, no measurement")
                continue

            if match_kind != MATCH_EXACT:
                # The element is still rendered, but reflow changed its label
                # text enough that the exact-string lookup missed it. This is
                # not "off screen" and not a model answer -- it is a distinct,
                # deliberately unscored category. Whether/how to query it is
                # an open sample-definition decision (see CLAUDE.md's
                # remediation plan); recording it here makes the category
                # visible and countable without pre-deciding that question.
                safe_matched = matched_text.encode("ascii", "replace").decode("ascii")
                append_result(results_csv, {
                    "screen": screen_name,
                    "target_text": target_text,
                    "profile": profile_name,
                    "status": STATUS_LABEL_CHANGED,
                    "raw_response": f"[LABEL-CHANGED: {matched_text}]",
                    "x_pred": "", "y_pred": "",
                    "x_min": box[0], "y_min": box[1],
                    "x_max": box[2], "y_max": box[3],
                    "score": "",
                    "trials": 0, "trial_scores": "", "parse_method": "",
                    "prompt_mode": PROMPT_MODE_TREE if use_a11y_tree else PROMPT_MODE_VISION,
                    "tree_rows_sent": 0,
                })
                count += 1
                print(f"    [LABEL-CHANGED] '{target_text}' -> now rendered as "
                      f"'{safe_matched}'")
                continue

            # Withhold both the target's own row AND any row whose centre
            # would score a hit on it, so any tree rendering (of any model's
            # prompt format) provides spatial context without handing over a
            # point that scores. See collect_tree_rows for why the label
            # exclusion alone is not enough. Collected unconditionally so it
            # can be passed to call_vlm as structured context even when the
            # shared hosted-model prompt below doesn't need it rendered.
            tree_rows = (
                collect_tree_rows(
                    profile_labels,
                    exclude_text=target_text,
                    target_box=box,
                    baseline_box=baseline_box,
                )
                if use_a11y_tree
                else None
            )

            if use_a11y_tree:
                tree_text = "\n".join(
                    f'- "{label}" [{x1},{y1}][{x2},{y2}]'
                    for label, (x1, y1, x2, y2) in tree_rows
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

            trial_results = []
            api_error: Exception | None = None

            for _ in range(max(1, trials)):
                try:
                    raw_response = call_vlm(
                        model,
                        image_path,
                        prompt,
                        target_text=target_text,
                        tree_rows=tree_rows,
                        img_width=img_width,
                        img_height=img_height,
                    )
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
                    "prompt_mode": PROMPT_MODE_TREE if use_a11y_tree else PROMPT_MODE_VISION,
                    "tree_rows_sent": 0,
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
                "prompt_mode": PROMPT_MODE_TREE if use_a11y_tree else PROMPT_MODE_VISION,
                "tree_rows_sent": len(tree_rows) if tree_rows else 0,
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
