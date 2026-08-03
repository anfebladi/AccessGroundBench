"""
mcnemar_analysis.py
-------------------
Phase 4: statistical analysis of VLM grounding under accessibility profiles.

Reports three things, deliberately kept apart:

  1. REACHABILITY -- what fraction of baseline targets still exist in the
     modified layout. A property of Android under that setting, identical for
     every model, and no inferential statistics are required.

  2. GROUNDING, pooled (PRIMARY) -- cluster permutation test across all models
     on the targets present in both layouts.

  3. GROUNDING, per model (SECONDARY) -- McNemar per model x profile with
     Holm-Bonferroni correction, plus floor and ceiling checks.

Why 1 and 2 are separate: earlier revisions scored a target 0 when it was
absent from the modified layout, without ever querying the model, and counted
that as a grounding failure. "The element is not on screen" and "the model
looked in the wrong place" are different phenomena and must not share a cell in
the contingency table. Conflating them inflated significance from 4 tests to 24
and systematically penalised the most accurate models, because a target can
only be recorded as broken if the model got it right at baseline.

Usage:
  python mcnemar_analysis.py                              # all CSVs in dataset/
  python mcnemar_analysis.py --data-dir dataset/experiment_2
  python mcnemar_analysis.py --csv path/to/results.csv
  python mcnemar_analysis.py --compare-a vision.csv --compare-b tree.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from vlm_eval.scoring import get_png_dimensions
from vlm_eval.targets import MAX_TARGET_CHARS, box_contains, locate_element
from vlm_eval.stats import (
    DEFAULT_PERMUTATIONS,
    cluster_permutation_test,
    conditional_odds_ratio,
    holm_bonferroni,
    mcnemar_test,
    paired_difference_interval,
    sign_test,
    wilson_interval,
)

PROJECT_ROOT = Path(__file__).parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "dataset"

ALPHA = 0.05

# Baseline accuracy below which McNemar cannot detect degradation: most targets
# already fail, so only (a + b) of them could ever break.
FLOOR_ACC_THRESHOLD = 50.0

# Baseline accuracy above which McNemar is equally uninformative in the other
# direction. At 99% there is almost nothing left to break, so a null result
# means "underpowered", not "resilient" -- the same error the floor check
# exists to prevent, mirrored at the top of the scale.
CEILING_ACC_THRESHOLD = 95.0

# elder_combo_rtl was dropped and renamed to elder_combo_mid: even with the
# correct RTL setting key, re-collection still measured 0% mirroring across
# every screen, so the profile is now honestly labelled as a second geometry
# condition (font 1.5 / density 480) rather than a mirroring condition. See
# dataset/experiment_2/README.md for the historical unverified arm.
EXPERIMENTAL_PROFILES = [
    "elder_text_heavy",
    "elder_zoom_heavy",
    "elder_combo_max",
    "elder_combo_mid",
    "colorblind_deuteranomaly",
]

# Row statuses. Only co_present rows carry a meaningful score.
STATUS_CO_PRESENT = "co_present"
STATUS_OFF_SCREEN = "off_screen"
STATUS_API_ERROR = "api_error"

# The element is still rendered under this profile, but its label text
# changed enough that the collection-time exact-string lookup missed it (see
# vlm_eval.targets.locate_element / vlm_eval.results.STATUS_LABEL_CHANGED).
# Excluded from every scored table (build_clusters, compute_contingency, the
# per-model tables) automatically, because those all gate on
# status == STATUS_CO_PRESENT and a label_changed row is never that -- no
# separate exclusion code is needed there. It only affects reachability,
# where --label-changed controls how it is counted (see compute_reachability).
STATUS_LABEL_CHANGED = "label_changed"

# How compute_reachability treats STATUS_LABEL_CHANGED rows. All three are
# free (no new API calls): the element's presence is known from the label
# JSON regardless of whether it was ever queried. This does NOT affect the
# scored/contingency tables -- those never contain label_changed rows, since
# such a target was never queried (see STATUS_LABEL_CHANGED above), so there
# is no score to include there under any mode.
LABEL_CHANGED_MODES = ("exclude", "unreachable", "reachable")
DEFAULT_LABEL_CHANGED_MODE = "unreachable"  # matches pre-reclassification behaviour

# The element is on screen -- reachability must count it as present -- but
# its recorded box's center falls outside the screenshot, so there is no
# valid point to score against (see bound_extractor.extract's clamping and
# vlm_eval.results.STATUS_OFF_FRAME). Unlike STATUS_LABEL_CHANGED there is no
# open question about how to count it for reachability: the element exists,
# so it counts as present unconditionally. It is excluded from every scored
# table for the same structural reason label_changed rows are: neither ever
# satisfies status == STATUS_CO_PRESENT.
STATUS_OFF_FRAME = "off_frame"

# Prompt modes (see vlm_eval.results). Archived CSVs predate this column;
# treated as vision, matching what was actually run before tree mode existed.
PROMPT_MODE_VISION = "vision"
PROMPT_MODE_TREE = "tree"

# Suffix get_results_csv() (vlm_eval/config.py) appends to a tree-mode
# model's filename. Excluded from the default glob so a tree run can never
# be silently pooled into the vision-only pipeline as a phantom extra model
# -- the pooled permutation test and sign test both assume independent
# measurement streams, and vision/tree rows for the same model are maximally
# correlated, not independent.
WITH_TREE_SUFFIX = "_with_tree"


# ---------------------------------------------------------------------------
# Sample exclusion sets
#
# B1 (screen, condition) contamination exclusions and B2 task-validity target
# exclusions, composed into named samples that are all reported side by side
# -- never silently replacing the unrestricted numbers, since each rests on
# a judgment call about contamination severity that a reader may weigh
# differently.
# ---------------------------------------------------------------------------

_FONT_DENSITY_PROFILES = (
    "elder_text_heavy", "elder_zoom_heavy", "elder_combo_max", "elder_combo_mid",
)

# B1-minimal: the one cell with measured contamination (see B0 -- a colour-only
# profile's captured text set differing from baseline with no geometry vector
# changed). settings_display's font/density losses are pure contiguous tails
# in document order, i.e. ordinary scroll-off with no measured contamination,
# so they are NOT excluded here.
B1_MINIMAL: frozenset[tuple[str, str]] = frozenset({
    ("settings_display", "colorblind_deuteranomaly"),
})

# B1-precautionary: also drop both settings pages from every font/density
# condition regardless of demonstrated contamination, on the grounds that a
# page displaying the manipulated setting should not be measured under it.
# A sensitivity row, not the primary sample -- the drop-pattern evidence does
# not support it as the default.
B1_PRECAUTIONARY: frozenset[tuple[str, str]] = B1_MINIMAL | frozenset({
    (screen, profile)
    for screen in ("settings_display", "settings_accessibility")
    for profile in _FONT_DENSITY_PROFILES
})

# B1-uniform: both settings pages out of every condition, including colour --
# where settings_accessibility is demonstrably clean. Included only so a
# reviewer who wants one consistent pool across all five conditions has it.
B1_UNIFORM: frozenset[tuple[str, str]] = frozenset({
    (screen, profile)
    for screen in ("settings_display", "settings_accessibility")
    for profile in (*_FONT_DENSITY_PROFILES, "colorblind_deuteranomaly")
})

# B2: length cap for the task-validity exclusion (container nodes are always
# excluded regardless of length; see compute_b2_targets). Shares
# vlm_eval.targets.MAX_TARGET_CHARS, the same cap harvest_targets applies
# before a target is ever queried, so this analysis-side recomputation cannot
# drift from what current collections actually harvest -- it only differs on
# datasets collected before that cap existed (e.g. dataset/experiment_2 and
# the six hosted-model CSVs already on disk), which still carry the excluded
# rows and need this recomputation to filter them out after the fact.
B2_LENGTH_CAP = MAX_TARGET_CHARS

SAMPLES: dict[str, dict] = {
    "full":          {"b1": frozenset(), "b2": False},
    "primary":       {"b1": B1_MINIMAL, "b2": True},
    "precautionary": {"b1": B1_PRECAUTIONARY, "b2": True},
    "uniform":       {"b1": B1_UNIFORM, "b2": True},
}
SAMPLE_NAMES = list(SAMPLES)  # preserves definition order for output ordering
DEFAULT_SAMPLE = "primary"


def compute_b2_targets(baseline_rows: list[dict]) -> frozenset[tuple[str, str]]:
    """
    Compute B2's excluded (screen, target_text) set from this run's own
    baseline rows, rather than hardcoding target strings -- so it reproduces
    correctly against any dataset (a different collection run's Gmail
    content, or the archived experiment_2) instead of silently excluding
    nothing on data it was not written against.

    Excludes a target when it is a container whose box fully encloses another
    target's box on the same screen, or when its text exceeds B2_LENGTH_CAP
    characters. Both are the shape of Gmail's row-level nodes: a whole-email
    summary crammed into one label, enclosing its own sender/subject/preview
    as separate targets.
    """
    by_screen: dict[str, list[tuple[str, list[int]]]] = defaultdict(list)
    for r in baseline_rows:
        if r.get("status") != STATUS_CO_PRESENT:
            continue
        try:
            box = [int(r[k]) for k in ("x_min", "y_min", "x_max", "y_max")]
        except (KeyError, ValueError):
            continue
        by_screen[r["screen"]].append((r["target_text"], box))

    excluded: set[tuple[str, str]] = set()
    for screen, items in by_screen.items():
        for text, box in items:
            if len(text) > B2_LENGTH_CAP:
                excluded.add((screen, text))
                continue
            if any(box_contains(box, other_box) for other_text, other_box in items
                   if other_text != text):
                excluded.add((screen, text))
    return frozenset(excluded)


def target_excluded_for_condition(
    sample: str,
    screen: str,
    target_text: str,
    profile: str,
    b2_targets: frozenset[tuple[str, str]],
) -> bool:
    """True when (target, profile) should be dropped from `sample`'s pool for this one condition's tables."""
    if sample not in SAMPLES:
        raise ValueError(f"Unknown sample: {sample!r}")
    # B2 applies to a target across every condition, baseline included --
    # the target itself is task-invalid regardless of what it is compared
    # against, so this check does not depend on `profile`.
    if (screen, target_text) in b2_targets and SAMPLES[sample]["b2"]:
        return True
    # B1 applies only to the named (screen, profile) cell: the same target's
    # baseline reading, and its readings under every other condition, are
    # unaffected -- settings_display is contaminated under
    # colorblind_deuteranomaly specifically, not under every condition it
    # appears in.
    return (screen, profile) in SAMPLES[sample]["b1"]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def derive_status(row: dict) -> str:
    """
    Determine a row's status, tolerating pre-status CSVs.

    Newer runs write an explicit `status` column. Archived runs
    (dataset/experiment_2/) predate it, so the status is recovered from the
    sentinel values the old runner wrote into `raw_response`.

    Note an unparseable reply is co_present, not a separate exclusion: the
    model was asked and answered, it just answered unusably, which is a genuine
    grounding failure rather than a missing measurement.
    """
    status = (row.get("status") or "").strip()
    if status:
        return status

    raw = row.get("raw_response", "")
    if raw == "[OFF-SCREEN]":
        return STATUS_OFF_SCREEN
    if raw.startswith("[API-ERROR"):
        return STATUS_API_ERROR
    if raw.startswith("[LABEL-CHANGED:"):
        return STATUS_LABEL_CHANGED
    return STATUS_CO_PRESENT


def load_results(csv_path: Path) -> list[dict]:
    """Load an evaluation CSV, normalising the status column."""
    if not csv_path.is_file():
        print(f"[ERROR] Results CSV not found: {csv_path}")
        sys.exit(1)

    with open(csv_path, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        row["status"] = derive_status(row)
        # prompt_mode/tree_rows_sent were added after the archived
        # experiment_2 run, so older CSVs lack those columns entirely;
        # default them to vision/0 rather than letting downstream code see
        # missing keys.
        if not row.get("prompt_mode"):
            row["prompt_mode"] = PROMPT_MODE_VISION
        if not row.get("tree_rows_sent"):
            row["tree_rows_sent"] = "0"

    print(f"[LOADED] {len(rows)} rows from {csv_path.name}")
    return rows


def index_rows(rows: list[dict]) -> dict[tuple[str, str, str], dict]:
    """
    Index rows by (screen, target_text, profile).

    A plain dict comprehension over `rows` would let whichever row for a
    duplicated key came LAST in the file silently win -- and a stale
    api_error row appended after a real answer (an interrupted-collection
    artifact, not a re-run of this code) would then shadow that real answer
    out of every downstream table, since they all gate on
    status == STATUS_CO_PRESENT. This prefers any real (non-api_error) row
    over an api_error row regardless of position, and warns rather than
    silently resolving the rest, so a corrupted file can never be consumed
    quietly again the way gpt-5.4_with_tree.csv was.
    """
    index: dict[tuple[str, str, str], dict] = {}
    key_counts: Counter = Counter()

    for r in rows:
        key = (r.get("screen", ""), r.get("target_text", ""), r.get("profile", ""))
        key_counts[key] += 1
        if key not in index:
            index[key] = r
            continue
        if index[key].get("status") == STATUS_API_ERROR and r.get("status") != STATUS_API_ERROR:
            index[key] = r
        # else: keep whichever real (or first api_error) row is already
        # stored -- a later api_error must never overwrite a real answer.

    duplicates = {k: c for k, c in key_counts.items() if c > 1}
    if duplicates:
        print(
            f"[WARN] {len(duplicates)} duplicate (screen, target_text, profile) "
            f"key(s) found among {len(rows)} rows; kept the first real "
            "(non-api_error) row for each and ignored the rest. This CSV "
            "should be canonicalized (vlm_eval.results.canonicalize_rows / "
            "finalize_csv) rather than analyzed repeatedly in this state."
        )

    return index


def _load_profile_labels(labels_dir: Path, screen: str, profile: str) -> list[dict]:
    """Load one screen/profile's label JSON, or [] if it is not on disk."""
    path = labels_dir / f"{screen}_{profile}.json"
    if not path.is_file():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def reclassify_label_changed(
    rows: list[dict],
    labels_dir: Path,
) -> list[dict]:
    """Recover the label_changed / off_screen distinction for CSVs collected before it existed.

    Mutates and returns `rows`.
    """
    # A row written STATUS_OFF_SCREEN before vlm_eval.runner started using
    # locate_element's relaxed match may actually be an element whose label
    # text reflowed but is still on screen -- the collection-time code could
    # not tell the two apart. Re-check each such row against the current
    # label JSON (unchanged since collection; no re-capture or API call
    # involved) and, when a relaxed match resolves it, rewrite the row's
    # status to STATUS_LABEL_CHANGED in memory only. Rows already written
    # with an explicit status are left untouched -- exact matches at
    # collection time are authoritative and never revisited here.
    #
    # This is purely a reachability-side correction: STATUS_LABEL_CHANGED
    # rows never satisfy status == STATUS_CO_PRESENT, so every
    # scored/contingency table already excludes them unchanged. Callers that
    # want the breakdown scan the returned rows for STATUS_LABEL_CHANGED
    # themselves (see report_label_changed_breakdown).
    if not labels_dir.is_dir():
        print(f"  [WARN] Labels directory not found: {labels_dir} "
              "-- skipping label_changed reclassification.")
        return rows

    label_cache: dict[tuple[str, str], list[dict]] = {}
    reclassified = 0

    for row in rows:
        if row.get("status") != STATUS_OFF_SCREEN:
            continue

        screen = row.get("screen", "")
        profile = row.get("profile", "")
        target_text = row.get("target_text", "")

        key = (screen, profile)
        if key not in label_cache:
            label_cache[key] = _load_profile_labels(labels_dir, screen, profile)
        profile_labels = label_cache[key]
        if not profile_labels:
            continue

        match = locate_element(profile_labels, target_text)
        if match is None:
            continue

        box, matched_text, _match_kind = match
        row["status"] = STATUS_LABEL_CHANGED
        row["_label_changed_matched_text"] = matched_text
        row["_label_changed_box"] = box
        reclassified += 1

    if reclassified:
        print(f"  [RECLASSIFY] {reclassified} off_screen row(s) recovered as "
              f"label_changed against {labels_dir}")

    return rows


