"""Single-query smoke test for a model, run before committing to a full evaluation.

A bring-your-own model has two failure modes that only surface after burning
the whole run: a missing/invalid API key (call_vlm raises immediately, but
only once evaluate_screen() is already deep in its loop), and a model that
answers on a 0-1000 normalized grid the evaluator does not recognise as such
(evaluation.providers.config.uses_normalized_coords matches on a fixed
substring tuple, so an unrecognised normalized model silently scores near 0%
because its reply is scored as if it were absolute pixels).

smoke_test_model sends exactly one query -- the same prompt shape a real run
would send, against a real baseline image and target -- and reports what
actually happened: the raw reply, the parsed point, whether that point looks
like it is on a 0-1000 grid rather than pixels, and whether it would have hit
the target. This is what backs the UI's "Test model" button, and it is also
directly usable from a shell for anyone not using the UI.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from .config import IMAGES_DIR, LABELS_DIR
from .grounding.scoring import hit_test, parse_coordinates_detailed, to_pixel_space
from .grounding.targets import harvest_targets, locate_element
from .grounding.task_prompting import PROMPT_TEMPLATE
from .providers import call_vlm
from .providers.coord_prompting import classify_normalized_reply
from .providers.config import uses_normalized_coords


@dataclass
class SmokeTestResult:
    """Outcome of one test query against one model."""

    ok: bool
    model: str
    screen: str
    target_text: str
    image_path: Path | None = None
    prompt: str | None = None
    raw_response: str | None = None
    x_pred: float | None = None
    y_pred: float | None = None
    box: list[int] | None = None
    hit: int | None = None
    latency_seconds: float | None = None
    coord_space_detected: str | None = None
    coord_space_used: str | None = None
    coord_space_mismatch: bool = False
    error: str | None = None


def _pick_target(screen_name: str, labels_dir: Path) -> dict | None:
    """Return one harvestable baseline target for screen_name, or None."""
    targets = harvest_targets(screen_name, labels_dir)
    return targets[0] if targets else None


def smoke_test_model(
    model: str,
    screen_name: str,
    *,
    images_dir: Path = IMAGES_DIR,
    labels_dir: Path = LABELS_DIR,
    profile_name: str = "baseline",
    coord_space: str = "pixel",
    target_text: str | None = None,
) -> SmokeTestResult:
    """Send one real query for `model` against one screen's baseline target.

    coord_space is the caller's current assumption for this model (mirrors
    the run-level COORD_SPACE override); coord_space_mismatch is set when the
    reply looks like the other convention, so the UI can suggest a switch
    before the user spends a full run finding out the hard way.
    """
    image_path = images_dir / f"{screen_name}_{profile_name}.png"
    label_path = labels_dir / f"{screen_name}_{profile_name}.json"

    if not image_path.is_file():
        return SmokeTestResult(
            ok=False, model=model, screen=screen_name, target_text=target_text or "",
            error=f"Missing image: {image_path}",
        )
    if not label_path.is_file():
        return SmokeTestResult(
            ok=False, model=model, screen=screen_name, target_text=target_text or "",
            error=f"Missing labels: {label_path}",
        )

    if target_text is None:
        target = _pick_target(screen_name, labels_dir)
        if target is None:
            return SmokeTestResult(
                ok=False, model=model, screen=screen_name, target_text="",
                error=f"No groundable targets found for screen: {screen_name}",
            )
        target_text = target["text"]

    import json

    with open(label_path, "r", encoding="utf-8") as f:
        profile_labels = json.load(f)

    match = locate_element(profile_labels, target_text)
    if match is None:
        return SmokeTestResult(
            ok=False, model=model, screen=screen_name, target_text=target_text,
            image_path=image_path,
            error=f"Target {target_text!r} not present on {screen_name}/{profile_name}",
        )
    box, _matched_text, _match_kind = match

    from .grounding.scoring import get_png_dimensions

    img_width, img_height = get_png_dimensions(image_path)

    prompt = PROMPT_TEMPLATE.format(
        img_width=img_width, img_height=img_height, target_text=target_text,
    )

    start = time.monotonic()
    try:
        coord_space_out: dict = {}
        raw_response = call_vlm(
            model,
            image_path,
            prompt,
            target_text=target_text,
            img_width=img_width,
            img_height=img_height,
            coord_space_out=coord_space_out,
        )
    except Exception as exc:
        return SmokeTestResult(
            ok=False, model=model, screen=screen_name, target_text=target_text,
            image_path=image_path, prompt=prompt,
            latency_seconds=time.monotonic() - start,
            error=f"{type(exc).__name__}: {exc}",
        )
    latency = time.monotonic() - start

    detected_space = classify_normalized_reply(raw_response)
    model_is_normalized_family = uses_normalized_coords(model)
    reply_space = coord_space_out.get("value") or coord_space
    mismatch = (
        (coord_space == "pixel" and not model_is_normalized_family
         and detected_space == "normalized")
        or (coord_space != "pixel" and detected_space == "pixel")
    )

    x_raw, y_raw, _parse_method = parse_coordinates_detailed(raw_response)
    x_pred, y_pred = to_pixel_space(x_raw, y_raw, img_width, img_height, reply_space)

    hit = None
    if 0 <= x_pred <= img_width and 0 <= y_pred <= img_height:
        hit = hit_test(int(x_pred), int(y_pred), box, box)

    return SmokeTestResult(
        ok=True, model=model, screen=screen_name, target_text=target_text,
        image_path=image_path, prompt=prompt, raw_response=raw_response,
        x_pred=x_pred, y_pred=y_pred, box=box, hit=hit,
        latency_seconds=latency,
        coord_space_detected=detected_space, coord_space_used=reply_space,
        coord_space_mismatch=mismatch,
    )


__all__ = ["SmokeTestResult", "smoke_test_model"]
