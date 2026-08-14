"""Offline result maintenance for evaluation CSV files.

Canonicalization reduces evaluation_results_*.csv files to exactly one row
per (screen, target_text, profile) key, matching the current harvested
target set.

This is the same canonicalization evaluation.workflow now runs automatically on
every resumed run (see evaluation.storage.results.prepare_csv/finalize_csv); this
script exists to repair files collected before that existed, or to recover
if a future run somehow still produces duplicates (e.g. the .lock file was
deleted mid-run).

Zero API calls are made -- every expected key already present in these files
already has at least one real measurement, so this is pure deletion of
stale-target, api_error, and duplicate rows, plus a canonical sort. A
timestamped copy of each file is kept under .backups/ before rewriting
(src/backups.py; gitignored).

"""

import argparse
import csv
import sys
from pathlib import Path

import os

import paths

from ..config import ALL_PROFILES, COORD_SPACES
from backups import preserve
from paths import evaluations_dir
from .results import (
    CSV_COLUMNS,
    PROMPT_MODE_TREE,
    PROMPT_MODE_VISION,
    CsvLockError,
    acquire_lock,
    finalize_csv,
    prepare_csv,
    release_lock,
)
from ..grounding.targets import build_expected_keys
from ..grounding.scoring import get_png_dimensions, hit_test, parse_coordinates, to_pixel_space

WITH_TREE_SUFFIX = "_with_tree"


def _add_data_dir_argument(parser: argparse.ArgumentParser) -> None:
    """Declare --data-dir on a maintenance parser.

    These commands own their own parsers rather than going through
    evaluation.cli, so the flag is declared here: adding it to the thin wrapper
    and stripping it would make argparse reject an unknown flag.
    """
    parser.add_argument(
        "--data-dir", type=Path, default=None,
        help=f"Dataset directory to operate on (or set ${paths.DATASET_DIR_ENV_VAR})",
    )


