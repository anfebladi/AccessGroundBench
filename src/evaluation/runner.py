"""Evaluation loop for VLM grounding benchmark runs."""

import json
import time
from collections import Counter
from pathlib import Path

from .providers import call_vlm

from .config import ALL_PROFILES, DEFAULT_COORD_SPACE, IMAGES_DIR, LABELS_DIR
from .storage.results import (
    PROMPT_MODE_TREE,
    PROMPT_MODE_VISION,
    STATUS_API_ERROR,
    STATUS_CO_PRESENT,
    STATUS_LABEL_CHANGED,
    STATUS_OFF_FRAME,
    STATUS_OFF_SCREEN,
    append_result,
)
from .grounding.scoring import (
    PARSE_FAILED,
    get_png_dimensions,
    hit_test,
    parse_coordinates_detailed,
    to_pixel_space,
)
from .grounding.targets import MATCH_EXACT, harvest_targets, locate_element

from .grounding.task_prompting import (
    PROMPT_TEMPLATE,
    PROMPT_TEMPLATE_WITH_TREE,
    build_tree_text,
    collect_tree_rows,
)

def score_one_trial(
    raw_response: str,
    box: list[int],
    baseline_box: list[int],
    img_width: int,
    img_height: int,
    coord_space: str = DEFAULT_COORD_SPACE,
) -> tuple[int, int, int, str]:
    """
    Turn one raw model reply into a scored prediction.

    Returns (x_pred, y_pred, score, parse_method). Predictions that cannot be
    parsed, or that land outside the image, are recorded as (-1, -1) misses --
    the model was asked and answered, so this is a genuine grounding failure
    rather than a missing measurement.

    coord_space is the space *this reply* was resolved to, not the model's
    general convention. A model on the 0-1000 grid can still answer a given
    query in pixels (evaluation.providers retries, then records it as such) or
    unparseably; converting those would corrupt a reply that needs no
    conversion, so the decision is made per reply rather than per model.
    """
    x_coord, y_coord, parse_method = parse_coordinates_detailed(raw_response)
    x_coord, y_coord = to_pixel_space(
        x_coord, y_coord, img_width, img_height, coord_space
    )

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
    coord_space: str = DEFAULT_COORD_SPACE,
) -> int:
    """Evaluate all profiles for a single screen.

    use_a11y_tree=True injects the accessibility tree into the prompt
    alongside the screenshot; otherwise runs vision-only. trials > 1 sends
    the same query that many times and scores by majority vote, measuring
    rather than assuming the stability of a single stochastic draw.

    coord_space declares the convention the model answers in; "norm1000"
    responses are rescaled to pixels before hit-testing.

    Returns the total number of evaluation rows generated.
    """
    # Targets absent from a profile's layout are recorded with
    # status=off_screen and NO score: they are a property of the layout,
    # not a grounding failure, and are analysed separately as
    # reachability.
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
                # deliberately unscored category, so it is recorded rather
                # than queried: whether/how such a target should eventually be
                # scored is a separate decision that recording it here does
                # not pre-empt.
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
            trial_coord_spaces = []
            api_error: Exception | None = None

            for _ in range(max(1, trials)):
                coord_space_out: dict = {}
                try:
                    raw_response = call_vlm(
                        model,
                        image_path,
                        prompt,
                        target_text=target_text,
                        tree_rows=tree_rows,
                        img_width=img_width,
                        img_height=img_height,
                        coord_space_out=coord_space_out,
                    )
                except Exception as exc:
                    api_error = exc
                    break
                # Models evaluation.providers recognises report the space they actually
                # answered in for this reply; anything else falls back to the
                # run-level COORD_SPACE override.
                reply_space = coord_space_out.get("value", "") or coord_space
                trial_coord_spaces.append(coord_space_out.get("value", ""))
                trial_results.append(
                    (raw_response,) + score_one_trial(
                        raw_response, box, baseline_box, img_width, img_height,
                        coord_space=reply_space,
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
            # logged coordinates (and coord_space) match the logged score.
            representative_index = next(
                (i for i, t in enumerate(trial_results) if t[3] == score), 0
            )
            raw_response, x_pred, y_pred, _, parse_method = trial_results[representative_index]
            # Distinct from the `coord_space` parameter (the run-level override):
            # this is what the representative reply resolved to, and it is what
            # gets logged.
            reported_coord_space = trial_coord_spaces[representative_index]

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
                "coord_space": reported_coord_space,
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
