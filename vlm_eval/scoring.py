"""Coordinate parsing and bounding-box scoring helpers."""

import re

COORD_REGEX = re.compile(r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)")


def parse_coordinates(response_text: str) -> tuple[float, float]:
    """Extract (x, y) coordinates from model response text."""
    match = COORD_REGEX.search(response_text)
    if match:
        return float(match.group(1)), float(match.group(2))
    return -1.0, -1.0


def to_pixel_space(
    x: float,
    y: float,
    img_width: int,
    img_height: int,
    coord_space: str = "pixel",
) -> tuple[float, float]:
    """Convert a model's raw coordinates into absolute image pixels.

    "pixel" answers are already absolute and pass through unchanged.
    "norm1000" answers sit on a 0-1000 grid independent of image size and are
    scaled by the real dimensions. Mirrors the conversion the Ferret-UI branch
    of vlm_provider already applies to its own 1000-scale output.
    """
    if coord_space == "norm1000":
        return x / 1000.0 * img_width, y / 1000.0 * img_height
    return x, y


def hit_test(x_pred: int, y_pred: int, box: list[int], baseline_box: list[int] | None = None) -> int:
    """
    Return 1 when a predicted point hits the target.
    If baseline_box is provided, enforces constant strictness by applying the
    baseline dimensions centered at the current altered box's location.
    """
    if baseline_box is not None:
        # Constant strictness: use baseline size, but current center
        w_base = baseline_box[2] - baseline_box[0]
        h_base = baseline_box[3] - baseline_box[1]
        
        cx = (box[0] + box[2]) / 2.0
        cy = (box[1] + box[3]) / 2.0
        
        if abs(x_pred - cx) <= (w_base / 2.0) and abs(y_pred - cy) <= (h_base / 2.0):
            return 1
        return 0
    else:
        # Fallback to standard bounds check
        x_min, y_min, x_max, y_max = box
        if x_min <= x_pred <= x_max and y_min <= y_pred <= y_max:
            return 1
        return 0