def _require_data_dir(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Publish --data-dir through the environment, or fail with usage.

    Set rather than returned because every path helper reads the environment, so
    one assignment reaches the whole call tree without threading an argument
    through functions that only ever operate on the active dataset.
    """
    if args.data_dir is not None:
        os.environ[paths.DATASET_DIR_ENV_VAR] = str(args.data_dir.expanduser().resolve())
    elif not os.environ.get(paths.DATASET_DIR_ENV_VAR, "").strip():
        parser.error(
            f"--data-dir is required (or set ${paths.DATASET_DIR_ENV_VAR}). "
            "There is no default dataset."
        )


def discover_screens() -> list[str]:
    """Auto-discover screen names from baseline label files."""
    labels_dir = paths.labels_dir()
    if not labels_dir.is_dir():
        return []
    return sorted(
        f.stem.replace("_baseline", "") for f in labels_dir.glob("*_baseline.json")
    )


def canonicalize_one(results_csv: Path, expected_key_order: list[tuple[str, str, str]]) -> list[str]:
    """Canonicalize and finalize a single CSV; returns any problems found."""
    # Current files end in `_tree`; pre-reorganization ones in `_with_tree`.
    is_tree = results_csv.stem.endswith(("_tree", WITH_TREE_SUFFIX))
    expected_prompt_mode = PROMPT_MODE_TREE if is_tree else PROMPT_MODE_VISION
    try:
        acquire_lock(results_csv)
    except CsvLockError as e:
        return [str(e)]

    try:
        prepare_csv(
            results_csv,
            fresh=False,
            expected_prompt_mode=expected_prompt_mode,
            expected_keys=set(expected_key_order),
        )
        return finalize_csv(results_csv, expected_key_order)
    finally:
        release_lock(results_csv)


def canonicalize_main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Canonicalize organized evaluation result files")
    parser.add_argument(
        "--csv", nargs="+", type=Path, default=None,
        help="Specific CSV path(s) to canonicalize (default: all organized outputs)",
    )
    _add_data_dir_argument(parser)
    args = parser.parse_args(argv)
    _require_data_dir(parser, args)

    screens = discover_screens()
    if not screens:
        print(f"[ERROR] No screens found under {paths.labels_dir()}.")
        sys.exit(1)

    expected_key_order = build_expected_keys(screens, paths.labels_dir(), ALL_PROFILES)
    print(f"Canonical key count: {len(expected_key_order)} "
          f"({len(screens)} screens x {len(ALL_PROFILES)} profiles)")

    evaluations_root = evaluations_dir()
    csv_files = args.csv or sorted(evaluations_root.glob("*.csv"))
    if not csv_files:
        print(f"[ERROR] No evaluation result files found in {evaluations_root}")
        sys.exit(1)

    all_problems: list[str] = []
    for results_csv in csv_files:
        print(f"\n--- {results_csv.name} ---")
        problems = canonicalize_one(results_csv, expected_key_order)
        all_problems.extend(problems)

    print("\n" + "=" * 60)
    if all_problems:
        print(f"{len(all_problems)} PROBLEM(S):")
        for problem in all_problems:
            print(f"  - {problem}")
        sys.exit(1)
    print(f"All {len(csv_files)} file(s) canonical: {len(expected_key_order)} rows each.")


def _dimensions_for(screen: str, profile: str) -> tuple[int, int] | None:
    image_path = paths.images_dir() / f"{screen}_{profile}.png"
    if not image_path.is_file():
        return None
    try:
        return get_png_dimensions(image_path)
    except Exception:
        return None


def _baseline_boxes(rows: list[dict]) -> dict[tuple[str, str], list[int]]:
    boxes = {}
    for row in rows:
        if row.get("profile") != "baseline":
            continue
        try:
            box = [int(float(row[key])) for key in ("x_min", "y_min", "x_max", "y_max")]
        except (ValueError, KeyError):
            continue
        boxes[(row["screen"], row["target_text"])] = box
    return boxes


def _row_image_scale(row: dict, img_width: int, img_height: int) -> float:
    """Recover the scale a row's screenshot was sent at, from the row itself.

    Self-describing rather than recomputed from the model id: if a provider
    later moves its cap and MAX_IMAGE_EDGE is updated, recomputing would
    rescale an old row by the new factor and silently move every prediction.
    """
    sent = (row.get("image_sent_size") or "").strip().lower()
    if "x" not in sent:
        return 1.0
    try:
        sent_w, sent_h = (int(part) for part in sent.split("x", 1))
    except ValueError:
        return 1.0
    return max(sent_w, sent_h) / max(img_width, img_height)


def rescore(rows: list[dict], coord_space: str) -> tuple[list[dict], int, int]:
    """Re-score every eligible row under a coordinate convention.

    Delegates to the runner's score_one_trial rather than reimplementing the
    parse, conversion, bounds check, and hit test. The duplicate that lived
    here drifted: it never learned about downscaled screenshots, so rescoring
    a capped model would have read its sent-space replies as full-size
    coordinates and moved every prediction.
    """
    from ..runner import score_one_trial

    baselines = _baseline_boxes(rows)
    scored = hits = 0
    for row in rows:
        dims = _dimensions_for(row.get("screen", ""), row.get("profile", ""))
        try:
            box = [int(float(row[key])) for key in ("x_min", "y_min", "x_max", "y_max")]
        except (ValueError, KeyError):
            box = None
        if dims is None or box is None:
            continue

        img_width, img_height = dims
        x_pred, y_pred, score, parse_method = score_one_trial(
            row.get("raw_response", ""),
            box,
            baselines.get((row["screen"], row["target_text"])),
            img_width,
            img_height,
            coord_space=coord_space,
            image_scale=_row_image_scale(row, img_width, img_height),
        )
        row["x_pred"], row["y_pred"], row["score"] = x_pred, y_pred, score
        row["parse_method"] = parse_method
        scored += 1
        hits += score
    return rows, scored, hits


def rescore_main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Re-score an evaluation CSV under a different coordinate convention"
    )
    parser.add_argument("--csv", type=Path, required=True, help="evaluation_results_*.csv to rescore")
    parser.add_argument("--coord-space", choices=COORD_SPACES)
    parser.add_argument("--check", action="store_true")
    _add_data_dir_argument(parser)
    args = parser.parse_args(argv)
    # Needed because rescoring re-runs hit-testing against the captured PNGs,
    # whose dimensions come from the dataset -- see _dimensions_for.
    _require_data_dir(parser, args)

    if not args.csv.is_file():
        print(f"[ERROR] CSV not found: {args.csv}")
        raise SystemExit(1)
    if not args.check and not args.coord_space:
        print("[ERROR] --coord-space is required unless --check is passed.")
        raise SystemExit(1)

    with open(args.csv, newline="", encoding="utf-8") as handle:
        original = list(csv.DictReader(handle))
    if not original:
        print(f"[ERROR] No rows in {args.csv}")
        raise SystemExit(1)

    if args.check:
        print(f"  {args.csv.name}")
        print(f"  {'convention':<12} {'scored':>7} {'hits':>6} {'accuracy':>9}")
        print(f"  {'-' * 12} {'-' * 7} {'-' * 6} {'-' * 9}")
        for space in COORD_SPACES:
            _, scored, hits = rescore([dict(row) for row in original], space)
            accuracy = f"{hits / scored * 100:.1f}%" if scored else "n/a"
            print(f"  {space:<12} {scored:>7} {hits:>6} {accuracy:>9}")
        print("\n  The convention with materially higher accuracy is the one the")
        print("  model answers in. Rerun with --coord-space to apply it.")
        return

    rows, scored, hits = rescore(original, args.coord_space)
    backup = preserve(args.csv, reason="rescoring rewrites every score")
    with open(args.csv, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for row in rows:
            writer.writerow([row.get(column, "") for column in CSV_COLUMNS])
    accuracy = f"{hits / scored * 100:.1f}%" if scored else "n/a"
    print(f"  Rescored {args.csv.name} as {args.coord_space}")
    print(f"  Backup:   {backup.name if backup else 'none'}")
    print(f"  Scored:   {scored} rows, {hits} hits ({accuracy})")
    print(f"\n  Now rerun: agb analyze --csv {args.csv}")


if __name__ == "__main__":
    canonicalize_main()
