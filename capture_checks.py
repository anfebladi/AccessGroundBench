"""
capture_checks.py
-----------------
Empirical checks on captured assets.

A device setting can be accepted and still have no effect. These functions
verify the *observable outcome* of a profile in the pixels and the hierarchy,
rather than trusting that a write to a settings key did something:

  - text_drift        did the app's own content change between two captures?
  - image_difference  how far apart are two captures, in pixels?

The colour transform is verified inside screenshot_pipeline instead, by
comparing the image before and after the matrix is applied. Diffing a filtered
capture against a separate baseline capture cannot work: the delta depends on
how colourful the screen is (a green-weak transform barely moves a dark UI) and
is contaminated by the app changing its own content between the two captures.

All three are pure functions over saved files, so they are unit-testable
without an emulator.
"""

from __future__ import annotations

import json
from pathlib import Path


def load_labels(path: str | Path) -> list[dict]:
    """Read a bound_extractor label JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def text_boxes(labels: list[dict]) -> dict[str, list[int]]:
    """Map non-empty text to its bounding box, keeping the first occurrence."""
    boxes: dict[str, list[int]] = {}
    for record in labels:
        text = record.get("text")
        if not text or not text.strip():
            continue
        boxes.setdefault(text.strip(), record["box"])
    return boxes


def image_difference(png_a: str | Path, png_b: str | Path) -> float:
    """
    Mean absolute per-channel difference between two PNGs, in 0-255 units.

    Returns 0.0 when the images differ in size, since a size change already
    means the captures are not comparable pixel-for-pixel.
    """
    from PIL import Image, ImageChops, ImageStat

    with Image.open(png_a) as image_a, Image.open(png_b) as image_b:
        first = image_a.convert("RGB")
        second = image_b.convert("RGB")
        if first.size != second.size:
            return 0.0
        stat = ImageStat.Stat(ImageChops.difference(first, second))
    return sum(stat.mean) / len(stat.mean)


def text_drift(labels_a: list[dict], labels_b: list[dict]) -> tuple[set[str], set[str]]:
    """
    Compare the text content of two captures.

    Returns (vanished, appeared) -- texts present only in A, and only in B.
    """
    texts_a = set(text_boxes(labels_a))
    texts_b = set(text_boxes(labels_b))
    return texts_a - texts_b, texts_b - texts_a


def drift_rate(labels_a: list[dict], labels_b: list[dict]) -> float:
    """
    Share of A's texts that changed between two captures of the same screen.

    Run against two baseline captures bracketing a screen's profile sweep, this
    is the empirical noise floor: any measured effect smaller than the drift
    rate cannot be distinguished from the app changing its own content.
    """
    texts_a = set(text_boxes(labels_a))
    if not texts_a:
        return 0.0
    vanished, appeared = text_drift(labels_a, labels_b)
    return len(vanished | appeared) / len(texts_a)
