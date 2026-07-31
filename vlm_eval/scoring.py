"""Coordinate parsing and bounding-box scoring helpers."""

import re
import struct
from pathlib import Path


def get_png_dimensions(image_path: str | Path) -> tuple[int, int]:
    """Extract width and height from a PNG file without external libraries.

    Lives here (no external deps) rather than in vlm_eval.runner so
    mcnemar_analysis.py can reuse it for offline box-vs-image checks without
    importing vlm_provider's litellm dependency chain.
    """
    with open(image_path, "rb") as f:
        f.read(16)
        width, height = struct.unpack(">II", f.read(8))
        return width, height

# Bracketed pair, e.g. "[540, 300]" -- the format the prompt asks for. Tried
# first because a loose scan can latch onto an earlier incidental pair: a reply
# like "row 3, column 2 ... so [540, 300]" would otherwise score (3, 2).
BRACKET_REGEX = re.compile(
    r"[\[(]\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*[\])]"
)

# Fallback: the first bare "number, number" anywhere in the reply.
COORD_REGEX = re.compile(r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)")

# Parse method labels, recorded per row so parse quality stays auditable.
PARSE_BRACKET = "bracket"
PARSE_LOOSE = "loose"
PARSE_FAILED = "failed"


def parse_coordinates_detailed(response_text: str) -> tuple[float, float, str]:
    """
    Extract (x, y) from a model reply, reporting which pattern matched.

    Returns (x, y, method). On failure returns (-1.0, -1.0, PARSE_FAILED).
    """
    match = BRACKET_REGEX.search(response_text)
    if match:
        return float(match.group(1)), float(match.group(2)), PARSE_BRACKET

    match = COORD_REGEX.search(response_text)
    if match:
        return float(match.group(1)), float(match.group(2)), PARSE_LOOSE

    return -1.0, -1.0, PARSE_FAILED


def parse_coordinates(response_text: str) -> tuple[float, float]:
    """Extract (x, y) coordinates from model response text."""
    x_coord, y_coord, _ = parse_coordinates_detailed(response_text)
    return x_coord, y_coord


TOLERANCE = 30

def hit_test(x_pred: int, y_pred: int, box: list[int], baseline_box: list[int] | None = None) -> int:
    """
    Return 1 when a predicted point hits the target.
    If baseline_box is provided, enforces constant strictness by applying the
    baseline dimensions centered at the current altered box's location.
    Adds a touch tolerance to simulate realistic mobile tap targets.
    """
    if baseline_box is not None:
        # Constant strictness: use baseline size, but current center
        w_base = baseline_box[2] - baseline_box[0] + (TOLERANCE * 2)
        h_base = baseline_box[3] - baseline_box[1] + (TOLERANCE * 2)

        cx = (box[0] + box[2]) / 2.0
        cy = (box[1] + box[3]) / 2.0

        if abs(x_pred - cx) <= (w_base / 2.0) and abs(y_pred - cy) <= (h_base / 2.0):
            return 1
        return 0
    else:
        # Fallback to standard bounds check
        x_min, y_min, x_max, y_max = box
        if (x_min - TOLERANCE) <= x_pred <= (x_max + TOLERANCE) and \
           (y_min - TOLERANCE) <= y_pred <= (y_max + TOLERANCE):
            return 1
        return 0
