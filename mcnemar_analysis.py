"""
mcnemar_analysis.py
-------------------
Phase 4: statistical analysis of VLM grounding under accessibility profiles.

Reports three things, deliberately kept apart:

  1. REACHABILITY -- what fraction of baseline targets still exist in the
     modified layout. A property of Android under that setting, identical for
     every model, and no inferential statistics are required.

  2. GROUNDING, pooled (PRIMARY) -- cluster permutation test across all models
     on the targets present in both layouts.

  3. GROUNDING, per model (SECONDARY) -- McNemar per model x profile with
     Holm-Bonferroni correction, plus floor and ceiling checks.

Why 1 and 2 are separate: earlier revisions scored a target 0 when it was
absent from the modified layout, without ever querying the model, and counted
that as a grounding failure. "The element is not on screen" and "the model
looked in the wrong place" are different phenomena and must not share a cell in
the contingency table. Conflating them inflated significance from 4 tests to 24
and systematically penalised the most accurate models, because a target can
only be recorded as broken if the model got it right at baseline.

Usage:
  python mcnemar_analysis.py                              # all CSVs in dataset/
  python mcnemar_analysis.py --data-dir dataset/experiment_2
  python mcnemar_analysis.py --csv path/to/results.csv
  python mcnemar_analysis.py --compare-a vision.csv --compare-b tree.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

from vlm_eval.stats import (
    DEFAULT_PERMUTATIONS,
    cluster_permutation_test,
    conditional_odds_ratio,
    holm_bonferroni,
    mcnemar_test,
    paired_difference_interval,
    sign_test,
    wilson_interval,
)

PROJECT_ROOT = Path(__file__).parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "dataset"

ALPHA = 0.05

# Baseline accuracy below which McNemar cannot detect degradation: most targets
# already fail, so only (a + b) of them could ever break.
FLOOR_ACC_THRESHOLD = 50.0

# Baseline accuracy above which McNemar is equally uninformative in the other
# direction. At 99% there is almost nothing left to break, so a null result
# means "underpowered", not "resilient" -- the same error the floor check
# exists to prevent, mirrored at the top of the scale.
CEILING_ACC_THRESHOLD = 95.0

# elder_combo_rtl was dropped and renamed to elder_combo_mid: even with the
# correct RTL setting key, re-collection still measured 0% mirroring across
# every screen, so the profile is now honestly labelled as a second geometry
# condition (font 1.5 / density 480) rather than a mirroring condition. See
# dataset/experiment_2/README.md for the historical unverified arm.
EXPERIMENTAL_PROFILES = [
    "elder_text_heavy",
    "elder_zoom_heavy",
    "elder_combo_max",
    "elder_combo_mid",
    "colorblind_deuteranomaly",
]

# Row statuses. Only co_present rows carry a meaningful score.
STATUS_CO_PRESENT = "co_present"
STATUS_OFF_SCREEN = "off_screen"
STATUS_API_ERROR = "api_error"

# Prompt modes (see vlm_eval.results). Archived CSVs predate this column;
# treated as vision, matching what was actually run before tree mode existed.
PROMPT_MODE_VISION = "vision"
PROMPT_MODE_TREE = "tree"

# Suffix get_results_csv() (vlm_eval/config.py) appends to a tree-mode
# model's filename. Excluded from the default glob so a tree run can never
# be silently pooled into the vision-only pipeline as a phantom extra model
# -- the pooled permutation test and sign test both assume independent
# measurement streams, and vision/tree rows for the same model are maximally
# correlated, not independent.
WITH_TREE_SUFFIX = "_with_tree"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def derive_status(row: dict) -> str:
    """
    Determine a row's status, tolerating pre-status CSVs.

    Newer runs write an explicit `status` column. Archived runs
    (dataset/experiment_2/) predate it, so the status is recovered from the
    sentinel values the old runner wrote into `raw_response`.

    Note an unparseable reply is co_present, not a separate exclusion: the
    model was asked and answered, it just answered unusably, which is a genuine
    grounding failure rather than a missing measurement.
    """
    status = (row.get("status") or "").strip()
    if status:
        return status

    raw = row.get("raw_response", "")
    if raw == "[OFF-SCREEN]":
        return STATUS_OFF_SCREEN
    if raw.startswith("[API-ERROR"):
        return STATUS_API_ERROR
    return STATUS_CO_PRESENT


def load_results(csv_path: Path) -> list[dict]:
    """Load an evaluation CSV, normalising the status column.

    prompt_mode/tree_rows_sent were added after the archived experiment_2
    run, so older CSVs lack those columns entirely; default them to vision/0
    rather than letting downstream code see missing keys, so the archived
    dataset's regression reproduction (CLAUDE.md #9) keeps working unchanged.
    """
    if not csv_path.is_file():
        print(f"[ERROR] Results CSV not found: {csv_path}")
        sys.exit(1)

    with open(csv_path, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        row["status"] = derive_status(row)
        if not row.get("prompt_mode"):
            row["prompt_mode"] = PROMPT_MODE_VISION
        if not row.get("tree_rows_sent"):
            row["tree_rows_sent"] = "0"

    print(f"[LOADED] {len(rows)} rows from {csv_path.name}")
    return rows


def index_rows(rows: list[dict]) -> dict[tuple[str, str, str], dict]:
    """Index rows by (screen, target_text, profile)."""
    return {
        (r.get("screen", ""), r.get("target_text", ""), r.get("profile", "")): r
        for r in rows
    }


def model_name_from_path(csv_path: Path) -> str:
    """Recover the model id from an evaluation_results_*.csv filename."""
    name = csv_path.stem.replace("evaluation_results_", "")
    return "default" if name == "evaluation_results" else name


def discover_result_csvs(data_dir: Path, mode: str) -> list[Path]:
    """
    Find evaluation_results_*.csv files for one prompt-mode arm.

    Vision and tree results for the same model are correlated, not
    independent measurements (the tree run repeats the same queries with
    context added), so the default glob must never pool a model's *.csv with
    its *_with_tree.csv counterpart -- doing so would feed both arms into the
    pooled cluster permutation test and the sign test as if they were two
    independent models, silently doubling the effective sample.
    """
    all_csv_files = sorted(data_dir.glob("evaluation_results_*.csv"))
    if mode == "tree":
        return [p for p in all_csv_files if p.stem.endswith(WITH_TREE_SUFFIX)]
    return [p for p in all_csv_files if not p.stem.endswith(WITH_TREE_SUFFIX)]


# ---------------------------------------------------------------------------
# Section 1: reachability
# ---------------------------------------------------------------------------

def compute_reachability(index: dict, profile: str) -> tuple[int, int]:
    """
    Count how many baseline targets still exist in a profile's layout.

    Returns (present, total). Model-independent: it depends only on which
    targets the capture found, never on a model's answer.
    """
    present = total = 0
    for (screen, text, prof) in index:
        if prof != "baseline":
            continue
        row = index.get((screen, text, profile))
        if row is None:
            continue
        total += 1
        if row["status"] != STATUS_OFF_SCREEN:
            present += 1
    return present, total


def report_reachability(index: dict, profiles: list[str]) -> list[dict]:
    """Print and return the reachability table for one model's captures."""
    print("\n" + "=" * 78)
    print("  SECTION 1 -- REACHABILITY (model-independent)")
    print("  Share of baseline targets still present in the modified layout.")
    print("=" * 78)
    print(f"  {'Profile':<28}{'Present':>9}{'Total':>7}{'Reachable':>12}   95% CI")
    print(f"  {'-' * 28}{'-' * 9:>9}{'-' * 7:>7}{'-' * 12:>12}   {'-' * 18}")

    table = []
    for profile in profiles:
        present, total = compute_reachability(index, profile)
        rate = present / total if total else 0.0
        low, high = wilson_interval(present, total)
        print(f"  {profile:<28}{present:>9}{total:>7}{rate * 100:>11.1f}%   "
              f"[{low * 100:5.1f}%, {high * 100:5.1f}%]")
        table.append({
            "profile": profile, "present": present, "total": total,
            "rate": rate, "ci_low": low, "ci_high": high,
        })
    return table