def reclassify_off_frame(rows: list[dict], images_dir: Path) -> list[dict]:
    """Recover the off_frame distinction for rows collected before bound_extractor clamped bounds to the visible area.

    Mutates and returns `rows`.
    """
    # A row with a box whose center falls outside its screenshot (a node
    # clipped at the crop edge but retained at full, uncropped size) could
    # not have been meaningfully scored -- hit_test compared the model's
    # answer to a point that was never on the image. Re-check every row that
    # carries a box (STATUS_CO_PRESENT or STATUS_LABEL_CHANGED; off_screen
    # rows have none) against the actual screenshot dimensions on disk
    # (unchanged since collection; no re-capture or API call involved) and
    # rewrite the status to STATUS_OFF_FRAME in memory when the center lands
    # outside it.
    #
    # Purely a scoring-side correction: STATUS_OFF_FRAME rows never satisfy
    # status == STATUS_CO_PRESENT, so every scored/contingency table already
    # excludes them unchanged. Reachability is unaffected in the other
    # direction -- the element genuinely exists in the layout, so it must
    # keep counting as present; compute_reachability's
    # `status != STATUS_OFF_SCREEN` check already handles any status other
    # than off_screen correctly, off_frame included.
    if not images_dir.is_dir():
        print(f"  [WARN] Images directory not found: {images_dir} "
              "-- skipping off_frame reclassification.")
        return rows

    dim_cache: dict[tuple[str, str], tuple[int, int] | None] = {}
    reclassified = 0

    for row in rows:
        if row.get("status") not in (STATUS_CO_PRESENT, STATUS_LABEL_CHANGED):
            continue

        x_min, y_min = row.get("x_min", ""), row.get("y_min", "")
        x_max, y_max = row.get("x_max", ""), row.get("y_max", "")
        if not (x_min and y_min and x_max and y_max):
            continue
        try:
            x_min, y_min, x_max, y_max = int(x_min), int(y_min), int(x_max), int(y_max)
        except ValueError:
            continue

        screen = row.get("screen", "")
        profile = row.get("profile", "")
        key = (screen, profile)
        if key not in dim_cache:
            png_path = images_dir / f"{screen}_{profile}.png"
            dim_cache[key] = get_png_dimensions(png_path) if png_path.is_file() else None
        dims = dim_cache[key]
        if dims is None:
            continue
        img_w, img_h = dims

        cx = (x_min + x_max) / 2.0
        cy = (y_min + y_max) / 2.0
        if 0 <= cx <= img_w and 0 <= cy <= img_h:
            continue

        row["status"] = STATUS_OFF_FRAME
        reclassified += 1

    if reclassified:
        print(f"  [RECLASSIFY] {reclassified} row(s) recovered as off_frame "
              f"against {images_dir}")

    return rows


