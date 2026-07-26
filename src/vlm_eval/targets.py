"""Target harvesting and profile label lookup for VLM evaluation."""

import json
from collections import Counter
from pathlib import Path


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
    """Return a target text element's bounding box from profile labels."""
    for rec in profile_labels:
        if rec.get("text") and rec["text"].strip() == target_text:
            return rec["box"]
    return None