# ---------------------------------------------------------------------------
# Section 2: pooled cluster permutation (primary)
# ---------------------------------------------------------------------------

def build_clusters(
    indices: dict[str, dict],
    profile: str,
) -> dict[tuple[str, str], list[tuple[int, int]]]:
    """
    Group paired outcomes by target across every model.

    One cluster is one (screen, target_text); its list holds that target's
    (baseline_score, profile_score) under each model. Only co_present rows in
    both arms are included.
    """
    clusters: dict[tuple[str, str], list[tuple[int, int]]] = defaultdict(list)

    for index in indices.values():
        for (screen, text, prof), baseline_row in index.items():
            if prof != "baseline" or baseline_row["status"] != STATUS_CO_PRESENT:
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
) -> list[dict]:
    """Run and print the pooled cluster permutation test for each profile."""
    print("\n" + "=" * 78)
    print("  SECTION 2 -- GROUNDING, POOLED ACROSS MODELS  [PRIMARY TEST]")
    print(f"  Cluster permutation, {permutations} draws, resampling unit = target.")
    print("  Co-present targets only. A target's outcomes across all models are")
    print("  relabelled together, preserving the correlation from target reuse.")
    print("=" * 78)

    raw = {}
    rows = []
    for profile in profiles:
        clusters = build_clusters(indices, profile)
        result = cluster_permutation_test(clusters, permutations, seed)
        raw[profile] = result["p_value"]
        rows.append({"profile": profile, **result})

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


