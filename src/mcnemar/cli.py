"""Command-line orchestration for McNemar analyses."""

import argparse
import csv
import sys
from pathlib import Path

from .pairing import (
    build_cross_file_pairs,
    build_pairs,
    compute_contingency,
    compute_cross_contingency,
    load_results,
)
from .reporting import (
    cross_csv_header,
    cross_csv_row,
    format_cross_report,
    format_cross_summary,
    format_report,
    format_standard_summary,
    standard_csv_header,
    standard_csv_row,
)
from .service import EXPERIMENTAL_PROFILES, analyze_profiles, cross_file_profiles
from .statistics import ALPHA, HAS_SCIPY

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUTS_DIR_NAME = "outputs"
EVALUATION_RESULTS_DIR_NAME = "evaluation_results"
MCNEMAR_RESULTS_DIR_NAME = "mcnemar"


def get_evaluation_results_dir(project_root: Path) -> Path:
    """Return the directory containing active VLM evaluation CSVs."""
    return project_root / OUTPUTS_DIR_NAME / EVALUATION_RESULTS_DIR_NAME


def get_mcnemar_results_dir(project_root: Path) -> Path:
    """Return the directory containing active McNemar CSVs."""
    return project_root / OUTPUTS_DIR_NAME / MCNEMAR_RESULTS_DIR_NAME


def discover_evaluation_csvs(project_root: Path) -> list[Path]:
    """Discover active evaluation CSVs without scanning reference datasets."""
    return sorted(
        get_evaluation_results_dir(project_root).glob("evaluation_results_*.csv")
    )


def run_cross_comparison(csv_a: Path, csv_b: Path, project_root: Path) -> None:
    """Run the legacy cross-file McNemar comparison."""
    print(f"\n{'=' * 60}")
    print("  Cross-File Comparison")
    print(f"  File A (Vision-only): {csv_a.name}")
    print(f"  File B (With Tree):   {csv_b.name}")
    print(f"{'=' * 60}")

    pairs = build_cross_file_pairs(load_results(csv_a), load_results(csv_b))
    print(f"[PAIRS] {len(pairs)} unique (screen, target_text) tracking keys")

    profiles_to_compare = cross_file_profiles(pairs)
    if not profiles_to_compare:
        print("[ERROR] No matching experimental profiles found across both files.")
        sys.exit(1)

    stem_a = csv_a.stem.replace("evaluation_results_", "")
    out_csv_path = get_mcnemar_results_dir(project_root) / f"mcnemar_compare_{stem_a}.csv"
    out_csv_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] Writing comparison results to: {out_csv_path}")

    records = analyze_profiles(pairs, profiles_to_compare, compute_cross_contingency)
    with open(out_csv_path, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.writer(out_f)
        writer.writerow(cross_csv_header())
        for record in records:
            print(format_cross_report(record))
            writer.writerow(cross_csv_row(record))

    print(format_cross_summary(records))
    print()


def run_standard_analysis(csv_files: list[Path], project_root: Path) -> None:
    """Run the legacy baseline-versus-profile analysis for each CSV file."""
    results_dir = get_mcnemar_results_dir(project_root)
    results_dir.mkdir(parents=True, exist_ok=True)
    for csv_file in csv_files:
        print(f"\n{'=' * 60}")
        print(f"  Analyzing: {csv_file.name}")
        print(f"{'=' * 60}")

        model_name = csv_file.stem.replace("evaluation_results_", "")
        if model_name == "evaluation_results":
            model_name = "default"

        pairs = build_pairs(load_results(csv_file))
        print(f"[PAIRS] {len(pairs)} unique (screen, target_text) tracking keys")

        out_csv_path = results_dir / f"mcnemar_results_{model_name}.csv"
        print(f"[INFO] Writing statistical results to: {out_csv_path}")

        records = analyze_profiles(pairs, EXPERIMENTAL_PROFILES, compute_contingency)
        with open(out_csv_path, "w", newline="", encoding="utf-8") as out_f:
            writer = csv.writer(out_f)
            writer.writerow(standard_csv_header())
            for record in records:
                print(format_report(record))
                writer.writerow(standard_csv_row(record))

        print(format_standard_summary(model_name, records))


def main(project_root: Path | None = None) -> None:
    """Parse arguments and run the selected legacy analysis mode."""
    project_root = project_root or PROJECT_ROOT
    evaluation_results_dir = get_evaluation_results_dir(project_root)
    default_csv = evaluation_results_dir / "evaluation_results.csv"

    parser = argparse.ArgumentParser(
        description="AccessGroundBench -- McNemar's Statistical Analysis"
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help=(
            "Path to a specific evaluation_results_*.csv file. If omitted, "
            "runs on all files in outputs/evaluation_results/"
        ),
    )
    parser.add_argument(
        "--compare-a",
        type=Path,
        default=None,
        help="Vision-only results CSV for cross-file comparison",
    )
    parser.add_argument(
        "--compare-b",
        type=Path,
        default=None,
        help="Tree-injected results CSV for cross-file comparison",
    )
    args = parser.parse_args()

    if not HAS_SCIPY:
        print("[WARN] scipy not installed. Using fallback calculations.")
        print("       For precise p-values: pip install scipy")
        print()

    if args.compare_a and args.compare_b:
        print("=" * 60)
        print("  AccessGroundBench -- McNemar's Cross-File Comparison")
        print(f"  alpha: {ALPHA}")
        print("=" * 60)
        run_cross_comparison(args.compare_a, args.compare_b, project_root)
        return

    if args.compare_a or args.compare_b:
        print("[ERROR] Both --compare-a and --compare-b are required for cross-file comparison.")
        sys.exit(1)

    print("=" * 60)
    print("  AccessGroundBench -- McNemar's Test Analysis")
    print(f"  alpha: {ALPHA}")
    print("=" * 60)

    if args.csv:
        csv_files = [args.csv]
    else:
        csv_files = discover_evaluation_csvs(project_root)
        if not csv_files:
            if default_csv.is_file():
                csv_files = [default_csv]
            else:
                print(
                    "[ERROR] No evaluation_results_*.csv files found in "
                    f"{evaluation_results_dir}"
                )
                sys.exit(1)

    run_standard_analysis(csv_files, project_root)
    print()


if __name__ == "__main__":
    main(PROJECT_ROOT)
