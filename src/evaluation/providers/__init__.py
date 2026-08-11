"""Stable VLM provider facade used by the evaluation runner."""

from .config import (
    FERRET_MODEL_ID,
    MAX_IMAGE_EDGE,
    image_send_scale,
    max_image_edge,
    model_configuration_error,
    resolve_completion_config,
    validate_coord_space,
)
from .ferret import build_ferret_prompt
from .hosted import TruncatedReplyError, call_vlm, image_to_data_url
from .coord_prompting import (
    GEMINI_SPACE_NORMALIZED,
    GEMINI_SPACE_PIXEL,
    GEMINI_SPACE_UNVERIFIED,
    build_normalized_prompt,
)

__all__ = [
    "FERRET_MODEL_ID",
    "MAX_IMAGE_EDGE",
    "TruncatedReplyError",
    "image_send_scale",
    "max_image_edge",
    "GEMINI_SPACE_NORMALIZED",
    "GEMINI_SPACE_PIXEL",
    "GEMINI_SPACE_UNVERIFIED",
    "build_ferret_prompt",
    "build_normalized_prompt",
    "call_vlm",
    "image_to_data_url",
    "model_configuration_error",
    "resolve_completion_config",
    "validate_coord_space",
]
