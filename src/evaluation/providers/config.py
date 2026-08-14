"""Provider route, credential, and coordinate override configuration."""

import os

from ..config import COORD_SPACE_ENV_VAR, DEFAULT_COORD_SPACE

NINEROUTER_PREFIX = "9router/"
NINEROUTER_BASE_URL_ENV_VAR = "NINEROUTER_BASE_URL"
NINEROUTER_API_KEY_ENV_VAR = "NINEROUTER_API_KEY"
FERRET_MODEL_ID = "local/ferret-ui-llama8b"
NORMALIZED_COORD_FAMILIES = ("gemini", "qwen", "glm")

# Longest image edge a model accepts, by substring of the model id.
#
# A provider that receives a larger image silently downscales it -- and the
# model then answers in the space it was actually shown, not the space the
# prompt states. Every prediction comes back multiplied by the downscale
# factor, which reads as catastrophically bad grounding rather than as a unit
# mismatch. It is invisible in the CSV: the reply parses fine and simply lands
# in the wrong place, so nothing downstream can flag it.
#
# Before adding a model, check its documented image cap against the tallest
# screenshot this pipeline produces. A low score from a capable model is this
# bug until proven otherwise.
#
# Declaring the cap here lets the pipeline do the resize itself, so the
# coordinate space is one we chose and recorded rather than one we inferred
# from provider behaviour that can change without notice. A model absent from
# this map is sent at native size and its request is untouched.
MAX_IMAGE_EDGE: dict[str, int] = {
    "claude-haiku-4-5": 1568,
    "claude-sonnet-4-6": 1568,
    "claude-sonnet-4-5": 1568,
    "claude-opus-4-6": 1568,
    "claude-opus-4-5": 1568,
    "claude-opus-4-1": 1568,
    # Opus 4.7+ and Sonnet 5 raised the cap to 2576, which exceeds the tallest
    # screenshot this pipeline produces (2219), so they need no entry.
}


def uses_normalized_coords(model: str) -> bool:
    """Return whether a model uses a native 0-1000 coordinate convention."""
    if model == FERRET_MODEL_ID:
        return False
    name = model[len(NINEROUTER_PREFIX):] if model.startswith(NINEROUTER_PREFIX) else model
    return any(family in name.lower() for family in NORMALIZED_COORD_FAMILIES)


def max_image_edge(model: str) -> int | None:
    """Return the longest image edge *model* accepts, or None when uncapped."""
    name = model.lower()
    for pattern, edge in MAX_IMAGE_EDGE.items():
        if pattern in name:
            return edge
    return None


def image_send_scale(model: str, width: int, height: int) -> float:
    """Return the factor an image must be scaled by before sending to *model*.

    Exactly 1.0 when the image already fits, which callers rely on to skip the
    resize entirely and leave the request byte-identical to what every
    already-collected model was sent.
    """
    edge = max_image_edge(model)
    if edge is None or max(width, height) <= edge:
        return 1.0
    return edge / max(width, height)

def _normalize_compatible_base_url(base_url: str) -> str:
    """Return an OpenAI-compatible base URL ending in exactly one ``/v1``."""
    normalized = base_url.strip().rstrip("/")
    if not normalized:
        return normalized
    return normalized if normalized.endswith("/v1") else f"{normalized}/v1"


def _is_configured_value(value: str | None) -> bool:
    if not value:
        return False
    value_lower = value.lower()
    return not ("your-" in value_lower and "-here" in value_lower)


def model_configuration_error(model: str) -> str | None:
    """Return a user-facing configuration error, or None when configured."""
    if model.startswith(NINEROUTER_PREFIX):
        if not model[len(NINEROUTER_PREFIX):].strip():
            return f"A 9Router model route is required after {NINEROUTER_PREFIX}"
        base_var = NINEROUTER_BASE_URL_ENV_VAR
        key_var = NINEROUTER_API_KEY_ENV_VAR
        example = "VLM_MODEL=9router/cx/gpt-5.3-codex"
    else:
        return None

    missing = [
        name
        for name in (base_var, key_var)
        if not _is_configured_value(os.environ.get(name, "").strip())
    ]
    if not missing:
        return None
    return f"{', '.join(missing)} must be set for {model}. Example: {example}"


def resolve_completion_config(model: str) -> dict[str, str]:
    """Resolve a model name into stable LiteLLM completion arguments."""
    error = model_configuration_error(model)
    if error:
        raise ValueError(error)

    if model.startswith(NINEROUTER_PREFIX):
        return {
            "model": model[len(NINEROUTER_PREFIX):],
            "custom_llm_provider": "openai",
            "api_base": _normalize_compatible_base_url(
                os.environ[NINEROUTER_BASE_URL_ENV_VAR]
            ),
            "api_key": os.environ[NINEROUTER_API_KEY_ENV_VAR].strip(),
        }

    return {"model": model}


def validate_coord_space(model: str, coord_space: str) -> str:
    """Reject overrides that would double-convert a known model reply."""
    if coord_space == DEFAULT_COORD_SPACE:
        return coord_space
    if uses_normalized_coords(model) or model == FERRET_MODEL_ID:
        print(
            f"[ERROR] {COORD_SPACE_ENV_VAR}={coord_space} is invalid for {model}: "
            "this model already reports its own coordinate space per reply, so "
            f"the override would convert twice. Unset {COORD_SPACE_ENV_VAR} "
            f"(or set it to '{DEFAULT_COORD_SPACE}')."
        )
        raise SystemExit(1)
    return coord_space
