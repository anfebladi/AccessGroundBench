"""
canonicalize_results.py
------------------------
Maintenance tool: reduce evaluation_results_*.csv files to exactly one row
per (screen, target_text, profile) key, matching the current harvested
target set.

This is the same canonicalization vlm_evaluator.py now runs automatically on
every resumed run (see vlm_eval.results.prepare_csv/finalize_csv); this
script exists to repair files collected before that existed, or to recover
if a future run somehow still produces duplicates (e.g. the .lock file was
deleted mid-run).

Zero API calls are made -- every expected key already present in these files
already has at least one real measurement, so this is pure deletion of
stale-target, api_error, and duplicate rows, plus a canonical sort. A .bak
copy of each file is kept before rewriting (see .gitignore).

Usage:
  python canonicalize_results.py                 # all evaluation_results_*.csv in dataset/
  python canonicalize_results.py --csv path1.csv path2.csv
"""

import argparse
import sys
from pathlib import Path

from vlm_eval.config import ALL_PROFILES, DATASET_DIR, LABELS_DIR
from vlm_eval.results import (
    PROMPT_MODE_TREE,
    PROMPT_MODE_VISION,
    CsvLockError,
    acquire_lock,
    finalize_csv,
    prepare_csv,
    release_lock,
)
from vlm_eval.targets import build_expected_keys

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


def main(argv: list[str] | None = None) -> None:
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


if __name__ == "__main__":
    main()
