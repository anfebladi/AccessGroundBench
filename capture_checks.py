"""
capture_checks.py
-----------------
Empirical checks on captured assets.

A device setting can be accepted and still have no effect. These functions
verify the *observable outcome* of a profile in the pixels and the hierarchy,
rather than trusting that a write to a settings key did something:

  - mirror_ratio      did the layout actually flip for an RTL profile?
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

# Elements whose centre is within this many pixels of the screen's vertical
# midline are ignored by the mirror check: mirroring barely moves them, so they
# cannot distinguish a mirrored layout from an unmirrored one.
CENTRE_EXCLUSION_PX = 150

# How far a mirrored centre may sit from its predicted position and still count.
MIRROR_TOLERANCE_PX = 70

# Fraction of off-centre elements that must mirror for an RTL profile to pass.
MIRROR_PASS_RATIO = 0.5



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


def mirror_ratio(
    reference_labels: list[dict],
    rtl_labels: list[dict],
    screen_width: int,
) -> tuple[int, int]:
    """
    Compare a non-RTL capture with an RTL capture of the same screen.

    Returns (mirrored, comparable): how many shared off-centre text elements
    moved to their mirrored x position, out of how many were testable.

    An element at centre x should appear at (screen_width - x) once the layout
    direction flips. Centred elements are excluded because the mirror maps them
    onto themselves.
    """
    reference = text_boxes(reference_labels)
    rtl = text_boxes(rtl_labels)

    midline = screen_width / 2.0
    mirrored = comparable = 0

    for text in set(reference) & set(rtl):
        ref_box, rtl_box = reference[text], rtl[text]
        ref_centre = (ref_box[0] + ref_box[2]) / 2.0
        rtl_centre = (rtl_box[0] + rtl_box[2]) / 2.0

        if abs(ref_centre - midline) < CENTRE_EXCLUSION_PX:
            continue

        comparable += 1
        if abs(rtl_centre - (screen_width - ref_centre)) < MIRROR_TOLERANCE_PX:
            mirrored += 1

    return mirrored, comparable


def rtl_applied(
    reference_labels: list[dict],
    rtl_labels: list[dict],
    screen_width: int,
) -> tuple[bool, str]:
    """
    Decide whether an RTL capture really is mirrored.

    Returns (passed, human-readable detail). When no off-centre elements are
    shared the check cannot conclude, and reports that rather than passing.
    """
    mirrored, comparable = mirror_ratio(reference_labels, rtl_labels, screen_width)

    if comparable == 0:
        return False, "no shared off-centre elements to compare"

    ratio = mirrored / comparable
    detail = f"{mirrored}/{comparable} off-centre elements mirrored ({ratio:.0%})"
    return ratio >= MIRROR_PASS_RATIO, detail


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
