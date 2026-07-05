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

# Experimental profiles to compare against baseline
EXPERIMENTAL_PROFILES = [
    "elder_text_heavy",
    "elder_zoom_heavy",
    "elder_combo_max",
    "elder_combo_rtl",
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
    lines = [
        f"",
        f"{'=' * 60}",
        f"  Profile: {profile}  vs.  baseline",
        f"{'=' * 60}",
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
    lines.append(f"")

    if result["p_value"] < ALPHA:
        lines.append(
            f"  >> REJECT H0 (p < {ALPHA}): The accessibility layout modifications "
            f"caused a STATISTICALLY SIGNIFICANT alteration in VLM grounding "
            f"performance for profile '{profile}'."
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
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="AccessGroundBench -- McNemar's Statistical Analysis"
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV,
        help=f"Path to evaluation_results.csv (default: {DEFAULT_CSV})",
    )
    args = parser.parse_args()

    if not HAS_SCIPY:
        print("[WARN] scipy not installed. Using fallback calculations.")
        print("       For precise p-values: pip install scipy")
        print()

    print("=" * 60)
    print("  AccessGroundBench -- McNemar's Test Analysis")
    print(f"  CSV: {args.csv}")
    print(f"  alpha: {ALPHA}")
    print("=" * 60)

    # Load data
    rows = load_results(args.csv)

    # Build paired samples
    pairs = build_pairs(rows)
    print(f"[PAIRS] {len(pairs)} unique (screen, target_text) tracking keys")

    # Run McNemar for each experimental profile
    all_reports = []

    for profile in EXPERIMENTAL_PROFILES:
        a, b, c, d = compute_contingency(pairs, profile)
        result = run_mcnemar(b, c)
        report = format_report(profile, a, b, c, d, result)
        all_reports.append(report)
        print(report)

    # Summary table
    print("\n" + "=" * 60)
    print("  Summary")
    print("=" * 60)
    print(f"  {'Profile':<25} {'b+c':>5}  {'Test':<22}  {'p-value':>10}  {'Result'}")
    print(f"  {'-' * 25} {'-' * 5}  {'-' * 22}  {'-' * 10}  {'-' * 12}")

    for profile in EXPERIMENTAL_PROFILES:
        a, b, c, d = compute_contingency(pairs, profile)
        result = run_mcnemar(b, c)
        verdict = "SIGNIFICANT" if result["p_value"] < ALPHA else "Not Sig."
        test_short = "Asymptotic" if b + c >= ASYMPTOTIC_THRESHOLD else "Exact Binom."
        if b + c == 0:
            test_short = "N/A"
        print(f"  {profile:<25} {b + c:>5}  {test_short:<22}  "
              f"{result['p_value']:>10.6f}  {verdict}")

    print()


if __name__ == "__main__":
    main()
