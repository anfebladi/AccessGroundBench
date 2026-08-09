"""Pooled and per-model grounding inference and direction summaries."""
from __future__ import annotations
from collections import defaultdict

from evaluation.storage.results import STATUS_CO_PRESENT
from ..data.samples import target_excluded_for_condition
from ..stats import (
    cluster_permutation_test,
    conditional_odds_ratio,
    holm_bonferroni,
    mcnemar_test,
    paired_difference_interval,
    sign_test,
)

ALPHA = 0.05
FLOOR_ACC_THRESHOLD = 50.0
CEILING_ACC_THRESHOLD = 95.0


def build_clusters(
    indices: dict[str, dict],
    profile: str,
    sample: str = "full",
    b2_targets: frozenset[tuple[str, str]] = frozenset(),
) -> dict[tuple[str, str], list[tuple[int, int]]]:
    """
    Group paired outcomes by target across every model.

    One cluster is one (screen, target_text); its list holds that target's
    (baseline_score, profile_score) under each model. Only co_present rows in
    both arms are included, and only targets not excluded by `sample` for
    this `profile` (see target_excluded_for_condition).
    """
    clusters: dict[tuple[str, str], list[tuple[int, int]]] = defaultdict(list)

    for index in indices.values():
        for (screen, text, prof), baseline_row in index.items():
            if prof != "baseline" or baseline_row["status"] != STATUS_CO_PRESENT:
                continue
            if target_excluded_for_condition(sample, screen, text, profile, b2_targets):
                continue
            exp_row = index.get((screen, text, profile))
            if exp_row is None or exp_row["status"] != STATUS_CO_PRESENT:
                continue
            clusters[(screen, text)].append(
                (int(baseline_row["score"] or 0), int(exp_row["score"] or 0))
            )

    return dict(clusters)


def report_pooled(
    indices: dict[str, dict],
    profiles: list[str],
    permutations: int,
    seed: int,
    sample: str = "full",
    b2_targets: frozenset[tuple[str, str]] = frozenset(),
) -> list[dict]:
    """Run and print the pooled cluster permutation test for each profile."""
    print("\n" + "=" * 78)
    print(f"  SECTION 2 -- GROUNDING, POOLED ACROSS MODELS  [PRIMARY TEST]  [sample={sample}]")
    print(f"  Cluster permutation, {permutations} draws, resampling unit = target.")
    print("  Co-present targets only. A target's outcomes across all models are")
    print("  relabelled together, preserving the correlation from target reuse.")
    print("=" * 78)

    raw = {}
    rows = []
    for profile in profiles:
        clusters = build_clusters(indices, profile, sample, b2_targets)
        result = cluster_permutation_test(clusters, permutations, seed)
        raw[profile] = result["p_value"]
        rows.append({"sample": sample, "profile": profile, **result})

    corrected = holm_bonferroni(raw, ALPHA)

    print(f"  {'Profile':<28}{'targets':>8}{'obs':>7}{'b':>6}{'c':>6}"
          f"{'p':>10}{'Holm':>9}   verdict")
    print(f"  {'-' * 28}{'-' * 8:>8}{'-' * 7:>7}{'-' * 6:>6}{'-' * 6:>6}"
          f"{'-' * 10:>10}{'-' * 9:>9}   {'-' * 22}")

    for row in rows:
        holm = corrected[row["profile"]]
        direction = "down" if row["b"] > row["c"] else ("up" if row["c"] > row["b"] else "flat")
        if holm.reject:
            verdict = f"SIGNIFICANT ({direction})"
        elif row["p_value"] < ALPHA:
            verdict = f"sig uncorrected ({direction})"
        else:
            verdict = "ns"
        row["holm_threshold"] = holm.threshold
        row["significant"] = holm.reject
        print(f"  {row['profile']:<28}{row['n_clusters']:>8}"
              f"{row['n_observations']:>7}{row['b']:>6}{row['c']:>6}"
              f"{row['p_value']:>10.5f}{holm.threshold:>9.5f}   {verdict}")

    return rows


def compute_contingency(
    index: dict,
    profile: str,
    sample: str = "full",
    b2_targets: frozenset[tuple[str, str]] = frozenset(),
) -> tuple[int, int, int, int]:
    """Build the 2x2 contingency table for baseline vs one profile.

    Returns (a, b, c, d): a both pass, b broke it, c fluke recovery, d both
    fail. Restricted to co_present rows in both arms, so off-screen targets
    and API failures never enter the table; `sample`/`b2_targets`
    additionally drop targets excluded for this profile (see
    target_excluded_for_condition).
    """
    a = b = c = d = 0

    for (screen, text, prof), baseline_row in index.items():
        if prof != "baseline" or baseline_row["status"] != STATUS_CO_PRESENT:
            continue
        if target_excluded_for_condition(sample, screen, text, profile, b2_targets):
            continue
        exp_row = index.get((screen, text, profile))
        if exp_row is None or exp_row["status"] != STATUS_CO_PRESENT:
            continue

        baseline_score = int(baseline_row["score"] or 0)
        exp_score = int(exp_row["score"] or 0)

        if baseline_score == 1 and exp_score == 1:
            a += 1
        elif baseline_score == 1:
            b += 1
        elif exp_score == 1:
            c += 1
        else:
            d += 1

    return a, b, c, d


