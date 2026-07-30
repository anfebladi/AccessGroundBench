"""
stats.py
--------
Statistical primitives for AccessGroundBench analysis.

Kept separate from mcnemar_analysis.py so the mathematics is unit-testable
without touching CSV loading or report formatting.

Contents:
  - Wilson score intervals for single proportions
  - Newcombe method-10 intervals for paired proportion differences
  - McNemar's test (exact binomial / asymptotic with Edwards' correction)
  - Conditional odds ratio with an exact interval
  - Holm-Bonferroni step-down correction over a family of tests
  - Cluster-level permutation test for pooled, correlated paired data
  - Sign test over per-model directions
"""

from __future__ import annotations

from dataclasses import dataclass
from math import comb, sqrt

import numpy as np
from scipy.stats import beta, binomtest, chi2, norm

# Discordant-pair count at or above which the asymptotic test is used.
ASYMPTOTIC_THRESHOLD = 25

# Default number of permutations for the cluster permutation test. With 20000
# draws the smallest reportable p-value is 1/20001 ~= 5e-05.
DEFAULT_PERMUTATIONS = 20_000


# ---------------------------------------------------------------------------
# Single-proportion intervals
# ---------------------------------------------------------------------------

def wilson_interval(k: int, n: int, conf: float = 0.95) -> tuple[float, float]:
    """
    Wilson score interval for a binomial proportion.

    Preferred over the Wald interval because it stays inside [0, 1] and keeps
    sensible coverage near 0 and 1 -- which is exactly where this benchmark
    operates (baseline accuracies of 98-99%).
    """
    if n == 0:
        return 0.0, 0.0

    z = norm.ppf(1.0 - (1.0 - conf) / 2.0)
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2.0 * n)) / denom
    halfwidth = (z / denom) * sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))
    return max(0.0, centre - halfwidth), min(1.0, centre + halfwidth)


# ---------------------------------------------------------------------------
# Paired-proportion difference
# ---------------------------------------------------------------------------

def paired_difference_interval(
    a: int, b: int, c: int, d: int, conf: float = 0.95
) -> tuple[float, float, float]:
    """
    Newcombe (1998) method 10 interval for the difference of paired proportions.

    Returns (difference, lower, upper) where difference = p_baseline - p_exp.

    The two arms share the same targets, so their proportions are correlated and
    an unpaired interval would be too wide. Newcombe's method combines Wilson
    intervals for each arm with the observed correlation phi.
    """
    n = a + b + c + d
    if n == 0:
        return 0.0, 0.0, 0.0

    p1 = (a + b) / n   # baseline accuracy
    p2 = (a + c) / n   # experimental accuracy
    diff = p1 - p2

    l1, u1 = wilson_interval(a + b, n, conf)
    l2, u2 = wilson_interval(a + c, n, conf)

    # Correlation between the two arms across the 2x2 table.
    denom = (a + b) * (c + d) * (a + c) * (b + d)
    phi = ((a * d - b * c) / sqrt(denom)) if denom > 0 else 0.0

    lower = diff - sqrt(
        max(0.0, (p1 - l1) ** 2 - 2 * phi * (p1 - l1) * (u2 - p2) + (u2 - p2) ** 2)
    )
    upper = diff + sqrt(
        max(0.0, (u1 - p1) ** 2 - 2 * phi * (u1 - p1) * (p2 - l2) + (p2 - l2) ** 2)
    )
    return diff, max(-1.0, lower), min(1.0, upper)


# ---------------------------------------------------------------------------
# McNemar's test
# ---------------------------------------------------------------------------

def exact_binomial_two_tailed(b: int, c: int) -> float:
    """Exact two-tailed McNemar p-value: discordant pairs ~ Binomial(b+c, 0.5)."""
    n = b + c
    if n == 0:
        return 1.0
    return float(binomtest(b, n, 0.5, alternative="two-sided").pvalue)


def asymptotic_mcnemar(b: int, c: int) -> tuple[float, float]:
    """Asymptotic McNemar with Edwards' continuity correction."""
    n = b + c
    if n == 0:
        return 0.0, 1.0
    statistic = (abs(b - c) - 1) ** 2 / n
    return statistic, float(1.0 - chi2.cdf(statistic, df=1))


def mcnemar_test(b: int, c: int) -> dict:
    """
    Run McNemar's test, choosing the exact or asymptotic variant automatically.

    Returns a dict with 'test', 'statistic' and 'p_value'.
    """
    n = b + c
    if n == 0:
        return {"test": "N/A (no discordant pairs)", "statistic": None, "p_value": 1.0}

    if n >= ASYMPTOTIC_THRESHOLD:
        statistic, p_value = asymptotic_mcnemar(b, c)
        return {
            "test": f"Asymptotic (Edwards' correction, n={n})",
            "statistic": statistic,
            "p_value": p_value,
        }

    return {
        "test": f"Exact Binomial (n={n})",
        "statistic": None,
        "p_value": exact_binomial_two_tailed(b, c),
    }