def model_name_from_path(csv_path: Path) -> str:
    """Recover the model id from an evaluation_results_*.csv filename."""
    name = csv_path.stem.replace("evaluation_results_", "")
    return "default" if name == "evaluation_results" else name


def discover_result_csvs(data_dir: Path, mode: str) -> list[Path]:
    """
    Find evaluation_results_*.csv files for one prompt-mode arm.

    Vision and tree results for the same model are correlated, not
    independent measurements (the tree run repeats the same queries with
    context added), so the default glob must never pool a model's *.csv with
    its *_with_tree.csv counterpart -- doing so would feed both arms into the
    pooled cluster permutation test and the sign test as if they were two
    independent models, silently doubling the effective sample.
    """
    all_csv_files = sorted(data_dir.glob("evaluation_results_*.csv"))
    if mode == "tree":
        return [p for p in all_csv_files if p.stem.endswith(WITH_TREE_SUFFIX)]
    return [p for p in all_csv_files if not p.stem.endswith(WITH_TREE_SUFFIX)]


# ---------------------------------------------------------------------------
# Section 1: reachability
# ---------------------------------------------------------------------------

def compute_reachability(
    index: dict,
    profile: str,
    label_changed_mode: str = DEFAULT_LABEL_CHANGED_MODE,
    sample: str = "full",
    b2_targets: frozenset[tuple[str, str]] = frozenset(),
) -> tuple[int, int]:
    """Count how many baseline targets still exist in a profile's layout.

    Returns (present, total). Model-independent: it depends only on which
    targets the capture found, never on a model's answer.
    """
    # label_changed_mode controls how STATUS_LABEL_CHANGED rows are counted
    # (see LABEL_CHANGED_MODES): "exclude" removes them from both present
    # and total (the target is dropped from the pool for this profile);
    # "unreachable" counts them in total but not present (the
    # pre-reclassification behaviour, since they used to be
    # indistinguishable from off_screen); "reachable" counts them in both.
    # All three are free -- reachability only needs presence, never a score.
    #
    # sample/b2_targets apply the sample's exclusions (see
    # target_excluded_for_condition): an excluded (target, profile) pair is
    # dropped from both present and total, same as
    # label_changed_mode="exclude" -- the target is removed from the pool
    # for this profile, not counted as unreachable.
    if label_changed_mode not in LABEL_CHANGED_MODES:
        raise ValueError(f"Unknown label_changed_mode: {label_changed_mode!r}")

    present = total = 0
    for (screen, text, prof) in index:
        if prof != "baseline":
            continue
        if target_excluded_for_condition(sample, screen, text, profile, b2_targets):
            continue
        row = index.get((screen, text, profile))
        if row is None:
            continue

        if row["status"] == STATUS_LABEL_CHANGED:
            if label_changed_mode == "exclude":
                continue
            total += 1
            if label_changed_mode == "reachable":
                present += 1
            continue

        total += 1
        if row["status"] != STATUS_OFF_SCREEN:
            present += 1
    return present, total


