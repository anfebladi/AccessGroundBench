"""
mcnemar_analysis.py
-------------------
Phase 4: Statistical Testing via McNemar's Test.

Evaluates whether accessibility layout distortions cause a statistically
significant degradation in VLM spatial grounding capabilities.

For each experimental profile vs. baseline:
  1. Constructs paired samples keyed by (screen, target_text)
  2. Builds a 2x2 contingency matrix of discordant pairs
  3. Selects asymptotic (Edwards' correction) or exact binomial test
  4. Reports p-values against alpha=0.05

Usage:
  python mcnemar_analysis.py                                 # default CSV path
  python mcnemar_analysis.py --csv path/to/results.csv       # custom CSV
"""

import argparse
import csv
import sys
from collections import defaultdict
from math import comb
from pathlib import Path

try:
    from scipy.stats import chi2, binomtest
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent
DEFAULT_CSV = PROJECT_ROOT / "dataset" / "evaluation_results.csv"

# Statistical threshold
ALPHA = 0.05

# Discordant pair threshold for test selection
ASYMPTOTIC_THRESHOLD = 25

# Baseline-accuracy threshold below which a non-significant result is treated
# as floor-limited rather than as evidence of resilience. McNemar can only
# detect degradation among targets that passed at baseline (a + b); when the
# baseline accuracy is low, most targets already fail and the test is
# underpowered by construction, so a null result says nothing about resilience.
FLOOR_ACC_THRESHOLD = 50.0

# Experimental profiles to compare against baseline
EXPERIMENTAL_PROFILES = [
    "elder_text_heavy",
    "elder_zoom_heavy",
    "elder_combo_max",
    "elder_combo_rtl",
    "colorblind_deuteranomaly",
]


# ---------------------------------------------------------------------------
# Data Loading
# ---------------------------------------------------------------------------

def load_results(csv_path: Path) -> list[dict]:
    """Load the evaluation results CSV into a list of row dicts."""
    if not csv_path.is_file():
        print(f"[ERROR] Results CSV not found: {csv_path}")
        sys.exit(1)

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"[LOADED] {len(rows)} rows from {csv_path}")
    return rows


# ---------------------------------------------------------------------------
# Paired Sample Construction
# ---------------------------------------------------------------------------

def build_pairs(rows: list[dict]) -> dict[str, dict[str, dict[str, int]]]:
    """
    Reorganize flat CSV rows into paired samples.

    Returns:
        {tracking_key: {profile_name: score}} nested dict.
        tracking_key = "{screen}_{target_text}"
    """
    pairs: dict[str, dict[str, int]] = defaultdict(dict)

    for row in rows:
        screen = row.get("screen", "")
        text = row.get("target_text", "")
        profile = row.get("profile", "")
        score = int(row.get("score", 0))

        key = f"{screen}_{text}"
        pairs[key][profile] = score

    return dict(pairs)


# ---------------------------------------------------------------------------
# Contingency Matrix
# ---------------------------------------------------------------------------

def compute_contingency(
    pairs: dict[str, dict[str, int]],
    experimental_profile: str,
) -> tuple[int, int, int, int]:
    """
    Compile the 2x2 contingency matrix for baseline vs. one experimental profile.

    Returns (a, b, c, d) where:
      a = Both Pass      (baseline=1, experimental=1)
      b = Broke It       (baseline=1, experimental=0) -- degradation
      c = Fluke Recovery  (baseline=0, experimental=1)
      d = Both Fail      (baseline=0, experimental=0)
    """
    a = b = c = d = 0

    for key, scores in pairs.items():
        baseline_score = scores.get("baseline")
        experimental_score = scores.get(experimental_profile)

        # Skip elements without both scores
        if baseline_score is None or experimental_score is None:
            continue

        if baseline_score == 1 and experimental_score == 1:
            a += 1
        elif baseline_score == 1 and experimental_score == 0:
            b += 1
        elif baseline_score == 0 and experimental_score == 1:
            c += 1
        else:
            d += 1

    return a, b, c, d


# ---------------------------------------------------------------------------
# Hypothesis Testing
# ---------------------------------------------------------------------------

def exact_binomial_two_tailed(b: int, c: int) -> float:
    """
    Exact binomial test (two-tailed) for McNemar's test.

    Under H0, discordant pairs follow Binomial(n=b+c, p=0.5).
    Two-tailed p-value = 2 x P(X >= max(b,c)) under the binomial.
    """
    n = b + c
    if n == 0:
        return 1.0

    if HAS_SCIPY:
        # scipy.stats.binomtest replaced the deprecated binom_test
        result = binomtest(b, n, 0.5, alternative="two-sided")
        return result.pvalue

    # Manual fallback: compute two-tailed p-value
    k = min(b, c)
    # P(X <= k) using CDF
    p_tail = sum(comb(n, i) * (0.5 ** n) for i in range(k + 1))
    return min(2.0 * p_tail, 1.0)


