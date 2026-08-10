"""Paired comparison between two evaluation-result files."""
from __future__ import annotations
import csv
from pathlib import Path

from evaluation.storage.results import STATUS_CO_PRESENT
from ..data.results import index_rows, load_results, reclassify_label_changed, reclassify_off_frame
from .grounding import ALPHA
from .output import _fmt
from ..data.samples import DEFAULT_SAMPLE, compute_b2_targets, target_excluded_for_condition
from ..stats import mcnemar_test
from paths import analysis_dir


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

    label = csv_a.stem.replace("evaluation_results_", "")
    out_path = analysis_dir(data_dir) / "comparisons" / f"mcnemar_compare_{label}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
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