def report_reachability(
    index: dict,
    profiles: list[str],
    label_changed_mode: str = DEFAULT_LABEL_CHANGED_MODE,
    sample: str = "full",
    b2_targets: frozenset[tuple[str, str]] = frozenset(),
) -> list[dict]:
    """Print and return the reachability table for one model's captures."""
    print("\n" + "=" * 78)
    print(f"  SECTION 1 -- REACHABILITY (model-independent)  [sample={sample}]")
    print("  Share of baseline targets still present in the modified layout.")
    print(f"  label_changed rows counted as: {label_changed_mode}")
    print("=" * 78)
    print(f"  {'Profile':<28}{'Present':>9}{'Total':>7}{'Reachable':>12}   95% CI")
    print(f"  {'-' * 28}{'-' * 9:>9}{'-' * 7:>7}{'-' * 12:>12}   {'-' * 18}")

    table = []
    for profile in profiles:
        present, total = compute_reachability(
            index, profile, label_changed_mode, sample, b2_targets
        )
        rate = present / total if total else 0.0
        low, high = wilson_interval(present, total)
        print(f"  {profile:<28}{present:>9}{total:>7}{rate * 100:>11.1f}%   "
              f"[{low * 100:5.1f}%, {high * 100:5.1f}%]")
        table.append({
            "sample": sample, "profile": profile, "present": present, "total": total,
            "rate": rate, "ci_low": low, "ci_high": high,
        })
    return table


def report_label_changed_breakdown(index: dict, profiles: list[str]) -> list[dict]:
    """Print and return every STATUS_LABEL_CHANGED row: which target, under which profile, and what it now renders as.

    Deliberately only measures and reports; how label_changed targets should
    ultimately be treated in scoring is a separate decision this function
    does not make.
    """
    rows_out = []
    for (screen, text, profile), row in sorted(index.items()):
        if profile == "baseline" or row["status"] != STATUS_LABEL_CHANGED:
            continue
        matched = row.get("_label_changed_matched_text", "")
        rows_out.append({
            "screen": screen, "profile": profile,
            "baseline_text": text, "matched_text": matched,
        })

    print("\n" + "=" * 78)
    print("  SECTION 1b -- LABEL_CHANGED BREAKDOWN")
    print("  Elements still on screen whose label text no longer matches")
    print("  the baseline string exactly (relaxed match). Not queried, not")
    print("  scored -- reported here so the category is visible before any")
    print("  decision is made about how to treat it.")
    print("=" * 78)
    if not rows_out:
        print("  (none)")
        return rows_out

    by_screen_profile: dict[tuple[str, str], int] = defaultdict(int)
    for r in rows_out:
        by_screen_profile[(r["screen"], r["profile"])] += 1

    print(f"  {'Screen':<26}{'Profile':<24}{'Count':>7}")
    print(f"  {'-' * 26}{'-' * 24}{'-' * 7}")
    for (screen, profile), n in sorted(by_screen_profile.items()):
        print(f"  {screen:<26}{profile:<24}{n:>7}")

    print(f"\n  {len(rows_out)} label_changed row(s) total. Matched pairs:")
    for r in rows_out:
        base_safe = r["baseline_text"][:60].encode("ascii", "replace").decode("ascii")
        matched_safe = r["matched_text"][:60].encode("ascii", "replace").decode("ascii")
        print(f"    [{r['screen']}/{r['profile']}] {base_safe!r} -> {matched_safe!r}")

    return rows_out