def asymptotic_mcnemar(b: int, c: int) -> tuple[float, float]:
    """
    Asymptotic McNemar test with Edwards' continuity correction.

    chi2 = (|b - c| - 1)^2 / (b + c)

    Returns (chi2_stat, p_value).
    """
    n = b + c
    if n == 0:
        return 0.0, 1.0

    chi2_stat = (abs(b - c) - 1) ** 2 / n

    if HAS_SCIPY:
        p_value = 1.0 - chi2.cdf(chi2_stat, df=1)
    else:
        # Very rough fallback -- recommend installing scipy
        print("  [WARN] scipy not available; p-value approximation may be imprecise.")
        # For chi2 with df=1, p < 0.05 when chi2 > 3.841
        p_value = 0.0 if chi2_stat > 10.828 else (0.05 if chi2_stat > 3.841 else 0.5)

    return chi2_stat, p_value


def run_mcnemar(b: int, c: int) -> dict:
    """
    Automatically select and execute the appropriate McNemar test variant.

    Returns a dict with 'test', 'statistic', 'p_value' keys.
    """
    n = b + c

    if n == 0:
        return {
            "test": "N/A (no discordant pairs)",
            "statistic": None,
            "p_value": 1.0,
        }

    if n >= ASYMPTOTIC_THRESHOLD:
        chi2_stat, p_value = asymptotic_mcnemar(b, c)
        return {
            "test": f"Asymptotic (Edwards' correction, n={n})",
            "statistic": chi2_stat,
            "p_value": p_value,
        }
    else:
        p_value = exact_binomial_two_tailed(b, c)
        return {
            "test": f"Exact Binomial (n={n})",
            "statistic": None,
            "p_value": p_value,
        }


# ---------------------------------------------------------------------------
# Report Formatting
# ---------------------------------------------------------------------------

def format_report(
    profile: str,
    a: int, b: int, c: int, d: int,
    result: dict,
) -> str:
    """Format a single profile's McNemar test results as a readable block."""
    total = a + b + c + d
    base_acc = ((a + b) / total * 100) if total > 0 else 0
    exp_acc = ((a + c) / total * 100) if total > 0 else 0

    lines = [
        f"",
        f"{'=' * 60}",
        f"  Profile: {profile}  vs.  baseline",
        f"{'=' * 60}",
        f"",
        f"  Accuracies:",
        f"    Baseline Accuracy:     {base_acc:.1f}% ({a+b}/{total})",
        f"    Experimental Accuracy: {exp_acc:.1f}% ({a+c}/{total})",
        f"",
        f"  2x2 Contingency Matrix (n={total} paired elements):",
        f"  +---------------------+--------------+--------------+",
        f"  |                     | Exp. PASS    | Exp. FAIL    |",
        f"  +---------------------+--------------+--------------+",
        f"  | Baseline PASS       |  a = {a:<7} |  b = {b:<7} |",
        f"  | Baseline FAIL       |  c = {c:<7} |  d = {d:<7} |",
        f"  +---------------------+--------------+--------------+",
        f"",
        f"  Discordant pairs: b + c = {b + c}",
        f"  Test selected:    {result['test']}",
    ]

    if result["statistic"] is not None:
        lines.append(f"  chi2 statistic:   {result['statistic']:.4f}")

    lines.append(f"  p-value:          {result['p_value']:.6f}")

    floor_limited = base_acc < FLOOR_ACC_THRESHOLD
    if floor_limited:
        lines.append(
            f"  Floor check:      FLOOR-LIMITED (baseline acc {base_acc:.1f}% "
            f"< {FLOOR_ACC_THRESHOLD:.0f}%; only {a + b}/{total} targets "
            f"could show degradation)"
        )
    lines.append(f"")

    if result["p_value"] < ALPHA:
        lines.append(
            f"  >> REJECT H0 (p < {ALPHA}): The accessibility layout modifications "
            f"caused a STATISTICALLY SIGNIFICANT alteration in VLM grounding "
            f"performance for profile '{profile}'."
        )
    elif floor_limited:
        lines.append(
            f"  >> INCONCLUSIVE (p >= {ALPHA}, FLOOR EFFECT): Baseline accuracy is "
            f"only {base_acc:.1f}%, so most targets already fail before any "
            f"distortion. This test CANNOT detect degradation here and is NOT "
            f"evidence of resilience for profile '{profile}'."
        )
    else:
        lines.append(
            f"  >> FAIL TO REJECT H0 (p >= {ALPHA}): The model demonstrated "
            f"spatial localization RESILIENCE. Performance differences fall within "
            f"random statistical noise for profile '{profile}'."
        )

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Cross-File Comparison (Vision-only vs. Tree-injected)
# ---------------------------------------------------------------------------

