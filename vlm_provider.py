"""
vlm_provider.py
---------------
LiteLLM-backed VLM provider helpers.

The evaluator only needs one operation: send a screenshot plus prompt to a
vision-capable model and return the raw text response.
"""

import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

MAX_RETRIES_ENV_VAR = "VLM_MAX_RETRIES"
DEFAULT_MAX_RETRIES = 3
DEFAULT_RATE_LIMIT_BACKOFF_SECONDS = 0.5
REQUEST_TIMEOUT_ENV_VAR = "VLM_REQUEST_TIMEOUT_SECONDS"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 120.0
TEMPERATURE_ENV_VAR = "VLM_TEMPERATURE"
DEFAULT_TEMPERATURE = 0.0

# Models whose provider rejected `temperature`; retried without it thereafter so
# one rejection does not cost an extra failed call on every later query.
_TEMPERATURE_UNSUPPORTED: set[str] = set()

NINEROUTER_PREFIX = "9router/"
OPENAI_COMPATIBLE_PREFIX = "openai_compatible/"
NINEROUTER_BASE_URL_ENV_VAR = "NINEROUTER_BASE_URL"
NINEROUTER_API_KEY_ENV_VAR = "NINEROUTER_API_KEY"
OPENAI_COMPATIBLE_BASE_URL_ENV_VAR = "OPENAI_COMPATIBLE_BASE_URL"
OPENAI_COMPATIBLE_API_KEY_ENV_VAR = "OPENAI_COMPATIBLE_API_KEY"

FERRET_MODEL_ID = "local/ferret-ui-llama8b"
FERRET_SERVER_URL = "http://localhost:8000/"
# ferret_ui/model_UI.py:16-17 (VOCAB_IMAGE_W/H) and the ferret_llama_3 system
# prompt in ferret_ui/conversation.py:443-448 ("Image size: 1000x1000") both
# fix Ferret's coordinate space at 1000x1000, independent of the real
# screenshot's pixel dimensions.
FERRET_VOCAB_SIZE = 1000

_FERRET_DOUBLE_BRACKET_RE = re.compile(
    r"\[\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,"
    r"\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\]\]"
)
_FERRET_SINGLE_BRACKET_RE = re.compile(
    r"\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,"
    r"\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\]"
)


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


def _resolve_request_timeout(timeout: float | None = None) -> float:
    """Resolve the per-request timeout from an argument or environment."""
    if timeout is not None:
        resolved = timeout
    else:
        raw_timeout = os.environ.get(REQUEST_TIMEOUT_ENV_VAR, "").strip()
        resolved = (
            DEFAULT_REQUEST_TIMEOUT_SECONDS
            if not raw_timeout
            else float(raw_timeout)
        )

    if resolved <= 0:
        raise ValueError(f"{REQUEST_TIMEOUT_ENV_VAR} must be > 0")
    return resolved


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
    elif model.startswith(OPENAI_COMPATIBLE_PREFIX):
        if not model[len(OPENAI_COMPATIBLE_PREFIX):].strip():
            return f"An OpenAI-compatible model is required after {OPENAI_COMPATIBLE_PREFIX}"
        base_var = OPENAI_COMPATIBLE_BASE_URL_ENV_VAR
        key_var = OPENAI_COMPATIBLE_API_KEY_ENV_VAR
        example = "VLM_MODEL=openai_compatible/my-provider-model"
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

    if model.startswith(OPENAI_COMPATIBLE_PREFIX):
        return {
            "model": model[len(OPENAI_COMPATIBLE_PREFIX):],
            "custom_llm_provider": "openai",
            "api_base": _normalize_compatible_base_url(
                os.environ[OPENAI_COMPATIBLE_BASE_URL_ENV_VAR]
            ),
            "api_key": os.environ[OPENAI_COMPATIBLE_API_KEY_ENV_VAR].strip(),
        }

    return {"model": model}


def _resolve_temperature(temperature: float | None = None) -> float | None:
    """
    Resolve the sampling temperature, defaulting to 0 for reproducibility.

    Scores were previously single draws at the provider's default temperature,
    so a marginal result could not be distinguished from a coin flip. Set
    VLM_TEMPERATURE to an empty string to omit the parameter entirely.
    """
    if temperature is not None:
        return temperature

    raw = os.environ.get(TEMPERATURE_ENV_VAR)
    if raw is None:
        return DEFAULT_TEMPERATURE
    raw = raw.strip()
    if not raw:
        return None
    return float(raw)


def _is_temperature_rejection(exc: Exception) -> bool:
    """Detect providers that refuse an explicit temperature (some reasoning models)."""
    message = str(exc).lower()
    return "temperature" in message and any(
        token in message
        for token in ("unsupported", "not supported", "does not support", "invalid", "unrecognized")
    )


