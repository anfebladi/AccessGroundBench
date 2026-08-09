"""Target harvesting and profile label lookup for VLM evaluation."""

import json
import re
from collections import Counter
from pathlib import Path

# Match kinds returned by locate_element, in decreasing order of confidence.
MATCH_EXACT = "exact"
MATCH_RELAXED = "relaxed"

# Invisible/exotic whitespace Android layouts embed freely, which reflow can
# add or drop without changing what a user sees: non-breaking space, narrow
# and thin no-break spaces, zero-width space, and the combining grapheme
# joiner (Gmail pads its preview text with runs of this one).
_INVISIBLE_CHARS = "   ​͏"
_INVISIBLE_RE = re.compile(f"[{_INVISIBLE_CHARS}]")
_WHITESPACE_RE = re.compile(r"\s+")

# A relaxed match additionally requires one string to be a prefix of the
# other, and only once both exceed this length. Below it, short labels
# collide by coincidence -- "Color" is a genuine prefix of "Colors", and both
# are real, independent targets on settings_display.
MIN_RELAXED_MATCH_CHARS = 20

# A harvested text this long is not a rendered on-screen label a model could
# plausibly be asked to tap: Android list rows (e.g. Gmail's conversation
# items) synthesize a single `text` attribute concatenating sender, subject,
# and full preview body onto one node for accessibility narration, well past
# anything actually visible as one string.
MAX_TARGET_CHARS = 100


def normalize_label(text: str) -> str:
    """Collapse the whitespace differences reflow introduces into a label.

    Strips invisible padding characters and collapses whitespace runs, so
    labels that differ only by an inserted non-breaking space or a run of
    joiner characters compare equal. Deliberately does NOT casefold or strip
    punctuation: a label whose wording actually changed is a different
    rendered string, and hiding that would defeat the point of this check.
    """
    if not text:
        return ""
    return _WHITESPACE_RE.sub(" ", _INVISIBLE_RE.sub(" ", text)).strip()


def box_contains(outer: list[int], inner: list[int]) -> bool:
    """True when `outer` fully encloses `inner` (and they are not the same box)."""
    return (
        outer[0] <= inner[0] and outer[1] <= inner[1]
        and outer[2] >= inner[2] and outer[3] >= inner[3]
        and outer != inner
    )


def invalid_targets(candidates: list[dict]) -> set[str]:
    """Return the text of candidates that are not real groundable targets.

    A candidate is invalid if its text exceeds MAX_TARGET_CHARS, or if its box
    fully encloses another candidate's box on the same screen. Both are the
    shape of a row-container node: a whole-row label (e.g. Gmail's
    conversation-item text, which concatenates sender, subject, and full
    preview body) that encloses its own sender/subject/preview children,
    which are already separate, individually-visible targets. Querying the
    container as its own target would ask a model to locate a string that is
    not what is actually rendered as one label on screen.
    """
    invalid: set[str] = set()
    for cand in candidates:
        text = cand["text"]
        box = cand["baseline_box"]
        if len(text) > MAX_TARGET_CHARS:
            invalid.add(text)
            continue
        if any(
            box_contains(box, other["baseline_box"])
            for other in candidates
            if other["text"] != text
        ):
            invalid.add(text)
    return invalid


def harvest_targets(screen_name: str, labels_dir: Path) -> list[dict]:
    """
    Read baseline label JSON for a screen and extract non-empty text elements.

    Returns a list of dicts with 'text' and 'baseline_box' keys.
    """
    baseline_path = labels_dir / f"{screen_name}_baseline.json"
    if not baseline_path.is_file():
        print(f"[WARN] Baseline labels not found: {baseline_path}")
        return []

    with open(baseline_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    text_counts = Counter()
    for rec in records:
        text = rec.get("text")
        if text and text.strip():
            text_counts[text.strip()] += 1

    candidates = []
    for rec in records:
        text = rec.get("text")
        if text and text.strip():
            clean_text = text.strip()
            if text_counts[clean_text] == 1:
                candidates.append({"text": clean_text, "baseline_box": rec["box"]})

    excluded = invalid_targets(candidates)
    targets = [cand for cand in candidates if cand["text"] not in excluded]

    excluded_note = f" ({len(excluded)} excluded: not groundable text)" if excluded else ""
    print(f"  [HARVEST] {len(targets)} unambiguous text targets from "
          f"{baseline_path.name}{excluded_note}")
    return targets


def build_expected_keys(
    screens: list[str],
    labels_dir: Path,
    profiles: list[str],
) -> list[tuple[str, str, str]]:
    """
    Build the canonical (screen, target_text, profile) key list for a collection.

    Order is screen (as given) outer, profile (as given) middle, target
    (harvest order) inner -- this is the single canonical ordering that
    evaluation.results.prepare_csv/finalize_csv sort result rows into, so a
    fresh collection and a repaired one are byte-comparable rather than
    differing by whatever order resume history happened to produce.

    Every key here is guaranteed queryable at collection time (every target
    comes from harvest_targets, which already excludes duplicated and
    non-groundable text). A row whose key is not in this set is stale --
    either the target set changed since collection (see invalid_targets) or
    the row is otherwise not a real measurement -- and gets dropped when a
    results CSV is canonicalized against it.
    """
    keys: list[tuple[str, str, str]] = []
    for screen in screens:
        targets = harvest_targets(screen, labels_dir)
        for profile in profiles:
            for target in targets:
                keys.append((screen, target["text"], profile))
    return keys


def find_element_in_profile(
    profile_labels: list[dict],
    target_text: str,
) -> list[int] | None:
    """Return a target text element's bounding box from profile labels.

    Exact match only. Kept as a thin wrapper around locate_element for
    callers that only care whether the box exists, not how it was found.
    """
    match = locate_element(profile_labels, target_text)
    return match[0] if match else None


def locate_element(
    profile_labels: list[dict],
    target_text: str,
) -> tuple[list[int], str, str] | None:
    """Find a target's element in a profile's labels, exact or relaxed.

    Returns (box, matched_text, match_kind) or None if nothing plausibly
    corresponds to target_text in this profile.
    """
    # Exact match is checked first and independently, so it can never be
    # shadowed by a coincidental relaxed match elsewhere in the layout.
    for rec in profile_labels:
        text = rec.get("text")
        if text and text.strip() == target_text:
            return rec["box"], text.strip(), MATCH_EXACT

    # match_kind is MATCH_RELAXED when the exact lookup above fails but a
    # whitespace-normalized comparison succeeds, or one normalized string
    # is a prefix of the other and both exceed MIN_RELAXED_MATCH_CHARS --
    # the shape of a reflow that truncated or re-worded a label without
    # actually removing the element from the screen.

    target_norm = normalize_label(target_text)
    if not target_norm:
        return None

    for rec in profile_labels:
        text = rec.get("text")
        if not text:
            continue
        candidate_norm = normalize_label(text)
        if not candidate_norm:
            continue
        if candidate_norm == target_norm:
            return rec["box"], text.strip(), MATCH_RELAXED
        if (
            len(target_norm) >= MIN_RELAXED_MATCH_CHARS
            and len(candidate_norm) >= MIN_RELAXED_MATCH_CHARS
            and (
                candidate_norm.startswith(target_norm)
                or target_norm.startswith(candidate_norm)
            )
        ):
            return rec["box"], text.strip(), MATCH_RELAXED

    return None