def build_cross_file_pairs(
    rows_a: list[dict],
    rows_b: list[dict],
) -> dict[str, dict[str, tuple[int, int]]]:
    """
    Build paired samples across two CSV files for the same profiles.

    Returns {tracking_key: {profile: (score_a, score_b)}} where
    tracking_key = "{screen}_{target_text}".
    """
    # Index file A by (screen, target_text, profile) -> score
    index_a: dict[tuple[str, str, str], int] = {}
    for row in rows_a:
        key = (row.get("screen", ""), row.get("target_text", ""), row.get("profile", ""))
        index_a[key] = int(row.get("score", 0))

    # Index file B by (screen, target_text, profile) -> score
    index_b: dict[tuple[str, str, str], int] = {}
    for row in rows_b:
        key = (row.get("screen", ""), row.get("target_text", ""), row.get("profile", ""))
        index_b[key] = int(row.get("score", 0))

    # Build paired structure keyed by tracking_key, grouped by profile
    pairs: dict[str, dict[str, tuple[int, int]]] = defaultdict(dict)
    all_keys = set(index_a.keys()) | set(index_b.keys())

    for screen, target_text, profile in all_keys:
        tracking_key = f"{screen}_{target_text}"
        score_a = index_a.get((screen, target_text, profile))
        score_b = index_b.get((screen, target_text, profile))
        if score_a is not None and score_b is not None:
            pairs[tracking_key][profile] = (score_a, score_b)

    return dict(pairs)


def compute_cross_contingency(
    pairs: dict[str, dict[str, tuple[int, int]]],
    profile: str,
) -> tuple[int, int, int, int]:
    """
    Compute the 2x2 contingency matrix comparing file A vs file B
    for a specific profile.

    Returns (a, b, c, d) where:
      a = Both hit   (A=1, B=1)
      b = Tree hurt  (A=1, B=0) -- regression
      c = Tree helped (A=0, B=1) -- improvement
      d = Both miss  (A=0, B=0)
    """
    a = b = c = d = 0

    for key, profile_scores in pairs.items():
        scores = profile_scores.get(profile)
        if scores is None:
            continue
        score_a, score_b = scores

        if score_a == 1 and score_b == 1:
            a += 1
        elif score_a == 1 and score_b == 0:
            b += 1
        elif score_a == 0 and score_b == 1:
            c += 1
        else:
            d += 1

    return a, b, c, d


def format_cross_report(
    profile: str,
    a: int, b: int, c: int, d: int,
    result: dict,
) -> str:
    """Format a cross-file comparison result as a readable block."""
    total = a + b + c + d
    acc_a = ((a + b) / total * 100) if total > 0 else 0
    acc_b = ((a + c) / total * 100) if total > 0 else 0

    lines = [
        f"",
        f"{'=' * 60}",
        f"  Profile: {profile}",
        f"  Vision-only vs. Vision + A11y Tree",
        f"{'=' * 60}",
        f"",
        f"  Accuracies:",
        f"    Vision-only Accuracy:  {acc_a:.1f}% ({a+b}/{total})",
        f"    With Tree Accuracy:    {acc_b:.1f}% ({a+c}/{total})",
        f"",
        f"  2x2 Contingency Matrix (n={total} paired elements):",
        f"  +---------------------+--------------+--------------+",
        f"  |                     | Tree PASS    | Tree FAIL    |",
        f"  +---------------------+--------------+--------------+",
        f"  | Vision-only PASS    |  a = {a:<7} |  b = {b:<7} |",
        f"  | Vision-only FAIL    |  c = {c:<7} |  d = {d:<7} |",
        f"  +---------------------+--------------+--------------+",
        f"",
        f"  Discordant pairs: b + c = {b + c}",
        f"  Test selected:    {result['test']}",
    ]

    if result["statistic"] is not None:
        lines.append(f"  chi2 statistic:   {result['statistic']:.4f}")

    lines.append(f"  p-value:          {result['p_value']:.6f}")
    lines.append(f"")

    if result["p_value"] < ALPHA:
        lines.append(
            f"  >> REJECT H0 (p < {ALPHA}): Tree injection caused a "
            f"STATISTICALLY SIGNIFICANT change in VLM grounding "
            f"performance for profile '{profile}'."
        )
    else:
        lines.append(
            f"  >> FAIL TO REJECT H0 (p >= {ALPHA}): Tree injection did NOT "
            f"significantly alter VLM grounding performance for "
            f"profile '{profile}'. Differences fall within random noise."
        )

    lines.append("")
    return "\n".join(lines)