def _resolve_max_retries(max_retries: int | None = None) -> int:
    """Resolve retry count from explicit argument or VLM_MAX_RETRIES."""
    if max_retries is not None:
        resolved = max_retries
    else:
        raw_retries = os.environ.get(MAX_RETRIES_ENV_VAR, "").strip()
        resolved = DEFAULT_MAX_RETRIES if not raw_retries else int(raw_retries)

    if resolved < 0:
        raise ValueError(f"{MAX_RETRIES_ENV_VAR} must be >= 0")

    return resolved


def _is_rate_limit_error(exc: Exception) -> bool:
    """Detect LiteLLM/provider rate-limit errors without importing LiteLLM eagerly."""
    class_name = exc.__class__.__name__.lower()
    if "ratelimit" in class_name or "rate_limit" in class_name or "overload" in class_name:
        return True

    status_code = getattr(exc, "status_code", None)
    if status_code in (429, 503):
        return True

    exc_str = str(exc).lower()
    return "rate limit" in exc_str or "try again" in exc_str or "later" in exc_str or "overload" in exc_str


def _is_retryable_error(exc: Exception) -> bool:
    """Identify provider throttling and transient network failures."""
    if _is_rate_limit_error(exc):
        return True

    class_name = exc.__class__.__name__.lower()
    if any(token in class_name for token in ("timeout", "connecterror", "networkerror")):
        return True

    message = str(exc).lower()
    return any(
        token in message
        for token in (
            "timed out",
            "timeout",
            "connection reset",
            "connection error",
            "connect error",
        )
    )


def _retry_delay_seconds(exc: Exception, fallback: float) -> float:
    """Extract retry delay hints from provider errors, falling back to backoff."""
    retry_after = getattr(exc, "retry_after", None)
    if retry_after is not None:
        try:
            return max(float(retry_after), 0.0)
        except (TypeError, ValueError):
            pass

    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", {}) if response is not None else {}
    header_retry_after = None
    if headers:
        header_retry_after = headers.get("retry-after") or headers.get("Retry-After")
    if header_retry_after is not None:
        try:
            return max(float(header_retry_after), 0.0)
        except (TypeError, ValueError):
            pass

    message = str(exc)
    ms_match = re.search(r"(?:try again|retry) in\s+(\d+(?:\.\d+)?)\s*ms", message, re.I)
    if ms_match:
        return max(float(ms_match.group(1)) / 1000.0, 0.0)

    seconds_match = re.search(r"(?:try again|retry) in\s+(\d+(?:\.\d+)?)\s*s", message, re.I)
    if seconds_match:
        return max(float(seconds_match.group(1)), 0.0)

    return fallback


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


def _sanitize_for_ferret(text: str) -> str:
    """
    Strip characters that would confuse ferret_server.py's prompt parsing.

    ferret_server.py:40-41 does `if "<image>" in qs: qs = qs.split('\\n')[1]`,
    so a UI label containing that literal token would silently shred the
    prompt down to a single line. Newlines are flattened too, so a tree row
    label can never masquerade as that split point.
    """
    return text.replace("<image>", "").replace("\n", " ").replace("\r", " ")


def build_ferret_prompt(
    target_text: str,
    tree_rows: list[tuple[str, list[int]]] | None,
    img_width: int,
    img_height: int,
) -> str:
    """
    Build the prompt Ferret-UI expects.

    Vision mode (tree_rows falsy) returns exactly the fine-tuned grounding
    line Ferret was trained on -- unchanged from before tree mode existed, so
    the two modes only ever differ by the tree block.

    Tree mode prepends nearby elements, scaled to Ferret's own 0-1000
    "vocabulary" coordinate space (see FERRET_VOCAB_SIZE), formatted the way
    ferret_ui/model_UI.py:126-140 formats an input box: single bracket,
    comma-space, `int()`-truncated (not rounded) after scaling -- matching
    ferret_ui/model_UI.py:131,136 exactly. The grounding line always comes
    last, since Ferret's fine-tuning expects the instruction to be the final
    thing it reads.
    """
    grounding_line = f"Provide the bounding box of the text '{_sanitize_for_ferret(target_text)}'."
    if not tree_rows:
        return grounding_line

    ratio_w = FERRET_VOCAB_SIZE / img_width
    ratio_h = FERRET_VOCAB_SIZE / img_height
    lines = []
    for label, box in tree_rows:
        x1, y1, x2, y2 = box
        vx1, vy1 = int(x1 * ratio_w), int(y1 * ratio_h)
        vx2, vy2 = int(x2 * ratio_w), int(y2 * ratio_h)
        lines.append(
            f'"{_sanitize_for_ferret(label)}" [{vx1}, {vy1}, {vx2}, {vy2}]'
        )

    return "Nearby elements:\n" + "\n".join(lines) + "\n\n" + grounding_line


def _parse_ferret_bbox(ferret_text: str) -> tuple[float, float, float, float] | None:
    """
    Extract an [x1, y1, x2, y2] box from a Ferret-UI reply.

    Prefers the anchored double-bracket [[...]] form the model is fine-tuned
    to emit. Falls back to the LAST single-bracket 4-tuple (int or float) in
    the reply -- "last" matters once the prompt itself can contain bracketed
    boxes (the injected tree) that the model might echo back before its
    actual answer.
    """
    match = _FERRET_DOUBLE_BRACKET_RE.search(ferret_text)
    if match:
        return tuple(float(v) for v in match.groups())

    matches = _FERRET_SINGLE_BRACKET_RE.findall(ferret_text)
    if matches:
        return tuple(float(v) for v in matches[-1])

    return None