def power_flag(base_acc: float) -> str:
    """Classify a comparison's ability to detect degradation at all."""
    if base_acc < FLOOR_ACC_THRESHOLD:
        return "floor"
    if base_acc > CEILING_ACC_THRESHOLD:
        return "ceiling"
    return ""


def report_per_model(
    indices: dict[str, dict],
    profiles: list[str],
    sample: str = "full",
    b2_targets: frozenset[tuple[str, str]] = frozenset(),
) -> list[dict]:
    """Run per-model McNemar with Holm correction across the whole family."""
    print("\n" + "=" * 78)
    print(f"  SECTION 3 -- GROUNDING, PER MODEL  [SECONDARY]  [sample={sample}]")
    print(f"  McNemar on co-present targets. Holm-Bonferroni across all "
          f"{len(indices) * len(profiles)} tests.")
    print("=" * 78)

    rows = []
    raw = {}
    for model, index in indices.items():
        for profile in profiles:
            a, b, c, d = compute_contingency(index, profile, sample, b2_targets)
            total = a + b + c + d
            result = mcnemar_test(b, c)
            base_acc = (a + b) / total * 100 if total else 0.0
            exp_acc = (a + c) / total * 100 if total else 0.0
            diff, diff_low, diff_high = paired_difference_interval(a, b, c, d)
            odds, odds_low, odds_high = conditional_odds_ratio(b, c)

            key = f"{model}|{profile}"
            raw[key] = result["p_value"]
            rows.append({
                "sample": sample, "model": model, "profile": profile, "key": key,
                "a": a, "b": b, "c": c, "d": d, "total": total,
                "base_acc": base_acc, "exp_acc": exp_acc,
                "test": result["test"], "statistic": result["statistic"],
                "p_value": result["p_value"],
                "diff": diff, "diff_low": diff_low, "diff_high": diff_high,
                "odds": odds, "odds_low": odds_low, "odds_high": odds_high,
                "power": power_flag(base_acc),
            })

    corrected = holm_bonferroni(raw, ALPHA)

    header = (f"  {'Model':<24}{'Profile':<26}{'n':>5}{'base':>7}{'exp':>7}"
              f"{'b':>4}{'c':>4}{'p':>10}{'Holm':>9}  power    verdict")
    print(header)
    print("  " + "-" * (len(header) - 2))

    for row in rows:
        holm = corrected[row["key"]]
        row["holm_threshold"] = holm.threshold
        row["significant"] = holm.reject

        if holm.reject:
            verdict = "SIGNIFICANT"
        elif row["p_value"] < ALPHA:
            verdict = "sig uncorrected"
        elif row["power"]:
            verdict = f"inconclusive ({row['power']})"
        else:
            verdict = "ns"

        print(f"  {row['model']:<24}{row['profile']:<26}{row['total']:>5}"
              f"{row['base_acc']:>6.1f}%{row['exp_acc']:>6.1f}%"
              f"{row['b']:>4}{row['c']:>4}{row['p_value']:>10.5f}"
              f"{holm.threshold:>9.5f}  {row['power'] or '-':<8} {verdict}")

    if any(r["power"] == "ceiling" for r in rows):
        print(f"\n  NOTE  'ceiling' marks baseline accuracy > {CEILING_ACC_THRESHOLD:.0f}%,")
        print("        where almost nothing remains to break. Those nulls are")
        print("        underpowered, NOT evidence of resilience.")
    if any(r["power"] == "floor" for r in rows):
        print(f"\n  NOTE  'floor' marks baseline accuracy < {FLOOR_ACC_THRESHOLD:.0f}%,")
        print("        where most targets already fail before any distortion.")

    return rows


def report_sign_test(
    per_model_rows: list[dict],
    profiles: list[str],
    sample: str = "full",
) -> list[dict]:
    """Check that a pooled effect is consistent across models, not driven by one."""
    print("\n" + "=" * 78)
    print(f"  SECTION 4 -- DIRECTION CONSISTENCY ACROSS MODELS  [DESCRIPTIVE]  [sample={sample}]")
    print("  Models are not a random sample of a population, so this corroborates")
    print("  the pooled result rather than testing an independent hypothesis.")
    print("=" * 78)
    print(f"  {'Profile':<28}{'down':>6}{'up':>5}{'tied':>6}{'sign p':>10}")
    print(f"  {'-' * 28}{'-' * 6:>6}{'-' * 5:>5}{'-' * 6:>6}{'-' * 10:>10}")

    table = []
    for profile in profiles:
        rows = [r for r in per_model_rows if r["profile"] == profile]
        down = sum(1 for r in rows if r["b"] > r["c"])
        up = sum(1 for r in rows if r["c"] > r["b"])
        tied = sum(1 for r in rows if r["b"] == r["c"])
        p_value = sign_test(down, up)
        print(f"  {profile:<28}{down:>6}{up:>5}{tied:>6}{p_value:>10.5f}")
        table.append({
            "sample": sample, "profile": profile, "down": down, "up": up,
            "tied": tied, "p_value": p_value,
        })
    return table
