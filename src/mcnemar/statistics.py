"""McNemar hypothesis-test calculations."""

from math import comb

try:
    from scipy.stats import chi2, binomtest

    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


ALPHA = 0.05
ASYMPTOTIC_THRESHOLD = 25


def exact_binomial_two_tailed(b: int, c: int) -> float:
    """Exact binomial test (two-tailed) for McNemar's test."""
    n = b + c
    if n == 0:
        return 1.0

    if HAS_SCIPY:
        result = binomtest(b, n, 0.5, alternative="two-sided")
        return result.pvalue

    k = min(b, c)
    p_tail = sum(comb(n, i) * (0.5**n) for i in range(k + 1))
    return min(2.0 * p_tail, 1.0)


def asymptotic_mcnemar(b: int, c: int) -> tuple[float, float]:
    """Asymptotic McNemar test with Edwards' continuity correction."""
    n = b + c
    if n == 0:
        return 0.0, 1.0

    chi2_stat = (abs(b - c) - 1) ** 2 / n

    if HAS_SCIPY:
        p_value = 1.0 - chi2.cdf(chi2_stat, df=1)
    else:
        print("  [WARN] scipy not available; p-value approximation may be imprecise.")
        p_value = 0.0 if chi2_stat > 10.828 else (0.05 if chi2_stat > 3.841 else 0.5)

    return chi2_stat, p_value


def run_mcnemar(b: int, c: int) -> dict:
    """Select and execute the existing McNemar test variant."""
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

    p_value = exact_binomial_two_tailed(b, c)
    return {
        "test": f"Exact Binomial (n={n})",
        "statistic": None,
        "p_value": p_value,
    }
