"""Coordinate parsing and bounding-box scoring helpers."""

import json
import math
from numbers import Real



def parse_coordinates(response_text: str) -> tuple[float, float]:
    """Parse exactly two finite numeric values from a JSON array response."""
    try:
        coordinates = json.loads(response_text)
    except (json.JSONDecodeError, TypeError):
        return -1.0, -1.0

    if (
        not isinstance(coordinates, list)
        or len(coordinates) != 2
        or any(
            isinstance(value, bool)
            or not isinstance(value, Real)
            or not math.isfinite(value)
            for value in coordinates
        )
    ):
        return -1.0, -1.0

    return float(coordinates[0]), float(coordinates[1])


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
