"""Hosted LiteLLM transport, response extraction, and provider dispatch."""

import base64
import os
import time
import urllib
from pathlib import Path
from typing import Any

from .config import (
    FERRET_MODEL_ID,
    NINEROUTER_PREFIX,
    OPENAI_COMPATIBLE_PREFIX,
    model_configuration_error,
    resolve_completion_config,
    validate_coord_space,
    _normalize_compatible_base_url,
)
from .ferret import build_ferret_prompt, call_ferret, parse_ferret_bbox
from .coord_prompting import (
    GEMINI_SPACE_NORMALIZED,
    GEMINI_SPACE_PIXEL,
    GEMINI_SPACE_UNVERIFIED,
    build_normalized_prompt,
    classify_normalized_reply,
    extract_target_from_prompt,
    resolve_image_dims,
    uses_normalized_coords,
)
from .retry import (
    DEFAULT_RATE_LIMIT_BACKOFF_SECONDS,
    is_rate_limit_error,
    is_retryable_error,
    is_temperature_rejection,
    resolve_max_retries,
    resolve_request_timeout,
    resolve_temperature,
    retry_delay_seconds,
)

_TEMPERATURE_UNSUPPORTED: set[str] = set()

# Private aliases retained for focused compatibility and tests.
_resolve_request_timeout = resolve_request_timeout
_resolve_temperature = resolve_temperature
_is_temperature_rejection = is_temperature_rejection
_resolve_max_retries = resolve_max_retries
_is_rate_limit_error = is_rate_limit_error
_is_retryable_error = is_retryable_error
_retry_delay_seconds = retry_delay_seconds
_uses_normalized_coords = uses_normalized_coords
_extract_target_from_prompt = extract_target_from_prompt
_resolve_image_dims = resolve_image_dims
_classify_normalized_reply = classify_normalized_reply
_call_ferret = call_ferret
_parse_ferret_bbox = parse_ferret_bbox

def image_to_data_url(image_path: Path) -> str:
    """Convert a local PNG screenshot to a base64 data URL."""
    image_bytes = image_path.read_bytes()
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _completion(**kwargs: Any) -> Any:
    """Import LiteLLM lazily so non-evaluator imports do not require it."""
    try:
        from litellm import completion
    except ImportError as exc:
        raise RuntimeError(
            "litellm package not installed. Run: pip install litellm"
        ) from exc

    return completion(**kwargs)


def _is_compatibility_model(model: str) -> bool:
    return model.startswith((NINEROUTER_PREFIX, OPENAI_COMPATIBLE_PREFIX))


def _register_compatible_model(model: str) -> None:
    """Register an arbitrary OpenAI-compatible route with LiteLLM once."""
    if not _is_compatibility_model(model):
        return

    route = model.split("/", 1)[1]
    try:
        import litellm
    except ImportError as exc:
        raise RuntimeError(
            "litellm package not installed. Run: pip install litellm"
        ) from exc

    if route in litellm.open_ai_chat_completion_models:
        return

    # register_model() performs an internal model-info lookup. LiteLLM's
    # lookup prints its provider help text for unknown custom IDs, so suppress
    # only that registration-time diagnostic and restore the setting at once.
    previous_suppress_debug_info = getattr(litellm, "suppress_debug_info", False)
    try:
        litellm.suppress_debug_info = True
        litellm.register_model(
            {
                route: {
                    "litellm_provider": "openai",
                    "mode": "chat",
                    "input_cost_per_token": 0.0,
                    "output_cost_per_token": 0.0,
                }
            }
        )
    finally:
        litellm.suppress_debug_info = previous_suppress_debug_info


def _extract_response_text(response: Any) -> str:
    """Extract assistant text from LiteLLM's OpenAI-compatible response shape."""
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, KeyError, TypeError):
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return ""

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(str(part.get("text", "")))
        return "".join(text_parts)

    return "" if content is None else str(content)


