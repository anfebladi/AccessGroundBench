"""Evaluation-result discovery, loading, indexing, and reclassification."""
from __future__ import annotations
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from evaluation.storage.results import (
    PROMPT_MODE_VISION,
    STATUS_API_ERROR,
    STATUS_CO_PRESENT,
    STATUS_LABEL_CHANGED,
    STATUS_OFF_FRAME,
    STATUS_OFF_SCREEN,
)
from evaluation.grounding.scoring import get_png_dimensions
from evaluation.grounding.targets import locate_element

WITH_TREE_SUFFIX = "_with_tree"


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
            "should be canonicalized (evaluation.storage.results.canonicalize_rows / "
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
    # A row written STATUS_OFF_SCREEN before evaluation.runner started using
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
