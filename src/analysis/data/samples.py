"""Named exclusion samples and target-validity policy."""
from __future__ import annotations
from collections import defaultdict

from evaluation.storage.results import STATUS_CO_PRESENT
from evaluation.grounding.targets import MAX_TARGET_CHARS, box_contains

_FONT_DENSITY_PROFILES = (
    "elder_text_heavy", "elder_zoom_heavy", "elder_combo_max", "elder_combo_mid",
)
B1_MINIMAL: frozenset[tuple[str, str]] = frozenset({
    ("settings_display", "colorblind_deuteranomaly"),
})
B1_PRECAUTIONARY: frozenset[tuple[str, str]] = B1_MINIMAL | frozenset({
    (screen, profile)
    for screen in ("settings_display", "settings_accessibility")
    for profile in _FONT_DENSITY_PROFILES
})
B1_UNIFORM: frozenset[tuple[str, str]] = frozenset({
    (screen, profile)
    for screen in ("settings_display", "settings_accessibility")
    for profile in (*_FONT_DENSITY_PROFILES, "colorblind_deuteranomaly")
})
B2_LENGTH_CAP = MAX_TARGET_CHARS
SAMPLES: dict[str, dict] = {
    "full":          {"b1": frozenset(), "b2": False},
    "primary":       {"b1": B1_MINIMAL, "b2": True},
    "precautionary": {"b1": B1_PRECAUTIONARY, "b2": True},
    "uniform":       {"b1": B1_UNIFORM, "b2": True},
}
SAMPLE_NAMES = list(SAMPLES)
DEFAULT_SAMPLE = "primary"


def compute_b2_targets(baseline_rows: list[dict]) -> frozenset[tuple[str, str]]:
    """
    Compute B2's excluded (screen, target_text) set from this run's own
    baseline rows, rather than hardcoding target strings -- so it reproduces
    correctly against any dataset (a different collection run's Gmail
    content, or the archived experiment_2) instead of silently excluding
    nothing on data it was not written against.

    Excludes a target when it is a container whose box fully encloses another
    target's box on the same screen, or when its text exceeds B2_LENGTH_CAP
    characters. Both are the shape of Gmail's row-level nodes: a whole-email
    summary crammed into one label, enclosing its own sender/subject/preview
    as separate targets.
    """
    by_screen: dict[str, list[tuple[str, list[int]]]] = defaultdict(list)
    for r in baseline_rows:
        if r.get("status") != STATUS_CO_PRESENT:
            continue
        try:
            box = [int(r[k]) for k in ("x_min", "y_min", "x_max", "y_max")]
        except (KeyError, ValueError):
            continue
        by_screen[r["screen"]].append((r["target_text"], box))

    excluded: set[tuple[str, str]] = set()
    for screen, items in by_screen.items():
        for text, box in items:
            if len(text) > B2_LENGTH_CAP:
                excluded.add((screen, text))
                continue
            if any(box_contains(box, other_box) for other_text, other_box in items
                   if other_text != text):
                excluded.add((screen, text))
    return frozenset(excluded)


def target_excluded_for_condition(
    sample: str,
    screen: str,
    target_text: str,
    profile: str,
    b2_targets: frozenset[tuple[str, str]],
) -> bool:
    """True when (target, profile) should be dropped from `sample`'s pool for this one condition's tables."""
    if sample not in SAMPLES:
        raise ValueError(f"Unknown sample: {sample!r}")
    # B2 applies to a target across every condition, baseline included --
    # the target itself is task-invalid regardless of what it is compared
    # against, so this check does not depend on `profile`.
    if (screen, target_text) in b2_targets and SAMPLES[sample]["b2"]:
        return True
    # B1 applies only to the named (screen, profile) cell: the same target's
    # baseline reading, and its readings under every other condition, are
    # unaffected -- settings_display is contaminated under
    # colorblind_deuteranomaly specifically, not under every condition it
    # appears in.
    return (screen, profile) in SAMPLES[sample]["b1"]