# ---------------------------------------------------------------------------
# Section 2: pooled cluster permutation (primary)
# ---------------------------------------------------------------------------

def build_clusters(
    indices: dict[str, dict],
    profile: str,
    sample: str = "full",
    b2_targets: frozenset[tuple[str, str]] = frozenset(),
) -> dict[tuple[str, str], list[tuple[int, int]]]:
    """
    Group paired outcomes by target across every model.

    One cluster is one (screen, target_text); its list holds that target's
    (baseline_score, profile_score) under each model. Only co_present rows in
    both arms are included, and only targets not excluded by `sample` for
    this `profile` (see target_excluded_for_condition).
    """
    clusters: dict[tuple[str, str], list[tuple[int, int]]] = defaultdict(list)

    for index in indices.values():
        for (screen, text, prof), baseline_row in index.items():
            if prof != "baseline" or baseline_row["status"] != STATUS_CO_PRESENT:
                continue
            if target_excluded_for_condition(sample, screen, text, profile, b2_targets):
                continue
            exp_row = index.get((screen, text, profile))
            if exp_row is None or exp_row["status"] != STATUS_CO_PRESENT:
                continue
            clusters[(screen, text)].append(
                (int(baseline_row["score"] or 0), int(exp_row["score"] or 0))
            )

    return dict(clusters)


def report_pooled(
    indices: dict[str, dict],
    profiles: list[str],
    permutations: int,
    seed: int,
    sample: str = "full",
    b2_targets: frozenset[tuple[str, str]] = frozenset(),
) -> list[dict]:
    """Run and print the pooled cluster permutation test for each profile."""
    print("\n" + "=" * 78)
    print(f"  SECTION 2 -- GROUNDING, POOLED ACROSS MODELS  [PRIMARY TEST]  [sample={sample}]")
    print(f"  Cluster permutation, {permutations} draws, resampling unit = target.")
    print("  Co-present targets only. A target's outcomes across all models are")
    print("  relabelled together, preserving the correlation from target reuse.")
    print("=" * 78)

    raw = {}
    rows = []
    for profile in profiles:
        clusters = build_clusters(indices, profile, sample, b2_targets)
        result = cluster_permutation_test(clusters, permutations, seed)
        raw[profile] = result["p_value"]
        rows.append({"sample": sample, "profile": profile, **result})

    corrected = holm_bonferroni(raw, ALPHA)

    print(f"  {'Profile':<28}{'targets':>8}{'obs':>7}{'b':>6}{'c':>6}"
          f"{'p':>10}{'Holm':>9}   verdict")
    print(f"  {'-' * 28}{'-' * 8:>8}{'-' * 7:>7}{'-' * 6:>6}{'-' * 6:>6}"
          f"{'-' * 10:>10}{'-' * 9:>9}   {'-' * 22}")

    for row in rows:
        holm = corrected[row["profile"]]
        direction = "down" if row["b"] > row["c"] else ("up" if row["c"] > row["b"] else "flat")
        if holm.reject:
            verdict = f"SIGNIFICANT ({direction})"
        elif row["p_value"] < ALPHA:
            verdict = f"sig uncorrected ({direction})"
        else:
            verdict = "ns"
        row["holm_threshold"] = holm.threshold
        row["significant"] = holm.reject
        print(f"  {row['profile']:<28}{row['n_clusters']:>8}"
              f"{row['n_observations']:>7}{row['b']:>6}{row['c']:>6}"
              f"{row['p_value']:>10.5f}{holm.threshold:>9.5f}   {verdict}")

    return rows


# ---------------------------------------------------------------------------
# Section 3: per-model McNemar (secondary)
# ---------------------------------------------------------------------------

def compute_contingency(
    index: dict,
    profile: str,
    sample: str = "full",
    b2_targets: frozenset[tuple[str, str]] = frozenset(),
) -> tuple[int, int, int, int]:
    """Build the 2x2 contingency table for baseline vs one profile.

    Returns (a, b, c, d): a both pass, b broke it, c fluke recovery, d both
    fail. Restricted to co_present rows in both arms, so off-screen targets
    and API failures never enter the table; `sample`/`b2_targets`
    additionally drop targets excluded for this profile (see
    target_excluded_for_condition).
    """
    a = b = c = d = 0

    for (screen, text, prof), baseline_row in index.items():
        if prof != "baseline" or baseline_row["status"] != STATUS_CO_PRESENT:
            continue
        if target_excluded_for_condition(sample, screen, text, profile, b2_targets):
            continue
        exp_row = index.get((screen, text, profile))
        if exp_row is None or exp_row["status"] != STATUS_CO_PRESENT:
            continue

        baseline_score = int(baseline_row["score"] or 0)
        exp_score = int(exp_row["score"] or 0)

        if baseline_score == 1 and exp_score == 1:
            a += 1
        elif baseline_score == 1:
            b += 1
        elif exp_score == 1:
            c += 1
        else:
            d += 1

    return a, b, c, d


def power_flag(base_acc: float) -> str:
    """Classify a comparison's ability to detect degradation at all."""
    if base_acc < FLOOR_ACC_THRESHOLD:
        return "floor"
    if base_acc > CEILING_ACC_THRESHOLD:
        return "ceiling"
    return ""


