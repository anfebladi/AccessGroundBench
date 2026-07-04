"""
mcnemar_analysis.py
-------------------
Phase 4: Statistical Testing via McNemar's Test.

Evaluates whether accessibility layout distortions cause a statistically
significant degradation in VLM spatial grounding capabilities -- and whether
supplying the accessibility tree recovers it.

Comparisons are auto-selected from the profiles present in the CSV:
  A vs B: baseline vs each elder profile            (layout effect)
  B vs C: each elder profile vs its _tree variant   (a11y tree effect)

For each comparison:
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

# Baseline (condition A) profile name
BASELINE_PROFILE = "baseline"

# Suffix marking condition-C rows written by vlm_evaluator.py (--with-tree)
TREE_SUFFIX = "_tree"

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
    base_profile: str = BASELINE_PROFILE,
) -> tuple[int, int, int, int]:
    """
    Compile the 2x2 contingency matrix for base_profile vs. experimental_profile.

    base_profile defaults to "baseline" so existing baseline-vs-elder calls are
    unchanged; pass an elder profile as base_profile to run B-vs-C comparisons
    (e.g. elder_combo_max vs elder_combo_max_tree).

    Returns (a, b, c, d) where:
      a = Both Pass    (base=1, exp=1)
      b = Broke It     (base=1, exp=0) -- exp did worse than base
      c = Recovered    (base=0, exp=1) -- exp did better than base
      d = Both Fail    (base=0, exp=0)
    """
    a = b = c = d = 0

    for key, scores in pairs.items():
        base_score = scores.get(base_profile)
        experimental_score = scores.get(experimental_profile)

        # Skip elements without both scores
        if base_score is None or experimental_score is None:
            continue

        if base_score == 1 and experimental_score == 1:
            a += 1
        elif base_score == 1 and experimental_score == 0:
            b += 1
        elif base_score == 0 and experimental_score == 1:
            c += 1
        else:
            d += 1

    return a, b, c, d


def present_profiles(pairs: dict[str, dict[str, int]]) -> set[str]:
    """Return the set of profile names that appear anywhere in the paired data."""
    seen: set[str] = set()
    for scores in pairs.values():
        seen.update(scores.keys())
    return seen


def build_comparisons(pairs: dict[str, dict[str, int]]) -> list[tuple[str, str, str]]:
    """
    Decide which McNemar comparisons to run based on the profiles present.

    Returns a list of (base_profile, exp_profile, label) tuples:
      - baseline vs each elder profile present     -> "layout effect" (A vs B)
      - each elder profile vs its _tree variant     -> "a11y tree effect" (B vs C)
    Only comparisons whose BOTH profiles exist in the data are included.
    """
    seen = present_profiles(pairs)
    comparisons: list[tuple[str, str, str]] = []

    # A vs B: baseline vs each elder profile
    if BASELINE_PROFILE in seen:
        for profile in EXPERIMENTAL_PROFILES:
            if profile in seen:
                comparisons.append((BASELINE_PROFILE, profile, "layout effect"))

    # B vs C: each elder profile vs its tree-augmented variant
    for profile in EXPERIMENTAL_PROFILES:
        tree_profile = profile + TREE_SUFFIX
        if profile in seen and tree_profile in seen:
            comparisons.append((profile, tree_profile, "a11y tree effect"))

    return comparisons


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
    base_profile: str,
    exp_profile: str,
    a: int, b: int, c: int, d: int,
    result: dict,
    label: str = "",
) -> str:
    """Format a single base-vs-exp McNemar test result as a readable block."""
    total = a + b + c + d
    tag = f"  [{label}]" if label else ""
    lines = [
        f"",
        f"{'=' * 60}",
        f"  {exp_profile}  vs.  {base_profile}{tag}",
        f"{'=' * 60}",
        f"",
        f"  2x2 Contingency Matrix (n={total} paired elements):",
        f"  +---------------------+--------------+--------------+",
        f"  |                     | Exp. PASS    | Exp. FAIL    |",
        f"  +---------------------+--------------+--------------+",
        f"  | Base PASS           |  a = {a:<7} |  b = {b:<7} |",
        f"  | Base FAIL           |  c = {c:<7} |  d = {d:<7} |",
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
            f"  >> REJECT H0 (p < {ALPHA}): STATISTICALLY SIGNIFICANT difference in "
            f"VLM grounding between '{base_profile}' and '{exp_profile}'."
        )
    else:
        lines.append(
            f"  >> FAIL TO REJECT H0 (p >= {ALPHA}): no significant difference in "
            f"VLM grounding between '{base_profile}' and '{exp_profile}'; "
            f"differences fall within random statistical noise."
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

    # Decide which comparisons the data supports (A-vs-B, and B-vs-C if tree data present)
    comparisons = build_comparisons(pairs)
    if not comparisons:
        print("[ERROR] No runnable comparisons found. Need a 'baseline' profile plus "
              "at least one elder profile in the CSV.")
        sys.exit(1)

    # Run McNemar for each comparison, caching results for the summary table
    computed: list[tuple[str, str, str, tuple[int, int, int, int], dict]] = []

    for base_profile, exp_profile, label in comparisons:
        a, b, c, d = compute_contingency(pairs, exp_profile, base_profile)
        result = run_mcnemar(b, c)
        computed.append((base_profile, exp_profile, label, (a, b, c, d), result))
        print(format_report(base_profile, exp_profile, a, b, c, d, result, label))

    # Summary table
    print("\n" + "=" * 72)
    print("  Summary")
    print("=" * 72)
    print(f"  {'Comparison':<38} {'b+c':>5}  {'Test':<12}  {'p-value':>10}  {'Result'}")
    print(f"  {'-' * 38} {'-' * 5}  {'-' * 12}  {'-' * 10}  {'-' * 12}")

    for base_profile, exp_profile, label, (a, b, c, d), result in computed:
        verdict = "SIGNIFICANT" if result["p_value"] < ALPHA else "Not Sig."
        test_short = "Asymptotic" if b + c >= ASYMPTOTIC_THRESHOLD else "Exact Binom."
        if b + c == 0:
            test_short = "N/A"
        name = f"{exp_profile} vs {base_profile}"
        print(f"  {name:<38} {b + c:>5}  {test_short:<12}  "
              f"{result['p_value']:>10.6f}  {verdict}")

    print()


if __name__ == "__main__":
    main()