# ---------------------------------------------------------------------------
# Section 3: per-model McNemar (secondary)
# ---------------------------------------------------------------------------

def compute_contingency(index: dict, profile: str) -> tuple[int, int, int, int]:
    """
    Build the 2x2 contingency table for baseline vs one profile.

    Restricted to co_present rows in both arms, so off-screen targets and API
    failures never enter the table.

    Returns (a, b, c, d):
      a both pass, b broke it, c fluke recovery, d both fail.
    """
    a = b = c = d = 0

    for (screen, text, prof), baseline_row in index.items():
        if prof != "baseline" or baseline_row["status"] != STATUS_CO_PRESENT:
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
) -> list[dict]:
    """Run per-model McNemar with Holm correction across the whole family."""
    print("\n" + "=" * 78)
    print("  SECTION 3 -- GROUNDING, PER MODEL  [SECONDARY]")
    print(f"  McNemar on co-present targets. Holm-Bonferroni across all "
          f"{len(indices) * len(profiles)} tests.")
    print("=" * 78)

    rows = []
    raw = {}
    for model, index in indices.items():
        for profile in profiles:
            a, b, c, d = compute_contingency(index, profile)
            total = a + b + c + d
            result = mcnemar_test(b, c)
            base_acc = (a + b) / total * 100 if total else 0.0
            exp_acc = (a + c) / total * 100 if total else 0.0
            diff, diff_low, diff_high = paired_difference_interval(a, b, c, d)
            odds, odds_low, odds_high = conditional_odds_ratio(b, c)

            key = f"{model}|{profile}"
            raw[key] = result["p_value"]
            rows.append({
                "model": model, "profile": profile, "key": key,
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


# ---------------------------------------------------------------------------
# Section 4: sign test across models
# ---------------------------------------------------------------------------

def report_sign_test(per_model_rows: list[dict], profiles: list[str]) -> list[dict]:
    """Check that a pooled effect is consistent across models, not driven by one."""
    print("\n" + "=" * 78)
    print("  SECTION 4 -- DIRECTION CONSISTENCY ACROSS MODELS  [DESCRIPTIVE]")
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
            "profile": profile, "down": down, "up": up,
            "tied": tied, "p_value": p_value,
        })
    return table


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------

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
) -> None:
    """Write the four result tables to CSV."""
    data_dir.mkdir(parents=True, exist_ok=True)

    reach_path = data_dir / "reachability_results.csv"
    with open(reach_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Profile", "Targets_Present", "Targets_Total",
                    "Reachability", "CI_Low", "CI_High"])
        for r in reachability:
            w.writerow([r["profile"], r["present"], r["total"],
                        _fmt(r["rate"], ".4f"), _fmt(r["ci_low"], ".4f"),
                        _fmt(r["ci_high"], ".4f")])

    pooled_path = data_dir / "pooled_permutation_results.csv"
    with open(pooled_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Profile", "Target_Clusters", "Observations", "Statistic",
                    "Broke_It_b", "Fluke_Recovery_c", "Permutations",
                    "P_Value", "Holm_Threshold", "Significant"])
        for r in pooled:
            w.writerow([r["profile"], r["n_clusters"], r["n_observations"],
                        _fmt(r["statistic"], ".1f"), r["b"], r["c"],
                        r["n_permutations"], _fmt(r["p_value"]),
                        _fmt(r["holm_threshold"]),
                        "Yes" if r["significant"] else "No"])

    per_model_path = data_dir / "mcnemar_results_per_model.csv"
    with open(per_model_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Model", "Profile", "Total_Pairs", "Both_Pass_a", "Broke_It_b",
                    "Fluke_Recovery_c", "Both_Fail_d", "Discordant_Pairs",
                    "Baseline_Acc", "Exp_Acc", "Risk_Diff", "Risk_Diff_CI_Low",
                    "Risk_Diff_CI_High", "Odds_Ratio", "OR_CI_Low", "OR_CI_High",
                    "Test_Used", "Statistic", "P_Value", "Holm_Threshold",
                    "Significant", "Power_Limit"])
        for r in per_model:
            w.writerow([
                r["model"], r["profile"], r["total"], r["a"], r["b"], r["c"], r["d"],
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
        w.writerow(["Profile", "Models_Down", "Models_Up", "Models_Tied", "Sign_P_Value"])
        for r in signs:
            w.writerow([r["profile"], r["down"], r["up"], r["tied"], _fmt(r["p_value"])])

    print("\n[WROTE]")
    for path in (reach_path, pooled_path, per_model_path, sign_path):
        print(f"  {path}")


# ---------------------------------------------------------------------------
# Cross-file comparison (vision-only vs tree-injected)
# ---------------------------------------------------------------------------

def run_cross_comparison(csv_a: Path, csv_b: Path, profiles: list[str]) -> None:
    """Compare two evaluation runs of the same profiles, target by target."""
    print("=" * 78)
    print("  CROSS-FILE COMPARISON")
    print(f"  A (vision-only): {csv_a.name}")
    print(f"  B (with tree):   {csv_b.name}")
    print("=" * 78)

    index_a = index_rows(load_results(csv_a))
    index_b = index_rows(load_results(csv_b))

    out_path = csv_a.parent / f"mcnemar_compare_{csv_a.stem.replace('evaluation_results_', '')}.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Profile", "Total_Pairs", "Both_Pass_a", "Tree_Hurt_b",
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
                if key[2] != profile or row_a["status"] != STATUS_CO_PRESENT:
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

            w.writerow([profile, total, a, b, c, d, b + c,
                        f"{acc_a:.1f}%", f"{acc_b:.1f}%", result["test"],
                        _fmt(result["statistic"], ".4f"),
                        _fmt(result["p_value"]),
                        "Yes" if result["p_value"] < ALPHA else "No"])

    print(f"\n[WROTE] {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="AccessGroundBench -- statistical analysis"
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR,
                        help="Directory holding evaluation_results_*.csv")
    parser.add_argument("--csv", type=Path, default=None,
                        help="Analyse a single evaluation CSV")
    parser.add_argument("--permutations", type=int, default=DEFAULT_PERMUTATIONS,
                        help="Permutation draws for the pooled test")
    parser.add_argument("--seed", type=int, default=0,
                        help="RNG seed for the permutation test")
    parser.add_argument("--compare-a", type=Path, default=None)
    parser.add_argument("--compare-b", type=Path, default=None)
    parser.add_argument("--mode", choices=["vision", "tree"], default="vision",
                        help="Which prompt-mode arm to analyse when discovering "
                             "CSVs from --data-dir (default: vision). Vision and "
                             "tree results for the same model are correlated, not "
                             "independent measurements, so they are never pooled "
                             "together automatically -- use --compare-a/--compare-b "
                             "for a paired vision-vs-tree comparison instead.")
    args = parser.parse_args()

    profiles = list(EXPERIMENTAL_PROFILES)

    if bool(args.compare_a) != bool(args.compare_b):
        print("[ERROR] --compare-a and --compare-b must be given together.")
        sys.exit(1)

    if args.compare_a and args.compare_b:
        run_cross_comparison(args.compare_a, args.compare_b, profiles)
        return

    if args.csv:
        csv_files = [args.csv]
        data_dir = args.csv.parent
    else:
        data_dir = args.data_dir
        csv_files = discover_result_csvs(data_dir, args.mode)
        if not csv_files:
            print(f"[ERROR] No evaluation_results_*.csv files for mode={args.mode!r} "
                  f"found in {data_dir}")
            sys.exit(1)

    print("=" * 78)
    print("  AccessGroundBench -- Statistical Analysis")
    print(f"  Data dir : {data_dir}")
    print(f"  Mode     : {args.mode}")
    print(f"  Models   : {len(csv_files)}")
    for path in csv_files:
        print(f"             {path.name}")
    print(f"  Profiles : {', '.join(profiles)}")
    print(f"  alpha    : {ALPHA} (Holm-Bonferroni corrected)")
    print("=" * 78)

    indices = {
        model_name_from_path(path): index_rows(load_results(path))
        for path in csv_files
    }

    # Reachability depends only on the captures, so any one model's rows show it.
    first_index = next(iter(indices.values()))

    # A profile can be in EXPERIMENTAL_PROFILES but absent from this specific
    # dataset -- e.g. an archived run predating a profile rename, or a
    # --screens subset. Without this filter every section below would print a
    # spurious present=0/total=0 "0.0%" row for it, which reads as "measured
    # and found unreachable" rather than "never captured here".
    available_profiles = {prof for (_screen, _text, prof) in first_index}
    missing_profiles = [p for p in profiles if p not in available_profiles]
    profiles = [p for p in profiles if p in available_profiles]
    if missing_profiles:
        print(f"  Skipped  : {', '.join(missing_profiles)} "
              f"(no captures for this profile in {data_dir})")

    reachability = report_reachability(first_index, profiles)

    pooled = report_pooled(indices, profiles, args.permutations, args.seed)
    per_model = report_per_model(indices, profiles)
    signs = report_sign_test(per_model, profiles)

    write_outputs(data_dir, reachability, pooled, per_model, signs)
    print()


if __name__ == "__main__":
    main()
