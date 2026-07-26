"""Ferret-UI provider adapter.

Ferret-UI uses a local HTTP endpoint and is trained to return normalized
bounding boxes rather than the pixel coordinates requested by hosted models.
This module keeps that model-specific protocol separate from the LiteLLM path.
"""

import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

FERRET_SERVER_URL = "http://localhost:8000/"
FERRET_BBOX_REGEX = re.compile(r"\[\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]\]")


class FerretProviderError(RuntimeError):
    """Raised when the local Ferret-UI provider cannot serve a request."""


def _ferret_bbox_to_coordinates(ferret_text: Any, image_path: Path) -> str:
    """Convert Ferret's normalized bbox response into canonical [x, y] text."""
    if not isinstance(ferret_text, str):
        return "" if ferret_text is None else str(ferret_text)

    bbox_match = FERRET_BBOX_REGEX.search(ferret_text)
    if bbox_match is None:
        return ferret_text

    try:
        from PIL import Image

        with Image.open(image_path) as image:
            width, height = image.size
    except (FileNotFoundError, OSError, ValueError):
        width, height = 1000, 1000

    x1, y1, x2, y2 = map(float, bbox_match.groups())
    x_center = ((x1 + x2) / 2.0 / 1000.0) * width
    y_center = ((y1 + y2) / 2.0 / 1000.0) * height
    return f"[{x_center:.1f}, {y_center:.1f}]"


def call_ferret_ui(image_path: Path, target_text: str) -> str:
    """Request a text-element bbox from the local Ferret-UI server."""
    if not target_text:
        raise ValueError("target_text is required for the Ferret-UI provider")

    payload = {
        "image_path": str(image_path),
        "prompt": f"Provide the bounding box of the text '{target_text}'.",
    }
    request = urllib.request.Request(
        FERRET_SERVER_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise FerretProviderError(
            "Could not connect to the Ferret-UI inference server. "
            "Start ferret_ui.ferret_server and wait for the model to load "
            f"({FERRET_SERVER_URL})"
        ) from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        raise FerretProviderError(
            f"Ferret-UI returned an invalid response ({FERRET_SERVER_URL})"
        ) from exc

    if not isinstance(result, dict) or "text" not in result:
        raise FerretProviderError(
            f"Ferret-UI response is missing the 'text' field ({FERRET_SERVER_URL})"
        )

    return _ferret_bbox_to_coordinates(result["text"], image_path)
