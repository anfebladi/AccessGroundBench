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


def harvest_targets(screen_name: str, labels_dir: Path) -> list[dict]:
    """
    Read baseline label JSON for a screen and extract non-empty text elements.

    Returns a list of dicts with 'text' and 'box' keys.
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

    targets = []
    for rec in records:
        text = rec.get("text")
        if text and text.strip():
            clean_text = text.strip()
            if text_counts[clean_text] == 1:
                targets.append({"text": clean_text, "baseline_box": rec["box"]})

    print(f"  [HARVEST] {len(targets)} unambiguous text targets from {baseline_path.name}")
    return targets


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

    match_kind is MATCH_EXACT when the rendered text is byte-identical to the
    baseline target string. It is MATCH_RELAXED when the exact lookup fails
    but a whitespace-normalized comparison succeeds, or one normalized string
    is a prefix of the other and both exceed MIN_RELAXED_MATCH_CHARS -- the
    shape of a reflow that truncated or re-worded a label without actually
    removing the element from the screen (see vlm_eval.targets module docs
    and CLAUDE.md re: label_changed).

    Exact match is checked first and independently, so it can never be
    shadowed by a coincidental relaxed match elsewhere in the layout.
    """
    for rec in profile_labels:
        text = rec.get("text")
        if text and text.strip() == target_text:
            return rec["box"], text.strip(), MATCH_EXACT

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