def _call_ferret(
    image_path: Path,
    prompt: str,
    target_text: str | None,
    tree_rows: list[tuple[str, list[int]]] | None,
    img_width: int | None,
    img_height: int | None,
    max_retries: int | None,
    request_timeout: float | None,
) -> str:
    """Send a request to the local Ferret-UI inference server."""
    from PIL import Image

    resolved_target = target_text
    if resolved_target is None:
        # Fallback for callers that don't pass structured target_text.
        # Apostrophes in the target text truncate the capture here, which is
        # why every in-repo caller now passes target_text explicitly instead.
        match = re.search(r"click on the text element:\s*'([^']+)'", prompt)
        if match:
            resolved_target = match.group(1)
            print(
                "    [WARN] call_vlm invoked for Ferret-UI without "
                "target_text; falling back to regex extraction from the "
                "prompt string."
            )

    if img_width is not None and img_height is not None:
        w, h = img_width, img_height
    else:
        with Image.open(image_path) as img:
            w, h = img.size

    if resolved_target is None:
        # No target could be determined at all; send the raw prompt through
        # rather than fabricate a grounding line (this will confuse Ferret,
        # but that is a caller bug this fallback cannot repair).
        ferret_prompt = prompt
    else:
        ferret_prompt = build_ferret_prompt(resolved_target, tree_rows, w, h)

    data = {
        "image_path": str(image_path),
        "prompt": ferret_prompt,
    }
    body = json.dumps(data).encode("utf-8")

    retries = _resolve_max_retries(max_retries)
    timeout = _resolve_request_timeout(request_timeout)
    delay = DEFAULT_RATE_LIMIT_BACKOFF_SECONDS

    attempt = 0
    while True:
        req = urllib.request.Request(
            FERRET_SERVER_URL,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read().decode("utf-8")).get("error", "")
            except Exception:
                detail = ""
            raise RuntimeError(
                f"Ferret-UI server rejected the request (HTTP {e.code}): {detail}"
            ) from e
        except urllib.error.URLError as e:
            if isinstance(e.reason, ConnectionRefusedError):
                print("\n[ERROR] Could not connect to the Ferret-UI inference server!")
                print("Please start the server in a separate terminal:")
                print("  cd ferret_ui")
                print("  .\\venv\\Scripts\\activate")
                print("  python ferret_server.py")
                print("Wait for 'Model loaded successfully!' before running the evaluator.\n")
                raise SystemExit(1)
            if _is_retryable_error(e) and attempt < retries:
                sleep_seconds = delay
                print(
                    f"    [RETRY] Ferret-UI request failed; sleeping "
                    f"{sleep_seconds:.2f}s before retry {attempt + 1}/{retries}"
                )
                time.sleep(sleep_seconds)
                delay = max(delay * 2, DEFAULT_RATE_LIMIT_BACKOFF_SECONDS)
                attempt += 1
                continue
            print(f"Error communicating with local ferret model: {e}")
            raise e
        break

    ferret_text = result.get("text", "")
    bbox = _parse_ferret_bbox(ferret_text)
    if bbox is None:
        return ferret_text

    x1, y1, x2, y2 = bbox
    # Convert from Ferret's 0-1000 vocabulary scale to absolute pixels.
    cx = ((x1 + x2) / 2.0 / FERRET_VOCAB_SIZE) * w
    cy = ((y1 + y2) / 2.0 / FERRET_VOCAB_SIZE) * h
    return f"[{cx:.1f}, {cy:.1f}]"


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
    only local/ferret-ui-llama8b). Hosted models ignore them and send
    `prompt` unchanged. tree_rows is the collect_tree_rows() output in
    cropped-image pixel space; each model-specific rewrite is responsible for
    converting to its own coordinate convention.
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

    data_url = image_to_data_url(image_path)
    retries = _resolve_max_retries(max_retries)
    timeout = _resolve_request_timeout(request_timeout)
    resolved_temperature = _resolve_temperature(temperature)
    _register_compatible_model(model)
    delay = DEFAULT_RATE_LIMIT_BACKOFF_SECONDS

    attempt = 0
    while attempt <= retries:
        try:
            kwargs = dict(
                **resolve_completion_config(model),
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
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
            return _extract_response_text(response)
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
            failure_kind = "Rate limited" if _is_rate_limit_error(exc) else "Request failed"
            print(
                f"    [RETRY] {failure_kind}; sleeping {sleep_seconds:.2f}s "
                f"before retry {attempt + 1}/{retries}"
            )
            time.sleep(sleep_seconds)
            delay = max(sleep_seconds * 2, DEFAULT_RATE_LIMIT_BACKOFF_SECONDS)
            attempt += 1

    raise RuntimeError("unreachable retry state")
