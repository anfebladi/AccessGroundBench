"""Coordination of the complete statistical-analysis workflow."""
from __future__ import annotations
from pathlib import Path

from evaluation.config import ALL_PROFILES
from .data.results import (
    discover_result_csvs, index_rows, load_results, model_name_from_path,
    reclassify_label_changed, reclassify_off_frame,
)
from .reports.grounding import ALPHA, report_per_model, report_pooled, report_sign_test
from .reports.output import write_outputs
from .reports.reachability import report_label_changed_breakdown, report_reachability
from .data.samples import SAMPLE_NAMES, compute_b2_targets

EXPERIMENTAL_PROFILES = [p for p in ALL_PROFILES if p != "baseline"]


def run_analysis(
    data_dir: Path,
    csv_path: Path | None,
    permutations: int,
    seed: int,
    mode: str,
    sample: str,
    label_changed_mode: str,
) -> None:
    """Load, correct, analyze, report, and serialize one analysis request."""
    profiles = list(EXPERIMENTAL_PROFILES)
    if csv_path:
        csv_files = [csv_path]
        data_dir = csv_path.parent
    else:
        csv_files = discover_result_csvs(data_dir, mode)
        if not csv_files:
            print(f"[ERROR] No evaluation_results_*.csv files for mode={mode!r} found in {data_dir}")
            raise SystemExit(1)

    print("=" * 78)
    print("  AccessGroundBench -- Statistical Analysis")
    print(f"  Data dir : {data_dir}")
    print(f"  Mode     : {mode}")
    print(f"  Models   : {len(csv_files)}")
    for path in csv_files:
        print(f"             {path.name}")
    print(f"  Profiles : {', '.join(profiles)}")
    print(f"  alpha    : {ALPHA} (Holm-Bonferroni corrected)")
    print("=" * 78)

    indices = {model_name_from_path(path): index_rows(load_results(path)) for path in csv_files}
    first_index = next(iter(indices.values()))
    available_profiles = {prof for (_screen, _text, prof) in first_index}
    missing_profiles = [p for p in profiles if p not in available_profiles]
    profiles = [p for p in profiles if p in available_profiles]
    if missing_profiles:
        print(f"  Skipped  : {', '.join(missing_profiles)} (no captures for this profile in {data_dir})")

    reclassify_label_changed(list(first_index.values()), data_dir / "labels")
    for index in indices.values():
        reclassify_off_frame(list(index.values()), data_dir / "images")
    label_changed_breakdown = report_label_changed_breakdown(first_index, profiles)
    baseline_rows = [row for (_s, _t, prof), row in first_index.items() if prof == "baseline"]
    b2_targets = compute_b2_targets(baseline_rows)
    samples_to_run = SAMPLE_NAMES if sample == "all" else [sample]

    reachability_all: list[dict] = []
    pooled_all: list[dict] = []
    per_model_all: list[dict] = []
    signs_all: list[dict] = []
    for sample_name in samples_to_run:
        reachability_all += report_reachability(
            first_index, profiles, label_changed_mode, sample_name, b2_targets
        )
        pooled = report_pooled(
            indices, profiles, permutations, seed, sample_name, b2_targets
        )
        per_model = report_per_model(indices, profiles, sample_name, b2_targets)
        signs = report_sign_test(per_model, profiles, sample_name)
        pooled_all += pooled
        per_model_all += per_model
        signs_all += signs

    if len(samples_to_run) > 1:
        print("\n" + "=" * 78)
        print("  SAMPLE SIZES  (paired observations, summed across profiles)")
        print("=" * 78)
        print(f"  {'Sample':<16}{'obs (all models)':>18}{'obs/model':>12}")
        n_models = len(indices)
        for sample_name in samples_to_run:
            total_obs = sum(r["n_observations"] for r in pooled_all if r["sample"] == sample_name)
            print(f"  {sample_name:<16}{total_obs:>18}{total_obs / n_models:>12.0f}")

    write_outputs(
        data_dir, reachability_all, pooled_all, per_model_all, signs_all,
        label_changed_breakdown,
    )
    print()
