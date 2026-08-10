"""Command-line adapter for statistical analysis."""
from __future__ import annotations
import argparse
from pathlib import Path

from paths import DATASET_DIR
from .reports.comparison import run_cross_comparison
from .reports.reachability import DEFAULT_LABEL_CHANGED_MODE, LABEL_CHANGED_MODES
from .data.samples import DEFAULT_SAMPLE, SAMPLE_NAMES
from .stats import DEFAULT_PERMUTATIONS
from .workflow import EXPERIMENTAL_PROFILES, run_analysis


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AccessGroundBench -- statistical analysis")
    parser.add_argument("--data-dir", type=Path, default=None,
                        help="Dataset directory to analyse (default: the active dataset)")
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
                        help="How label-changed targets count for reachability")
    parser.add_argument("--mode", choices=["vision", "tree"], default="vision",
                        help="Prompt-mode arm to discover from --data-dir")
    parser.add_argument("--sample", choices=[*SAMPLE_NAMES, "all"], default="all",
                        help="Exclusion sample(s) to report")
    return parser


def resolve_data_dir(data_dir: Path | None, csv_path: Path | None) -> Path:
    """Decide which dataset supplies the labels and images for a run.

    The reclassification passes read `<data_dir>/labels` and
    `<data_dir>/images`, so this has to name the dataset the CSV was collected
    against -- correcting one run's rows against another run's captures would
    silently mislabel them. An explicit --data-dir always wins. Otherwise a
    --csv sitting beside a `labels/` directory identifies its own dataset,
    which is how the pre-reorganization archives are laid out; a CSV under
    `outputs/` has no captures beside it and falls through to the active
    dataset.
    """
    if data_dir is not None:
        return data_dir
    if csv_path is not None and (csv_path.parent / "labels").is_dir():
        return csv_path.parent
    return DATASET_DIR


def analyze_main(argv: list[str] | None = None) -> None:
    """Run the analysis CLI with an explicit, testable argument vector."""
    args = build_parser().parse_args(argv)
    if bool(args.compare_a) != bool(args.compare_b):
        print("[ERROR] --compare-a and --compare-b must be given together.")
        raise SystemExit(1)
    if args.compare_a and args.compare_b:
        sample = DEFAULT_SAMPLE if args.sample == "all" else args.sample
        run_cross_comparison(
            args.compare_a, args.compare_b, list(EXPERIMENTAL_PROFILES), sample,
            resolve_data_dir(args.data_dir, args.compare_a),
        )
        return
    run_analysis(
        resolve_data_dir(args.data_dir, args.csv), args.csv, args.permutations,
        args.seed, args.mode, args.sample, args.label_changed,
    )


main = analyze_main

if __name__ == "__main__":
    analyze_main()
