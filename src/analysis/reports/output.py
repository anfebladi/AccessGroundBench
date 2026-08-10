"""Serialization of analysis result tables."""
from __future__ import annotations
import csv
from pathlib import Path

from backups import preserve


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
    """Write the result tables to CSV.

    Any existing tables here are preserved first. The tables are named after
    the analysis rather than the run, so a re-run with a different
    --permutations or --seed replaces the numbers behind a finished
    experiment; the copy is what makes that recoverable.
    """
    preserve(data_dir, reason="re-analysis replaces these tables")
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