def call_vlm(
    model: str,
    image_path: Path,
    prompt: str,
    max_retries: int | None = None,
    max_tokens: int | None = None,
    request_timeout: float | None = None,
    temperature: float | None = None,
    *,
    target_text: str | None = None,
    tree_rows: list[tuple[str, list[int]]] | None = None,
    img_width: int | None = None,
    img_height: int | None = None,
    coord_space_out: dict | None = None,
) -> str:
    """
    Send image + prompt to a vision model and return raw text.

    Model examples:
      - openai/gpt-4o-mini
      - gemini/gemini-2.5-flash
      - anthropic/claude-3-5-sonnet-latest
      - local/ferret-ui-llama8b

    target_text and tree_rows are structured context for models whose wire
    format is rewritten from `prompt` rather than sent verbatim (currently
    Ferret-UI and Gemini). Other hosted models ignore them and send `prompt`
    unchanged. tree_rows is the collect_tree_rows() output in cropped-image
    pixel space; each model-specific rewrite is responsible for converting to
    its own coordinate convention.

    coord_space_out, when given a dict, receives {"value": GEMINI_SPACE_*}
    for Gemini models once the reply is resolved, so a caller can log
    per-row format compliance (see build_gemini_prompt / _resolve_gemini_reply).
    It is left untouched for every other model family.
    """
    if model == FERRET_MODEL_ID:
        return _call_ferret(
            image_path,
            prompt,
            target_text,
            tree_rows,
            img_width,
            img_height,
            max_retries,
            request_timeout,
        )

    is_normalized = _uses_normalized_coords(model)
    norm_target = None
    norm_w = norm_h = None
    if is_normalized:
        norm_target = (
            target_text if target_text is not None else _extract_target_from_prompt(prompt)
        )
        if norm_target is not None:
            norm_w, norm_h = _resolve_image_dims(image_path, img_width, img_height)

    data_url = image_to_data_url(image_path)
    retries = _resolve_max_retries(max_retries)
    timeout = _resolve_request_timeout(request_timeout)
    resolved_temperature = _resolve_temperature(temperature)
    _register_compatible_model(model)
    delay = DEFAULT_RATE_LIMIT_BACKOFF_SECONDS

    attempt = 0
    while attempt <= retries:
        wire_prompt = (
            build_normalized_prompt(
                norm_target, tree_rows, norm_w, norm_h, strict=attempt > 0
            )
            if is_normalized and norm_target is not None
            else prompt
        )
        try:
            kwargs = dict(
                **resolve_completion_config(model),
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": wire_prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": data_url},
                            },
                        ],
                    }
                ],
            )
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens
            if resolved_temperature is not None and model not in _TEMPERATURE_UNSUPPORTED:
                kwargs["temperature"] = resolved_temperature
            kwargs["timeout"] = timeout
            response = _completion(**kwargs)
            raw_text = _extract_response_text(response)
        except Exception as exc:
            # Some reasoning models reject an explicit temperature. Drop it for
            # this model and retry rather than failing the whole run.
            if (
                _is_temperature_rejection(exc)
                and model not in _TEMPERATURE_UNSUPPORTED
            ):
                _TEMPERATURE_UNSUPPORTED.add(model)
                print(f"    [INFO] {model} rejects an explicit temperature; "
                      f"continuing without it (results are not guaranteed "
                      f"deterministic for this model).")
                # Deliberately does not advance `attempt`: dropping an
                # unsupported parameter is a correction, not a failed try, and
                # must not consume the retry budget (nor exhaust it when
                # retries == 0).
                continue

            if not _is_retryable_error(exc) or attempt >= retries:
                raise

            sleep_seconds = _retry_delay_seconds(exc, delay)
            # Name the exception class for non-rate-limit failures: retries now
            # cover timeouts, 5xx, and dropped connections, and "Request failed"
            # alone makes those indistinguishable in a run log.
            reason = "Rate limited" if _is_rate_limit_error(exc) else exc.__class__.__name__
            print(
                f"    [RETRY] {reason}; sleeping {sleep_seconds:.2f}s "
                f"before retry {attempt + 1}/{retries}"
            )
            time.sleep(sleep_seconds)
            delay = max(sleep_seconds * 2, DEFAULT_RATE_LIMIT_BACKOFF_SECONDS)
            attempt += 1
            continue

        if is_normalized and norm_target is not None:
            space = _classify_normalized_reply(raw_text)
            if space == GEMINI_SPACE_PIXEL and attempt < retries:
                # Out-of-range on either axis is unambiguous pixel-space
                # non-compliance (see _classify_normalized_reply); retry with a
                # stricter restatement rather than silently coercing it.
                print(
                    f"    [RETRY] {model} answered in pixel space instead of "
                    f"the requested 0-1000 normalized scale; retrying with a "
                    f"stricter restatement ({attempt + 1}/{retries})"
                )
                attempt += 1
                continue
            if coord_space_out is not None:
                coord_space_out["value"] = space
            # Verbatim: the runner converts, using `space` for this reply.
            return raw_text

        return raw_text

    raise RuntimeError("unreachable retry state")
