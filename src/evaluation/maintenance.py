"""Offline result maintenance for evaluation CSV files.

Canonicalization reduces evaluation_results_*.csv files to exactly one row
per (screen, target_text, profile) key, matching the current harvested
target set.

This is the same canonicalization evaluation.workflow now runs automatically on
every resumed run (see evaluation.results.prepare_csv/finalize_csv); this
script exists to repair files collected before that existed, or to recover
if a future run somehow still produces duplicates (e.g. the .lock file was
deleted mid-run).

Zero API calls are made -- every expected key already present in these files
already has at least one real measurement, so this is pure deletion of
stale-target, api_error, and duplicate rows, plus a canonical sort. A .bak
copy of each file is kept before rewriting (see .gitignore).

"""

import argparse
import csv
import shutil
import sys
from pathlib import Path

from .config import ALL_PROFILES, COORD_SPACES, DATASET_DIR, IMAGES_DIR, LABELS_DIR
from .results import (
    PROMPT_MODE_TREE,
    PROMPT_MODE_VISION,
    CsvLockError,
    acquire_lock,
    finalize_csv,
    prepare_csv,
    release_lock,
)
from .targets import build_expected_keys
from .results import CSV_COLUMNS
from .scoring import get_png_dimensions, hit_test, parse_coordinates, to_pixel_space

WITH_TREE_SUFFIX = "_with_tree"


def discover_screens() -> list[str]:
    """Auto-discover screen names from baseline label files."""
    if not LABELS_DIR.is_dir():
        return []
    return sorted(
        f.stem.replace("_baseline", "") for f in LABELS_DIR.glob("*_baseline.json")
    )


def canonicalize_one(results_csv: Path, expected_key_order: list[tuple[str, str, str]]) -> list[str]:
    """Canonicalize and finalize a single CSV; returns any problems found."""
    expected_prompt_mode = (
        PROMPT_MODE_TREE if results_csv.stem.endswith(WITH_TREE_SUFFIX) else PROMPT_MODE_VISION
    )
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
    parser = argparse.ArgumentParser(description="Canonicalize evaluation_results_*.csv files")
    parser.add_argument(
        "--csv", nargs="+", type=Path, default=None,
        help="Specific CSV path(s) to canonicalize (default: all evaluation_results_*.csv in dataset/)",
    )
    args = parser.parse_args(argv)

    screens = discover_screens()
    if not screens:
        print("[ERROR] No screens found under dataset/labels/.")
        sys.exit(1)

    expected_key_order = build_expected_keys(screens, LABELS_DIR, ALL_PROFILES)
    print(f"Canonical key count: {len(expected_key_order)} "
          f"({len(screens)} screens x {len(ALL_PROFILES)} profiles)")

    csv_files = args.csv or sorted(DATASET_DIR.glob("evaluation_results_*.csv"))
    if not csv_files:
        print(f"[ERROR] No evaluation_results_*.csv files found in {DATASET_DIR}")
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
    image_path = IMAGES_DIR / f"{screen}_{profile}.png"
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


def rescore(rows: list[dict], coord_space: str) -> tuple[list[dict], int, int]:
    """Re-score every eligible row under a coordinate convention."""
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
        x_raw, y_raw = parse_coordinates(row.get("raw_response", ""))
        x_coord, y_coord = to_pixel_space(
            x_raw, y_raw, img_width, img_height, coord_space
        )
        if x_coord < 0 or y_coord < 0 or x_coord > img_width or y_coord > img_height:
            x_pred, y_pred, score = -1, -1, 0
        else:
            x_pred, y_pred = int(x_coord), int(y_coord)
            score = hit_test(
                x_pred,
                y_pred,
                box,
                baselines.get((row["screen"], row["target_text"])),
            )
        row["x_pred"], row["y_pred"], row["score"] = x_pred, y_pred, score
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
    args = parser.parse_args(argv)

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
    backup = args.csv.with_suffix(".csv.bak")
    shutil.copy2(args.csv, backup)
    with open(args.csv, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for row in rows:
            writer.writerow([row.get(column, "") for column in CSV_COLUMNS])
    accuracy = f"{hits / scored * 100:.1f}%" if scored else "n/a"
    print(f"  Rescored {args.csv.name} as {args.coord_space}")
    print(f"  Backup:   {backup.name}")
    print(f"  Scored:   {scored} rows, {hits} hits ({accuracy})")
    print(f"\n  Now rerun: agb analyze --csv {args.csv}")


if __name__ == "__main__":
    canonicalize_main()