def report_per_model(
    indices: dict[str, dict],
    profiles: list[str],
    sample: str = "full",
    b2_targets: frozenset[tuple[str, str]] = frozenset(),
) -> list[dict]:
    """Run per-model McNemar with Holm correction across the whole family."""
    print("\n" + "=" * 78)
    print(f"  SECTION 3 -- GROUNDING, PER MODEL  [SECONDARY]  [sample={sample}]")
    print(f"  McNemar on co-present targets. Holm-Bonferroni across all "
          f"{len(indices) * len(profiles)} tests.")
    print("=" * 78)

    rows = []
    raw = {}
    for model, index in indices.items():
        for profile in profiles:
            a, b, c, d = compute_contingency(index, profile, sample, b2_targets)
            total = a + b + c + d
            result = mcnemar_test(b, c)
            base_acc = (a + b) / total * 100 if total else 0.0
            exp_acc = (a + c) / total * 100 if total else 0.0
            diff, diff_low, diff_high = paired_difference_interval(a, b, c, d)
            odds, odds_low, odds_high = conditional_odds_ratio(b, c)

            key = f"{model}|{profile}"
            raw[key] = result["p_value"]
            rows.append({
                "sample": sample, "model": model, "profile": profile, "key": key,
                "a": a, "b": b, "c": c, "d": d, "total": total,
                "base_acc": base_acc, "exp_acc": exp_acc,
                "test": result["test"], "statistic": result["statistic"],
                "p_value": result["p_value"],
                "diff": diff, "diff_low": diff_low, "diff_high": diff_high,
                "odds": odds, "odds_low": odds_low, "odds_high": odds_high,
                "power": power_flag(base_acc),
            })

    corrected = holm_bonferroni(raw, ALPHA)

    header = (f"  {'Model':<24}{'Profile':<26}{'n':>5}{'base':>7}{'exp':>7}"
              f"{'b':>4}{'c':>4}{'p':>10}{'Holm':>9}  power    verdict")
    print(header)
    print("  " + "-" * (len(header) - 2))

    for row in rows:
        holm = corrected[row["key"]]
        row["holm_threshold"] = holm.threshold
        row["significant"] = holm.reject

        if holm.reject:
            verdict = "SIGNIFICANT"
        elif row["p_value"] < ALPHA:
            verdict = "sig uncorrected"
        elif row["power"]:
            verdict = f"inconclusive ({row['power']})"
        else:
            verdict = "ns"

        print(f"  {row['model']:<24}{row['profile']:<26}{row['total']:>5}"
              f"{row['base_acc']:>6.1f}%{row['exp_acc']:>6.1f}%"
              f"{row['b']:>4}{row['c']:>4}{row['p_value']:>10.5f}"
              f"{holm.threshold:>9.5f}  {row['power'] or '-':<8} {verdict}")

    if any(r["power"] == "ceiling" for r in rows):
        print(f"\n  NOTE  'ceiling' marks baseline accuracy > {CEILING_ACC_THRESHOLD:.0f}%,")
        print("        where almost nothing remains to break. Those nulls are")
        print("        underpowered, NOT evidence of resilience.")
    if any(r["power"] == "floor" for r in rows):
        print(f"\n  NOTE  'floor' marks baseline accuracy < {FLOOR_ACC_THRESHOLD:.0f}%,")
        print("        where most targets already fail before any distortion.")

    return rows


# ---------------------------------------------------------------------------
# Section 4: sign test across models
# ---------------------------------------------------------------------------

def report_sign_test(
    per_model_rows: list[dict],
    profiles: list[str],
    sample: str = "full",
) -> list[dict]:
    """Check that a pooled effect is consistent across models, not driven by one."""
    print("\n" + "=" * 78)
    print(f"  SECTION 4 -- DIRECTION CONSISTENCY ACROSS MODELS  [DESCRIPTIVE]  [sample={sample}]")
    print("  Models are not a random sample of a population, so this corroborates")
    print("  the pooled result rather than testing an independent hypothesis.")
    print("=" * 78)
    print(f"  {'Profile':<28}{'down':>6}{'up':>5}{'tied':>6}{'sign p':>10}")
    print(f"  {'-' * 28}{'-' * 6:>6}{'-' * 5:>5}{'-' * 6:>6}{'-' * 10:>10}")

    table = []
    for profile in profiles:
        rows = [r for r in per_model_rows if r["profile"] == profile]
        down = sum(1 for r in rows if r["b"] > r["c"])
        up = sum(1 for r in rows if r["c"] > r["b"])
        tied = sum(1 for r in rows if r["b"] == r["c"])
        p_value = sign_test(down, up)
        print(f"  {profile:<28}{down:>6}{up:>5}{tied:>6}{p_value:>10.5f}")
        table.append({
            "sample": sample, "profile": profile, "down": down, "up": up,
            "tied": tied, "p_value": p_value,
        })
    return table


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------

def _fmt(value, spec: str = ".6f") -> str:
    """Format a float for CSV, leaving None and infinities readable."""
    if value is None:
        return ""
    if isinstance(value, float) and value == float("inf"):
        return "inf"
    return format(value, spec) if isinstance(value, float) else str(value)


