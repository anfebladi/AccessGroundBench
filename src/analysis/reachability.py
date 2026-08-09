"""Model-independent reachability and label-change reporting."""
from __future__ import annotations
from collections import defaultdict

from evaluation.results import STATUS_LABEL_CHANGED, STATUS_OFF_SCREEN
from .samples import target_excluded_for_condition
from .stats import wilson_interval

LABEL_CHANGED_MODES = ("exclude", "unreachable", "reachable")
DEFAULT_LABEL_CHANGED_MODE = "unreachable"


def compute_reachability(
    index: dict,
    profile: str,
    label_changed_mode: str = DEFAULT_LABEL_CHANGED_MODE,
    sample: str = "full",
    b2_targets: frozenset[tuple[str, str]] = frozenset(),
) -> tuple[int, int]:
    """Count how many baseline targets still exist in a profile's layout.

    Returns (present, total). Model-independent: it depends only on which
    targets the capture found, never on a model's answer.
    """
    # label_changed_mode controls how STATUS_LABEL_CHANGED rows are counted
    # (see LABEL_CHANGED_MODES): "exclude" removes them from both present
    # and total (the target is dropped from the pool for this profile);
    # "unreachable" counts them in total but not present (the
    # pre-reclassification behaviour, since they used to be
    # indistinguishable from off_screen); "reachable" counts them in both.
    # All three are free -- reachability only needs presence, never a score.
    #
    # sample/b2_targets apply the sample's exclusions (see
    # target_excluded_for_condition): an excluded (target, profile) pair is
    # dropped from both present and total, same as
    # label_changed_mode="exclude" -- the target is removed from the pool
    # for this profile, not counted as unreachable.
    if label_changed_mode not in LABEL_CHANGED_MODES:
        raise ValueError(f"Unknown label_changed_mode: {label_changed_mode!r}")

    present = total = 0
    for (screen, text, prof) in index:
        if prof != "baseline":
            continue
        if target_excluded_for_condition(sample, screen, text, profile, b2_targets):
            continue
        row = index.get((screen, text, profile))
        if row is None:
            continue

        if row["status"] == STATUS_LABEL_CHANGED:
            if label_changed_mode == "exclude":
                continue
            total += 1
            if label_changed_mode == "reachable":
                present += 1
            continue

        total += 1
        if row["status"] != STATUS_OFF_SCREEN:
            present += 1
    return present, total


def report_reachability(
    index: dict,
    profiles: list[str],
    label_changed_mode: str = DEFAULT_LABEL_CHANGED_MODE,
    sample: str = "full",
    b2_targets: frozenset[tuple[str, str]] = frozenset(),
) -> list[dict]:
    """Print and return the reachability table for one model's captures."""
    print("\n" + "=" * 78)
    print(f"  SECTION 1 -- REACHABILITY (model-independent)  [sample={sample}]")
    print("  Share of baseline targets still present in the modified layout.")
    print(f"  label_changed rows counted as: {label_changed_mode}")
    print("=" * 78)
    print(f"  {'Profile':<28}{'Present':>9}{'Total':>7}{'Reachable':>12}   95% CI")
    print(f"  {'-' * 28}{'-' * 9:>9}{'-' * 7:>7}{'-' * 12:>12}   {'-' * 18}")

    table = []
    for profile in profiles:
        present, total = compute_reachability(
            index, profile, label_changed_mode, sample, b2_targets
        )
        rate = present / total if total else 0.0
        low, high = wilson_interval(present, total)
        print(f"  {profile:<28}{present:>9}{total:>7}{rate * 100:>11.1f}%   "
              f"[{low * 100:5.1f}%, {high * 100:5.1f}%]")
        table.append({
            "sample": sample, "profile": profile, "present": present, "total": total,
            "rate": rate, "ci_low": low, "ci_high": high,
        })
    return table


def report_label_changed_breakdown(index: dict, profiles: list[str]) -> list[dict]:
    """Print and return every STATUS_LABEL_CHANGED row: which target, under which profile, and what it now renders as.

    Deliberately only measures and reports; how label_changed targets should
    ultimately be treated in scoring is a separate decision this function
    does not make.
    """
    rows_out = []
    for (screen, text, profile), row in sorted(index.items()):
        if profile == "baseline" or row["status"] != STATUS_LABEL_CHANGED:
            continue
        matched = row.get("_label_changed_matched_text", "")
        rows_out.append({
            "screen": screen, "profile": profile,
            "baseline_text": text, "matched_text": matched,
        })

    print("\n" + "=" * 78)
    print("  SECTION 1b -- LABEL_CHANGED BREAKDOWN")
    print("  Elements still on screen whose label text no longer matches")
    print("  the baseline string exactly (relaxed match). Not queried, not")
    print("  scored -- reported here so the category is visible before any")
    print("  decision is made about how to treat it.")
    print("=" * 78)
    if not rows_out:
        print("  (none)")
        return rows_out

    by_screen_profile: dict[tuple[str, str], int] = defaultdict(int)
    for r in rows_out:
        by_screen_profile[(r["screen"], r["profile"])] += 1

    print(f"  {'Screen':<26}{'Profile':<24}{'Count':>7}")
    print(f"  {'-' * 26}{'-' * 24}{'-' * 7}")
    for (screen, profile), n in sorted(by_screen_profile.items()):
        print(f"  {screen:<26}{profile:<24}{n:>7}")

    print(f"\n  {len(rows_out)} label_changed row(s) total. Matched pairs:")
    for r in rows_out:
        base_safe = r["baseline_text"][:60].encode("ascii", "replace").decode("ascii")
        matched_safe = r["matched_text"][:60].encode("ascii", "replace").decode("ascii")
        print(f"    [{r['screen']}/{r['profile']}] {base_safe!r} -> {matched_safe!r}")

    return rows_out
