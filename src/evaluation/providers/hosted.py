"""Hosted LiteLLM transport, response extraction, and provider dispatch."""

import base64
import io
import os
import time
from pathlib import Path
from typing import Any

from .config import (
    FERRET_MODEL_ID,
    NINEROUTER_PREFIX,
    resolve_completion_config,
    uses_normalized_coords,
)
from .ferret import call_ferret
from .coord_prompting import (
    GEMINI_SPACE_NORMALIZED,
    GEMINI_SPACE_PIXEL,
    GEMINI_SPACE_UNVERIFIED,
    build_normalized_prompt,
    classify_normalized_reply,
    extract_target_from_prompt,
    resolve_image_dims,
)
from .retry import (
    DEFAULT_RATE_LIMIT_BACKOFF_SECONDS,
    MAX_TOKENS_ENV_VAR,
    THINKING_ENV_VAR,
    is_rate_limit_error,
    is_retryable_error,
    is_temperature_rejection,
    resolve_max_retries,
    resolve_max_tokens,
    resolve_request_timeout,
    resolve_structured_coords,
    resolve_temperature,
    resolve_thinking,
    retry_delay_seconds,
)

# Providers whose models accept an extended-thinking configuration. Sending it
# to anyone else is an unrecognised parameter, so it is opt-in by prefix.
_THINKING_PREFIXES = ("anthropic/", "claude-")

_TEMPERATURE_UNSUPPORTED: set[str] = set()

def image_to_data_url(image_path: Path, scale: float = 1.0) -> str:
    """Convert a local PNG screenshot to a base64 data URL.

    A scale below 1.0 downsizes the image first, so the model is shown -- and
    therefore answers in -- a coordinate space this pipeline chose. Left to the
    provider, the same downscale happens silently and the reply lands in a
    space nothing recorded (see MAX_IMAGE_EDGE).

    scale == 1.0 re-reads and re-encodes the original bytes untouched, so an
    uncapped model's request is byte-identical to what it was before capping
    existed.
    """
    if scale >= 1.0:
        image_bytes = image_path.read_bytes()
    else:
        from PIL import Image

        with Image.open(image_path) as img:
            img = img.convert("RGB")
            target = (round(img.width * scale), round(img.height * scale))
            buffer = io.BytesIO()
            img.resize(target, Image.LANCZOS).save(buffer, format="PNG")
        image_bytes = buffer.getvalue()

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
    return model.startswith(NINEROUTER_PREFIX)


def _register_compatible_model(model: str) -> None:
    """Register a 9Router route with LiteLLM once."""
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


class TruncatedReplyError(RuntimeError):
    """A reply hit the token budget before the model finished answering.

    Raised rather than parsed because a truncated reply is a failed call, not a
    wrong answer. Left to the parser it reads as an unparseable coordinate and
    scores as a grounding miss -- and on a model that thinks, truncation gets
    likelier the longer the model reasons, so the misses would land on exactly
    the hard targets and make the accessibility profiles look worse than they
    are. Deliberately not retryable: the same budget truncates again.
    """


def _finish_reason(response: Any) -> str | None:
    """Read the finish reason from LiteLLM's OpenAI-compatible response shape."""
    try:
        return response.choices[0].finish_reason
    except (AttributeError, IndexError, KeyError, TypeError):
        try:
            return response["choices"][0]["finish_reason"]
        except (KeyError, IndexError, TypeError):
            return None


def _raise_if_truncated(response: Any, max_tokens: int | None) -> None:
    """Fail the call when the provider stopped at the token budget."""
    if _finish_reason(response) != "length":
        return
    budget = f"{max_tokens}-token" if max_tokens is not None else "provider default"
    raise TruncatedReplyError(
        f"reply hit the {budget} budget before completing. "
        f"Set {MAX_TOKENS_ENV_VAR} higher, or disable thinking with "
        f"{THINKING_ENV_VAR}=disabled."
    )


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
    image_scale: float = 1.0,
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
    unchanged. tree_rows is the collect_tree_rows() output, scaled (see
    scale_tree_rows) into the coordinate space of the image actually sent --
    matching the img_width/img_height args it is rendered alongside, not
    always full-size cropped-image pixels. Each model-specific rewrite is
    responsible for converting to its own coordinate convention.

    coord_space_out, when given a dict, receives {"value": GEMINI_SPACE_*}
    for Gemini models once the reply is resolved, so a caller can log
    per-row format compliance.
    It is left untouched for every other model family.

    image_scale downsizes the screenshot before sending, for models whose
    provider would otherwise downscale it silently (see MAX_IMAGE_EDGE). The
    reply is then in the scaled image's coordinate space, and the caller is
    responsible for scaling predictions back -- `prompt` must already state
    the scaled dimensions. The default 1.0 sends the image untouched.
    """
    if model == FERRET_MODEL_ID:
        return call_ferret(
            image_path,
            prompt,
            target_text,
            tree_rows,
            img_width,
            img_height,
            max_retries,
            request_timeout,
        )

    is_normalized = uses_normalized_coords(model)
    norm_target = None
    norm_w = norm_h = None
    if is_normalized:
        norm_target = (
            target_text if target_text is not None else extract_target_from_prompt(prompt)
        )
        if norm_target is not None:
            norm_w, norm_h = resolve_image_dims(image_path, img_width, img_height)

    data_url = image_to_data_url(image_path, image_scale)
    retries = resolve_max_retries(max_retries)
    timeout = resolve_request_timeout(request_timeout)
    resolved_temperature = resolve_temperature(temperature)
    resolved_max_tokens = resolve_max_tokens(max_tokens)
    is_anthropic = any(model.startswith(p) for p in _THINKING_PREFIXES)
    resolved_thinking = resolve_thinking() if is_anthropic else None
    resolved_format = resolve_structured_coords() if is_anthropic else None
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
            if resolved_max_tokens is not None:
                kwargs["max_tokens"] = resolved_max_tokens
            if resolved_thinking is not None:
                kwargs["thinking"] = resolved_thinking
            if resolved_format is not None:
                kwargs["response_format"] = resolved_format
            if resolved_temperature is not None and model not in _TEMPERATURE_UNSUPPORTED:
                kwargs["temperature"] = resolved_temperature
            kwargs["timeout"] = timeout
            response = _completion(**kwargs)
            _raise_if_truncated(response, resolved_max_tokens)
            raw_text = _extract_response_text(response)
        except Exception as exc:
            # Some reasoning models reject an explicit temperature. Drop it for
            # this model and retry rather than failing the whole run.
            if (
                is_temperature_rejection(exc)
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

            if not is_retryable_error(exc) or attempt >= retries:
                raise

            sleep_seconds = retry_delay_seconds(exc, delay)
            # Name the exception class for non-rate-limit failures: retries now
            # cover timeouts, 5xx, and dropped connections, and "Request failed"
            # alone makes those indistinguishable in a run log.
            reason = "Rate limited" if is_rate_limit_error(exc) else exc.__class__.__name__
            print(
                f"    [RETRY] {reason}; sleeping {sleep_seconds:.2f}s "
                f"before retry {attempt + 1}/{retries}"
            )
            time.sleep(sleep_seconds)
            delay = max(sleep_seconds * 2, DEFAULT_RATE_LIMIT_BACKOFF_SECONDS)
            attempt += 1
            continue

        if is_normalized and norm_target is not None:
            space = classify_normalized_reply(raw_text)
            if space == GEMINI_SPACE_PIXEL and attempt < retries:
                # Out-of-range on either axis is unambiguous pixel-space
                # non-compliance (see classify_normalized_reply); retry with a
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
