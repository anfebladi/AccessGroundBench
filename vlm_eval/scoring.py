"""Coordinate parsing and bounding-box scoring helpers."""

import re

COORD_REGEX = re.compile(r"(\d+)\s*,\s*(\d+)")


def parse_coordinates(response_text: str) -> tuple[int, int]:
    """Extract (x, y) coordinates from model response text."""
    match = COORD_REGEX.search(response_text)
    if match:
        return int(match.group(1)), int(match.group(2))
    return -1, -1


def hit_test(x_pred: int, y_pred: int, box: list[int]) -> int:
    """Return 1 when a predicted point is inside the bounding box, else 0."""
    x_min, y_min, x_max, y_max = box
    if x_min <= x_pred <= x_max and y_min <= y_pred <= y_max:
        return 1
    return 0