def write_outputs(
    data_dir: Path,
    reachability: list[dict],
    pooled: list[dict],
    per_model: list[dict],
    signs: list[dict],
    label_changed: list[dict] | None = None,
) -> None:
    """Write the result tables to CSV."""
    data_dir.mkdir(parents=True, exist_ok=True)

    reach_path = data_dir / "reachability_results.csv"
    with open(reach_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Sample", "Profile", "Targets_Present", "Targets_Total",
                    "Reachability", "CI_Low", "CI_High"])
        for r in reachability:
            w.writerow([r["sample"], r["profile"], r["present"], r["total"],
                        _fmt(r["rate"], ".4f"), _fmt(r["ci_low"], ".4f"),
                        _fmt(r["ci_high"], ".4f")])

    pooled_path = data_dir / "pooled_permutation_results.csv"
    with open(pooled_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Sample", "Profile", "Target_Clusters", "Observations", "Statistic",
                    "Broke_It_b", "Fluke_Recovery_c", "Permutations",
                    "P_Value", "Holm_Threshold", "Significant"])
        for r in pooled:
            w.writerow([r["sample"], r["profile"], r["n_clusters"], r["n_observations"],
                        _fmt(r["statistic"], ".1f"), r["b"], r["c"],
                        r["n_permutations"], _fmt(r["p_value"]),
                        _fmt(r["holm_threshold"]),
                        "Yes" if r["significant"] else "No"])

    per_model_path = data_dir / "mcnemar_results_per_model.csv"
    with open(per_model_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Sample", "Model", "Profile", "Total_Pairs", "Both_Pass_a", "Broke_It_b",
                    "Fluke_Recovery_c", "Both_Fail_d", "Discordant_Pairs",
                    "Baseline_Acc", "Exp_Acc", "Risk_Diff", "Risk_Diff_CI_Low",
                    "Risk_Diff_CI_High", "Odds_Ratio", "OR_CI_Low", "OR_CI_High",
                    "Test_Used", "Statistic", "P_Value", "Holm_Threshold",
                    "Significant", "Power_Limit"])
        for r in per_model:
            w.writerow([
                r["sample"], r["model"], r["profile"], r["total"], r["a"], r["b"], r["c"], r["d"],
                r["b"] + r["c"], f"{r['base_acc']:.1f}%", f"{r['exp_acc']:.1f}%",
                _fmt(r["diff"], ".4f"), _fmt(r["diff_low"], ".4f"),
                _fmt(r["diff_high"], ".4f"), _fmt(r["odds"], ".3f"),
                _fmt(r["odds_low"], ".3f"), _fmt(r["odds_high"], ".3f"),
                r["test"], _fmt(r["statistic"], ".4f"), _fmt(r["p_value"]),
                _fmt(r["holm_threshold"]),
                "Yes" if r["significant"] else "No", r["power"] or "none",
            ])

    sign_path = data_dir / "direction_consistency.csv"
    with open(sign_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Sample", "Profile", "Models_Down", "Models_Up", "Models_Tied", "Sign_P_Value"])
        for r in signs:
            w.writerow([r["sample"], r["profile"], r["down"], r["up"], r["tied"], _fmt(r["p_value"])])

    written = [reach_path, pooled_path, per_model_path, sign_path]

    if label_changed:
        label_changed_path = data_dir / "label_changed_breakdown.csv"
        with open(label_changed_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Screen", "Profile", "Baseline_Text", "Matched_Text"])
            for r in label_changed:
                w.writerow([r["screen"], r["profile"], r["baseline_text"],
                            r["matched_text"]])
        written.append(label_changed_path)

    print("\n[WROTE]")
    for path in written:
        print(f"  {path}")


# ---------------------------------------------------------------------------
# Cross-file comparison (vision-only vs tree-injected)
# ---------------------------------------------------------------------------

def run_cross_comparison(
    csv_a: Path,
    csv_b: Path,
    profiles: list[str],
    sample: str = DEFAULT_SAMPLE,
    data_dir: Path | None = None,
) -> None:
    """Compare two evaluation runs of the same profiles, target by target.

    Applies the same corrections as the main analysis path, which it used to
    skip entirely: both reclassification passes (A1 label_changed, A2
    off_frame) and the Stage B sample exclusions. Without them the headline
    vision-vs-tree number would be computed on the uncorrected `full` sample
    -- scoring the 2 unscoreable out-of-frame targets as misses and including
    the 7 degenerate Gmail targets -- while every other table in the repo
    reports `primary`.
    """
    print("=" * 78)
    print("  CROSS-FILE COMPARISON")
    print(f"  A (vision-only): {csv_a.name}")
    print(f"  B (with tree):   {csv_b.name}")
    print(f"  Sample         : {sample}")
    print("=" * 78)

    index_a = index_rows(load_results(csv_a))
    index_b = index_rows(load_results(csv_b))

    if data_dir is None:
        data_dir = csv_a.parent
    for index in (index_a, index_b):
        reclassify_label_changed(list(index.values()), data_dir / "labels")
        reclassify_off_frame(list(index.values()), data_dir / "images")

    baseline_rows = [row for (_s, _t, prof), row in index_a.items() if prof == "baseline"]
    b2_targets = compute_b2_targets(baseline_rows)

    out_path = csv_a.parent / f"mcnemar_compare_{csv_a.stem.replace('evaluation_results_', '')}.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Sample", "Profile", "Total_Pairs", "Both_Pass_a", "Tree_Hurt_b",
                    "Tree_Helped_c", "Both_Fail_d", "Discordant_Pairs",
                    "VisionOnly_Acc", "WithTree_Acc", "Test_Used", "Statistic",
                    "P_Value", "Significant"])

        print(f"\n  {'Profile':<28}{'n':>5}{'A acc':>8}{'B acc':>8}"
              f"{'b':>4}{'c':>4}{'p':>10}  verdict")
        print(f"  {'-' * 28}{'-' * 5:>5}{'-' * 8:>8}{'-' * 8:>8}"
              f"{'-' * 4:>4}{'-' * 4:>4}{'-' * 10:>10}  {'-' * 12}")

        for profile in profiles:
            a = b = c = d = 0
            for key, row_a in index_a.items():
                screen, text, prof = key
                if prof != profile or row_a["status"] != STATUS_CO_PRESENT:
                    continue
                if target_excluded_for_condition(sample, screen, text, profile, b2_targets):
                    continue
                row_b = index_b.get(key)
                if row_b is None or row_b["status"] != STATUS_CO_PRESENT:
                    continue
                score_a = int(row_a["score"] or 0)
                score_b = int(row_b["score"] or 0)
                if score_a == 1 and score_b == 1:
                    a += 1
                elif score_a == 1:
                    b += 1
                elif score_b == 1:
                    c += 1
                else:
                    d += 1

            total = a + b + c + d
            result = mcnemar_test(b, c)
            acc_a = (a + b) / total * 100 if total else 0.0
            acc_b = (a + c) / total * 100 if total else 0.0
            verdict = "SIGNIFICANT" if result["p_value"] < ALPHA else "ns"

            print(f"  {profile:<28}{total:>5}{acc_a:>7.1f}%{acc_b:>7.1f}%"
                  f"{b:>4}{c:>4}{result['p_value']:>10.5f}  {verdict}")

            w.writerow([sample, profile, total, a, b, c, d, b + c,
                        f"{acc_a:.1f}%", f"{acc_b:.1f}%", result["test"],
                        _fmt(result["statistic"], ".4f"),
                        _fmt(result["p_value"]),
                        "Yes" if result["p_value"] < ALPHA else "No"])

    print(f"\n[WROTE] {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="AccessGroundBench -- statistical analysis"
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR,
                        help="Directory holding evaluation_results_*.csv")
    parser.add_argument("--csv", type=Path, default=None,
                        help="Analyse a single evaluation CSV")
    parser.add_argument("--permutations", type=int, default=DEFAULT_PERMUTATIONS,
                        help="Permutation draws for the pooled test")
    parser.add_argument("--seed", type=int, default=0,
                        help="RNG seed for the permutation test")
    parser.add_argument("--compare-a", type=Path, default=None)
    parser.add_argument("--compare-b", type=Path, default=None)
    parser.add_argument("--label-changed", choices=LABEL_CHANGED_MODES,
                        default=DEFAULT_LABEL_CHANGED_MODE,
                        help="How to count targets whose element is still on "
                             "screen but whose label text changed under "
                             "reflow (see STATUS_LABEL_CHANGED). Affects "
                             "reachability only -- these targets are never "
                             "queried, so they never enter the scored "
                             "McNemar/permutation tables regardless of this "
                             f"flag. Default: {DEFAULT_LABEL_CHANGED_MODE!r} "
                             "(matches pre-reclassification behaviour).")
    parser.add_argument("--mode", choices=["vision", "tree"], default="vision",
                        help="Which prompt-mode arm to analyse when discovering "
                             "CSVs from --data-dir (default: vision). Vision and "
                             "tree results for the same model are correlated, not "
                             "independent measurements, so they are never pooled "
                             "together automatically -- use --compare-a/--compare-b "
                             "for a paired vision-vs-tree comparison instead.")
    parser.add_argument("--sample", choices=[*SAMPLE_NAMES, "all"], default="all",
                        help="Which exclusion set(s) to report. 'full' is "
                             "no exclusions; 'primary' is the recommended sample "
                             "(B1-minimal + B2); 'precautionary' and 'uniform' "
                             "are sensitivity variants. Default 'all' runs every "
                             "sample and writes them side by side in one set of "
                             "output CSVs, distinguished by a Sample column -- "
                             "restricted numbers never replace the unrestricted "
                             "ones.")
    args = parser.parse_args()

    profiles = list(EXPERIMENTAL_PROFILES)

    if bool(args.compare_a) != bool(args.compare_b):
        print("[ERROR] --compare-a and --compare-b must be given together.")
        sys.exit(1)

    if args.compare_a and args.compare_b:
        # "all" is meaningful for the main path (it writes one row per sample
        # into shared output files) but not here, where each run produces a
        # single comparison table; fall back to the recommended sample.
        sample = DEFAULT_SAMPLE if args.sample == "all" else args.sample
        run_cross_comparison(
            args.compare_a, args.compare_b, profiles, sample, args.data_dir
        )
        return

    if args.csv:
        csv_files = [args.csv]
        data_dir = args.csv.parent
    else:
        data_dir = args.data_dir
        csv_files = discover_result_csvs(data_dir, args.mode)
        if not csv_files:
            print(f"[ERROR] No evaluation_results_*.csv files for mode={args.mode!r} "
                  f"found in {data_dir}")
            sys.exit(1)

    print("=" * 78)
    print("  AccessGroundBench -- Statistical Analysis")
    print(f"  Data dir : {data_dir}")
    print(f"  Mode     : {args.mode}")
    print(f"  Models   : {len(csv_files)}")
    for path in csv_files:
        print(f"             {path.name}")
    print(f"  Profiles : {', '.join(profiles)}")
    print(f"  alpha    : {ALPHA} (Holm-Bonferroni corrected)")
    print("=" * 78)

    indices = {
        model_name_from_path(path): index_rows(load_results(path))
        for path in csv_files
    }

    # Reachability depends only on the captures, so any one model's rows show it.
    first_index = next(iter(indices.values()))

    # A profile can be in EXPERIMENTAL_PROFILES but absent from this specific
    # dataset -- e.g. an archived run predating a profile rename, or a
    # --screens subset. Without this filter every section below would print a
    # spurious present=0/total=0 "0.0%" row for it, which reads as "measured
    # and found unreachable" rather than "never captured here".
    available_profiles = {prof for (_screen, _text, prof) in first_index}
    missing_profiles = [p for p in profiles if p not in available_profiles]
    profiles = [p for p in profiles if p in available_profiles]
    if missing_profiles:
        print(f"  Skipped  : {', '.join(missing_profiles)} "
              f"(no captures for this profile in {data_dir})")

    reclassify_label_changed(list(first_index.values()), data_dir / "labels")

    # Off-frame reclassification must depend on each model's own rows: a box
    # is a property of the (screen, profile) capture, identical across
    # models, but the stored x_min..y_max only exists on rows that were
    # actually queried -- so every model's index needs the same check, not
    # just first_index (unlike label_changed, which only feeds the
    # model-independent reachability/breakdown reports).
    for index in indices.values():
        reclassify_off_frame(list(index.values()), data_dir / "images")

    label_changed_breakdown = report_label_changed_breakdown(first_index, profiles)

    # B2's target set is computed once from this run's own baseline rows (not
    # hardcoded), so it reproduces correctly against any dataset -- see
    # compute_b2_targets. Baseline is identical across models, so first_index
    # is representative.
    baseline_rows = [row for (_s, _t, prof), row in first_index.items() if prof == "baseline"]
    b2_targets = compute_b2_targets(baseline_rows)

    samples_to_run = SAMPLE_NAMES if args.sample == "all" else [args.sample]

    reachability_all: list[dict] = []
    pooled_all: list[dict] = []
    per_model_all: list[dict] = []
    signs_all: list[dict] = []

    for sample in samples_to_run:
        reachability_all += report_reachability(
            first_index, profiles, args.label_changed, sample, b2_targets
        )
        pooled = report_pooled(
            indices, profiles, args.permutations, args.seed, sample, b2_targets
        )
        per_model = report_per_model(indices, profiles, sample, b2_targets)
        signs = report_sign_test(per_model, profiles, sample)
        pooled_all += pooled
        per_model_all += per_model
        signs_all += signs

    if len(samples_to_run) > 1:
        print("\n" + "=" * 78)
        print("  SAMPLE SIZES  (paired observations, summed across profiles)")
        print("=" * 78)
        print(f"  {'Sample':<16}{'obs (all models)':>18}{'obs/model':>12}")
        n_models = len(indices)
        for sample in samples_to_run:
            total_obs = sum(r["n_observations"] for r in pooled_all if r["sample"] == sample)
            print(f"  {sample:<16}{total_obs:>18}{total_obs / n_models:>12.0f}")

    write_outputs(data_dir, reachability_all, pooled_all, per_model_all, signs_all,
                  label_changed_breakdown)
    print()


if __name__ == "__main__":
    main()