def run_cross_comparison(csv_a: Path, csv_b: Path) -> None:
    """Run cross-file McNemar comparison between vision-only and tree-injected results."""
    print(f"\n{'=' * 60}")
    print(f"  Cross-File Comparison")
    print(f"  File A (Vision-only): {csv_a.name}")
    print(f"  File B (With Tree):   {csv_b.name}")
    print(f"{'=' * 60}")

    rows_a = load_results(csv_a)
    rows_b = load_results(csv_b)

    pairs = build_cross_file_pairs(rows_a, rows_b)
    print(f"[PAIRS] {len(pairs)} unique (screen, target_text) tracking keys")

    # Detect profiles present in the paired data
    profiles_present = set()
    for profile_scores in pairs.values():
        profiles_present.update(profile_scores.keys())

    profiles_to_compare = [p for p in EXPERIMENTAL_PROFILES if p in profiles_present]
    if not profiles_to_compare:
        print("[ERROR] No matching experimental profiles found across both files.")
        sys.exit(1)

    # Derive output filename
    stem_a = csv_a.stem.replace("evaluation_results_", "")
    out_csv_path = PROJECT_ROOT / "dataset" / f"mcnemar_compare_{stem_a}.csv"
    print(f"[INFO] Writing comparison results to: {out_csv_path}")

    with open(out_csv_path, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.writer(out_f)
        writer.writerow([
            "Profile", "Total_Pairs", "Both_Pass_a", "Tree_Hurt_b",
            "Tree_Helped_c", "Both_Fail_d", "Discordant_Pairs",
            "VisionOnly_Acc", "WithTree_Acc", "Test_Used", "Statistic",
            "P_Value", "Significant",
        ])

        for profile in profiles_to_compare:
            a, b, c, d = compute_cross_contingency(pairs, profile)
            result = run_mcnemar(b, c)
            report = format_cross_report(profile, a, b, c, d, result)
            print(report)

            verdict = "Yes" if result["p_value"] < ALPHA else "No"
            total = a + b + c + d
            acc_a = f"{((a + b) / total * 100):.1f}%" if total > 0 else "0%"
            acc_b = f"{((a + c) / total * 100):.1f}%" if total > 0 else "0%"

            writer.writerow([
                profile, total, a, b, c, d, b + c,
                acc_a, acc_b,
                result["test"],
                result["statistic"] if result["statistic"] is not None else "",
                result["p_value"], verdict,
            ])

    # Summary table
    print("\n" + "=" * 80)
    print(f"  Cross-File Summary: Vision-only vs. Vision + A11y Tree")
    print("=" * 80)
    print(f"  {'Profile':<20} {'Vis Acc':>9} {'Tree Acc':>9} {'b+c':>5}  {'Test':<15}  {'p-value':>10}  {'Result'}")
    print(f"  {'-' * 20} {'-' * 9} {'-' * 9} {'-' * 5}  {'-' * 15}  {'-' * 10}  {'-' * 12}")

    for profile in profiles_to_compare:
        a, b, c, d = compute_cross_contingency(pairs, profile)
        result = run_mcnemar(b, c)
        verdict = "SIGNIFICANT" if result["p_value"] < ALPHA else "Not Sig."
        test_short = "Asymptotic" if b + c >= ASYMPTOTIC_THRESHOLD else "Exact Binom."
        if b + c == 0:
            test_short = "N/A"

        total = a + b + c + d
        acc_a = f"{((a + b) / total * 100):.1f}%" if total > 0 else "0%"
        acc_b = f"{((a + c) / total * 100):.1f}%" if total > 0 else "0%"

        print(f"  {profile:<20} {acc_a:>9} {acc_b:>9} {b + c:>5}  {test_short:<15}  "
              f"{result['p_value']:>10.6f}  {verdict}")

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="AccessGroundBench -- McNemar's Statistical Analysis"
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Path to a specific evaluation_results_*.csv file. If omitted, runs on all in dataset/",
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

    # Cross-file comparison mode
    if args.compare_a and args.compare_b:
        print("=" * 60)
        print("  AccessGroundBench -- McNemar's Cross-File Comparison")
        print(f"  alpha: {ALPHA}")
        print("=" * 60)
        run_cross_comparison(args.compare_a, args.compare_b)
        return

    if args.compare_a or args.compare_b:
        print("[ERROR] Both --compare-a and --compare-b are required for cross-file comparison.")
        sys.exit(1)

    # Standard single-file analysis (unchanged)
    print("=" * 60)
    print("  AccessGroundBench -- McNemar's Test Analysis")
    print(f"  alpha: {ALPHA}")
    print("=" * 60)

    dataset_dir = PROJECT_ROOT / "dataset"
    if args.csv:
        csv_files = [args.csv]
    else:
        csv_files = list(dataset_dir.glob("evaluation_results_*.csv"))
        if not csv_files:
            # Fallback to the original default if no specific files found
            if DEFAULT_CSV.is_file():
                csv_files = [DEFAULT_CSV]
            else:
                print(f"[ERROR] No evaluation_results_*.csv files found in {dataset_dir}")
                sys.exit(1)

    for csv_file in csv_files:
        print(f"\n{'=' * 60}")
        print(f"  Analyzing: {csv_file.name}")
        print(f"{'=' * 60}")

        # Extract model name from filename: evaluation_results_model_name.csv
        model_name = csv_file.stem.replace("evaluation_results_", "")
        if model_name == "evaluation_results":
            model_name = "default"

        # Load data
        rows = load_results(csv_file)

        # Build paired samples
        pairs = build_pairs(rows)
        print(f"[PAIRS] {len(pairs)} unique (screen, target_text) tracking keys")

        out_csv_path = dataset_dir / f"mcnemar_results_{model_name}.csv"
        print(f"[INFO] Writing statistical results to: {out_csv_path}")

        with open(out_csv_path, "w", newline="", encoding="utf-8") as out_f:
            writer = csv.writer(out_f)
            writer.writerow([
                "Profile", "Total_Pairs", "Both_Pass_a", "Broke_It_b",
                "Fluke_Recovery_c", "Both_Fail_d", "Discordant_Pairs",
                "Baseline_Acc", "Exp_Acc", "Test_Used", "Statistic", "P_Value",
                "Significant", "Floor_Limited"
            ])

            for profile in EXPERIMENTAL_PROFILES:
                a, b, c, d = compute_contingency(pairs, profile)
                result = run_mcnemar(b, c)
                report = format_report(profile, a, b, c, d, result)
                print(report)

                verdict = "Yes" if result["p_value"] < ALPHA else "No"
                total = a + b + c + d
                base_acc_pct = (a + b) / total * 100 if total > 0 else 0.0
                base_acc = f"{base_acc_pct:.1f}%"
                exp_acc = f"{((a + c) / total * 100):.1f}%" if total > 0 else "0%"
                floor_limited = "Yes" if base_acc_pct < FLOOR_ACC_THRESHOLD else "No"

                writer.writerow([
                    profile, total, a, b, c, d, b + c,
                    base_acc, exp_acc,
                    result["test"],
                    result["statistic"] if result["statistic"] is not None else "",
                    result["p_value"], verdict, floor_limited
                ])

        # Summary table
        print("\n" + "=" * 80)
        print(f"  Summary for {model_name}")
        print("=" * 80)
        print(f"  {'Profile':<20} {'Base Acc':>9} {'Exp Acc':>9} {'b+c':>5}  {'Test':<15}  {'p-value':>10}  {'Result'}")
        print(f"  {'-' * 20} {'-' * 9} {'-' * 9} {'-' * 5}  {'-' * 15}  {'-' * 10}  {'-' * 12}")

        for profile in EXPERIMENTAL_PROFILES:
            a, b, c, d = compute_contingency(pairs, profile)
            result = run_mcnemar(b, c)
            total = a + b + c + d
            base_acc_pct = (a + b) / total * 100 if total > 0 else 0.0
            floor_limited = base_acc_pct < FLOOR_ACC_THRESHOLD

            if result["p_value"] < ALPHA:
                verdict = "SIGNIFICANT"
            elif floor_limited:
                verdict = "Inconclusive (floor)"
            else:
                verdict = "Not Sig."
            test_short = "Asymptotic" if b + c >= ASYMPTOTIC_THRESHOLD else "Exact Binom."
            if b + c == 0:
                test_short = "N/A"

            base_acc = f"{base_acc_pct:.1f}%"
            exp_acc = f"{((a + c) / total * 100):.1f}%" if total > 0 else "0%"

            print(f"  {profile:<20} {base_acc:>9} {exp_acc:>9} {b + c:>5}  {test_short:<15}  "
                  f"{result['p_value']:>10.6f}  {verdict}")

    print()


if __name__ == "__main__":
    main()

