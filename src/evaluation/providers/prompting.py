"""Normalized-coordinate prompt construction and reply policy."""

import re
from pathlib import Path

from .config import uses_normalized_coords

GEMINI_VOCAB_SIZE = 1000
GEMINI_SPACE_NORMALIZED = "normalized"
GEMINI_SPACE_PIXEL = "pixel"
GEMINI_SPACE_UNVERIFIED = "unverified"
_GEMINI_COORD_RE = re.compile(
    r"[\[(]\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*[\])]"
)
_TARGET_TEXT_RE = re.compile(r"click on the text element:\s*'([^']+)'")

def extract_target_from_prompt(prompt: str) -> str | None:
    """
    Best-effort fallback: recover the target text from a rendered prompt.

    Used only when a caller does not pass target_text explicitly. Apostrophes
    in the target text truncate this extraction, which is why every in-repo
    caller now passes target_text directly instead of relying on it.
    """
    match = _TARGET_TEXT_RE.search(prompt)
    return match.group(1) if match else None


def resolve_image_dims(
    image_path: Path, img_width: int | None, img_height: int | None
) -> tuple[int, int]:
    """Return (width, height), reading the PNG directly when not already known."""
    if img_width is not None and img_height is not None:
        return img_width, img_height

    from PIL import Image

    with Image.open(image_path) as img:
        return img.size


def build_normalized_prompt(
    target_text: str,
    tree_rows: list[tuple[str, list[int]]] | None,
    img_width: int,
    img_height: int,
    strict: bool = False,
) -> str:
    """
    Build the prompt for models with a native normalized coordinate convention.

    These models answer in 0-1000 normalized space regardless of what the
    prompt asks for (see GEMINI_VOCAB_SIZE) -- restating "pixel" harder does
    not fix that, since they are not confused about the instruction, they are
    applying their own trained output convention. So instead of asking for
    pixels and converting nothing, this asks for what the model already wants
    to give -- a 0-1000 point with a worked example anchored to this image's
    actual dimensions -- and the runner converts the reply back to pixels
    afterward, using the space resolved for that individual reply.

    strict=True adds one more corrective sentence, used only when a prior
    attempt in the same call_vlm retry loop came back in pixel space anyway.
    """
    lines = [
        "You are an autonomous mobile agent navigating an Android user interface.",
        f"Look closely at this image. This image is {img_width} x {img_height} pixels.",
    ]
    if tree_rows:
        tree_text = "\n".join(
            f'- "{label}" [{x1},{y1}][{x2},{y2}]'
            for label, (x1, y1, x2, y2) in tree_rows
        )
        lines.append(
            "You are also given a partial accessibility tree listing some "
            "on-screen elements with their pixel bounds in the format "
            f"[x1,y1][x2,y2]:\n{tree_text}\nThe target element may not appear "
            "in this tree; use the surrounding elements' positions as "
            "spatial reference and the image to locate it."
        )
    instruction = (
        f"Locate the text element: '{target_text}'. Report its centre point "
        "on a 0-1000 NORMALIZED scale, where [0, 0] is the top-left corner "
        "and [1000, 1000] is the bottom-right corner of the image -- NOT "
        "raw pixel coordinates. For example, the exact centre of this image "
        f"is [500, 500] regardless of its {img_width}x{img_height} pixel "
        "size. Return your response strictly in the bracket format: [x, y]"
    )
    if strict:
        instruction += (
            " Your previous answer used raw pixel coordinates, which is "
            "wrong for this request -- rescale your answer to the 0-1000 "
            "range before replying."
        )
    lines.append(instruction)
    return "\n".join(lines)


def classify_normalized_reply(raw_text: str) -> str:
    """
    Decide which coordinate space a normalized-convention model actually used.

    Returns one of GEMINI_SPACE_*. A value > GEMINI_VOCAB_SIZE (or negative) on
    either axis is unambiguous pixel-space non-compliance -- nothing on a 0-1000
    scale can produce it -- so it is reported as PIXEL for the caller to retry
    or flag. Anything in range is trusted as NORMALIZED. An unparseable reply is
    UNVERIFIED.

    Classification only. The reply text is returned to the caller verbatim and
    the pixel conversion happens in the runner (evaluation.scoring.to_pixel_space),
    driven by the space this returns. Converting here instead would discard the
    model's original answer, which is what made the already-collected Gemini
    rows impossible to re-score offline.

    A pixel-space reply whose values also happen to fall inside 0-1000 (the
    top-left ~45% of these screens) is indistinguishable from a genuinely
    normalized reply from the text alone -- this is a stated limitation, not
    a bug: see CLAUDE.md and the plan's "Compliance check and retry" section.
    """
    match = _GEMINI_COORD_RE.search(raw_text)
    if not match:
        return GEMINI_SPACE_UNVERIFIED

    x, y = float(match.group(1)), float(match.group(2))
    if x > GEMINI_VOCAB_SIZE or y > GEMINI_VOCAB_SIZE or x < 0 or y < 0:
        return GEMINI_SPACE_PIXEL

    return GEMINI_SPACE_NORMALIZED