def conditional_odds_ratio(b: int, c: int, conf: float = 0.95) -> tuple:
    """
    Conditional odds ratio b/c for the discordant pairs, with an exact interval.

    A p-value says only whether an effect exists; this says how large it is.
    OR = 2 means a target was twice as likely to break as to recover.

    Derived by treating b as Binomial(b+c, p) and transforming the
    Clopper-Pearson interval for p through OR = p / (1 - p).
    Returns (or_point, lower, upper); components are None when undefined.
    """
    n = b + c
    if n == 0:
        return None, None, None

    point = float("inf") if c == 0 else b / c

    alpha = 1.0 - conf
    p_lo = beta.ppf(alpha / 2.0, b, n - b + 1) if b > 0 else 0.0
    p_hi = beta.ppf(1.0 - alpha / 2.0, b + 1, n - b) if b < n else 1.0

    lower = p_lo / (1.0 - p_lo) if p_lo < 1.0 else float("inf")
    upper = p_hi / (1.0 - p_hi) if p_hi < 1.0 else float("inf")
    return point, lower, upper


# ---------------------------------------------------------------------------
# Multiple-comparison correction
# ---------------------------------------------------------------------------

@dataclass
class HolmResult:
    """Outcome of a Holm-Bonferroni step for a single test in a family."""

    p_value: float
    threshold: float
    reject: bool


def holm_bonferroni(p_values: dict[str, float], alpha: float = 0.05) -> dict[str, HolmResult]:
    """
    Holm-Bonferroni step-down correction over a family of tests.

    Sort ascending; test i is compared against alpha / (m - i). The procedure
    stops at the first failure and every later test is retained.

    Chosen over plain Bonferroni because it is uniformly more powerful at the
    same family-wise error rate, and unlike Benjamini-Hochberg it needs no
    independence assumption -- these tests share underlying data.
    """
    ordered = sorted(p_values.items(), key=lambda kv: kv[1])
    m = len(ordered)
    results: dict[str, HolmResult] = {}
    stopped = False

    for i, (key, p_value) in enumerate(ordered):
        threshold = alpha / (m - i)
        reject = (p_value < threshold) and not stopped
        if not reject:
            stopped = True
        results[key] = HolmResult(p_value=p_value, threshold=threshold, reject=reject)

    return results


# ---------------------------------------------------------------------------
# Cluster-level permutation test
# ---------------------------------------------------------------------------

def cluster_permutation_test(
    clusters: dict,
    n_permutations: int = DEFAULT_PERMUTATIONS,
    seed: int = 0,
) -> dict:
    """
    Two-tailed permutation test on paired binary outcomes with clustering.

    Args:
        clusters: {cluster_key: [(baseline_score, experimental_score), ...]}.
            One cluster is one target; its list holds that target's paired
            outcome under every model evaluated.

    Why this test rather than a per-model McNemar:

      1. Power. Per-model tests have only a handful of discordant pairs each.
         The smallest achievable two-tailed exact binomial p-value is
         2 * 0.5**n, so after correcting across a family of ~28 tests a model
         needs >= 11 one-directional discordant pairs to reach significance --
         which several models cannot produce even in principle. Pooling the
         models supplies enough discordant observations to test at all.

      2. Non-independence. The same targets are reused for every model, so the
         per-model outcomes for one target are correlated: a target that is
         intrinsically hard is hard for everyone. Pooling them into a single
         McNemar would treat them as independent and manufacture confidence.
         Permuting whole clusters preserves that correlation exactly, because
         a target's outcomes across models are always relabelled together.

    Under H0 the baseline/experimental labels are exchangeable within a target,
    so flipping a cluster negates its contribution to the statistic
    T = sum(baseline - experimental). The null distribution is built by
    randomly flipping each cluster and recomputing T.

    Returns a dict with the observed statistic, b/c totals, and the p-value.
    """
    keys = list(clusters)
    if not keys:
        return {
            "statistic": 0.0, "p_value": 1.0, "b": 0, "c": 0,
            "n_clusters": 0, "n_observations": 0, "n_permutations": n_permutations,
        }

    cluster_diffs = np.array(
        [sum(base - exp for base, exp in clusters[k]) for k in keys],
        dtype=float,
    )
    observed = float(cluster_diffs.sum())

    b = sum(1 for k in keys for base, exp in clusters[k] if base == 1 and exp == 0)
    c = sum(1 for k in keys for base, exp in clusters[k] if base == 0 and exp == 1)
    n_observations = sum(len(clusters[k]) for k in keys)

    rng = np.random.default_rng(seed)
    signs = rng.choice([-1.0, 1.0], size=(n_permutations, len(keys)))
    null_distribution = signs @ cluster_diffs

    # +1 in numerator and denominator: the observed labelling is itself one of
    # the equally likely permutations, so the p-value can never be exactly 0.
    p_value = float(
        (np.sum(np.abs(null_distribution) >= abs(observed)) + 1) / (n_permutations + 1)
    )

    return {
        "statistic": observed,
        "p_value": p_value,
        "b": b,
        "c": c,
        "n_clusters": len(keys),
        "n_observations": n_observations,
        "n_permutations": n_permutations,
    }


# ---------------------------------------------------------------------------
# Sign test across models
# ---------------------------------------------------------------------------

def sign_test(n_down: int, n_up: int) -> float:
    """
    Two-tailed sign test over per-model directions, ignoring ties.

    Used as descriptive corroboration only: models are not a random sample of
    a population, so this checks that a pooled effect is consistent across
    models rather than driven by one, and is not an independent inferential
    claim.
    """
    n = n_down + n_up
    if n == 0:
        return 1.0
    return float(binomtest(n_down, n, 0.5, alternative="two-sided").pvalue)
