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

# vlm_eval.config imports nothing from this module (only os/pathlib), so this
# direction is safe; the reverse would be circular.
from vlm_eval.config import COORD_SPACE_ENV_VAR, DEFAULT_COORD_SPACE

MAX_RETRIES_ENV_VAR = "VLM_MAX_RETRIES"
DEFAULT_MAX_RETRIES = 3
DEFAULT_RATE_LIMIT_BACKOFF_SECONDS = 0.5
REQUEST_TIMEOUT_ENV_VAR = "VLM_REQUEST_TIMEOUT_SECONDS"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 120.0
# Ferret-UI is a locally-hosted 8B model doing single-request inference on
# one GPU, not a hosted API behind a load balancer -- a query that echoes a
# long target string back before its answer can take minutes, not seconds.
# Abandoning the socket at the hosted-API default leaves the server still
# generating for a client that already gave up, which is what causes the
# request backlog seen under FerretServer.request_queue_size.
FERRET_REQUEST_TIMEOUT_SECONDS = 1800.0
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

# Gemini's own grounding/object-detection post-training returns point and
# bounding-box coordinates on a 0-1000 normalized scale regardless of the
# image's real pixel dimensions, and it applies that convention here even
# though PROMPT_TEMPLATE (vlm_eval/runner.py) explicitly asks for pixels.
# Measured on the collected dataset: gemini-pro-agent's y_pred was a median
# 0.4522x of the true pixel y-centre, against an expected 1000/2219 = 0.4507
# for that image's height -- it was answering in vocab space, not pixel
# space, on ~90% of replies. See CLAUDE.md and build_gemini_prompt below.
GEMINI_VOCAB_SIZE = 1000

GEMINI_SPACE_NORMALIZED = "normalized"
GEMINI_SPACE_PIXEL = "pixel"
GEMINI_SPACE_UNVERIFIED = "unverified"

# Same bracketed-pair shape as vlm_eval.scoring.BRACKET_REGEX, duplicated
# here (rather than imported) so this module keeps parsing its own
# model-specific wire replies locally, the same way the Ferret regexes above
# do for Ferret's own reply shape.
_GEMINI_COORD_RE = re.compile(
    r"[\[(]\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*[\])]"
)

_TARGET_TEXT_RE = re.compile(r"click on the text element:\s*'([^']+)'")


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


def _resolve_request_timeout(
    timeout: float | None = None,
    default: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
) -> float:
    """Resolve the per-request timeout from an argument, environment, or default."""
    if timeout is not None:
        resolved = timeout
    else:
        raw_timeout = os.environ.get(REQUEST_TIMEOUT_ENV_VAR, "").strip()
        resolved = default if not raw_timeout else float(raw_timeout)

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


def _is_retryable_error(exc: Exception) -> bool:
    """Detect transient provider failures worth retrying.

    Covers rate limits plus timeouts, connection drops, and 5xx responses. A
    single hung request used to abort an entire multi-hundred-call sweep,
    discarding every row already collected, because only rate limits were
    retried and the runner treats any surviving exception as fatal.
    """
    if _is_rate_limit_error(exc):
        return True

    class_name = exc.__class__.__name__.lower()
    if any(tok in class_name for tok in ("timeout", "connection", "apierror", "serviceunavailable", "internalserver")):
        return True

    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int) and status_code >= 500:
        return True

    message = str(exc).lower()
    return any(
        tok in message
        for tok in ("timed out", "timeout", "connection error", "connection reset", "bad gateway", "service unavailable")
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


# Model families whose grounding post-training answers on a 0-1000 normalized
# grid rather than in image pixels. Extend this rather than adding a second
# mechanism: one predicate keeps prompt selection, per-reply space resolution,
# and the COORD_SPACE override guard all agreeing about the same models.
_NORMALIZED_COORD_FAMILIES = ("gemini", "qwen", "glm")


def _uses_normalized_coords(model: str) -> bool:
    """True for models that answer on the 0-1000 scale instead of in pixels.

    Covers native `gemini/...`, OpenRouter `openrouter/qwen/...` and
    `openrouter/z-ai/glm-...`, and 9router routes naming any of them. 9router
    routes have their own prefix stripped before the underlying model name
    reaches LiteLLM (see resolve_completion_config), so the 9router branch
    checks past NINEROUTER_PREFIX rather than matching the raw model string.

    Ferret-UI is deliberately excluded: it also replies on a 1000 scale, but
    call_vlm's Ferret branch already converts its own output, so treating it
    here would convert twice.
    """
    if model == FERRET_MODEL_ID:
        return False

    name = model
    if model.startswith(NINEROUTER_PREFIX):
        name = model[len(NINEROUTER_PREFIX):]
    name = name.lower()

    return any(family in name for family in _NORMALIZED_COORD_FAMILIES)


def validate_coord_space(model: str, coord_space: str) -> str:
    """Reject a COORD_SPACE override that would double-convert a model's reply.

    COORD_SPACE is a single global value per run while VLM_MODEL may name
    several models, so no one value is correct for a mixed run. It exists only
    for models this module does not already recognise. A model that converts
    its own output -- anything matched by _uses_normalized_coords, plus
    Ferret-UI -- would have that conversion applied a second time in the
    runner, putting every prediction near the top-left corner and reporting a
    capable model as ~0% accurate. Fail loudly at startup instead.
    """
    if coord_space == DEFAULT_COORD_SPACE:
        return coord_space

    if _uses_normalized_coords(model) or model == FERRET_MODEL_ID:
        print(
            f"[ERROR] {COORD_SPACE_ENV_VAR}={coord_space} is invalid for {model}: "
            f"this model already reports its own coordinate space per reply, so "
            f"the override would convert twice. Unset {COORD_SPACE_ENV_VAR} "
            f"(or set it to '{DEFAULT_COORD_SPACE}')."
        )
        raise SystemExit(1)

    return coord_space


def _extract_target_from_prompt(prompt: str) -> str | None:
    """
    Best-effort fallback: recover the target text from a rendered prompt.

    Used only when a caller does not pass target_text explicitly. Apostrophes
    in the target text truncate this extraction, which is why every in-repo
    caller now passes target_text directly instead of relying on it.
    """
    match = _TARGET_TEXT_RE.search(prompt)
    return match.group(1) if match else None


def _resolve_image_dims(
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


def _classify_normalized_reply(raw_text: str) -> str:
    """
    Decide which coordinate space a normalized-convention model actually used.

    Returns one of GEMINI_SPACE_*. A value > GEMINI_VOCAB_SIZE (or negative) on
    either axis is unambiguous pixel-space non-compliance -- nothing on a 0-1000
    scale can produce it -- so it is reported as PIXEL for the caller to retry
    or flag. Anything in range is trusted as NORMALIZED. An unparseable reply is
    UNVERIFIED.

    Classification only. The reply text is returned to the caller verbatim and
    the pixel conversion happens in the runner (vlm_eval.scoring.to_pixel_space),
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
    """Build the prompt Ferret-UI expects.

    Vision mode (tree_rows falsy) returns exactly the fine-tuned grounding
    line Ferret was trained on. Tree mode prepends nearby elements before it.
    """
    grounding_line = f"Provide the bounding box of the text '{_sanitize_for_ferret(target_text)}'."
    if not tree_rows:
        return grounding_line

    # Tree rows are scaled to Ferret's own 0-1000 "vocabulary" coordinate
    # space (see FERRET_VOCAB_SIZE), formatted the way
    # ferret_ui/model_UI.py:126-140 formats an input box: single bracket,
    # comma-space, `int()`-truncated (not rounded) after scaling -- matching
    # ferret_ui/model_UI.py:131,136 exactly. The grounding line always comes
    # last, since Ferret's fine-tuning expects the instruction to be the
    # final thing it reads.
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
    resolved_target = target_text
    if resolved_target is None:
        # Fallback for callers that don't pass structured target_text.
        resolved_target = _extract_target_from_prompt(prompt)
        if resolved_target is not None:
            print(
                "    [WARN] call_vlm invoked for Ferret-UI without "
                "target_text; falling back to regex extraction from the "
                "prompt string."
            )

    w, h = _resolve_image_dims(image_path, img_width, img_height)

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
    timeout = _resolve_request_timeout(request_timeout, default=FERRET_REQUEST_TIMEOUT_SECONDS)
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
        except TimeoutError as e:
            # Raised directly by urlopen on a read timeout, not wrapped in
            # URLError, so it needs its own clause. Not retried: the server
            # is still generating for this same request, so a retry would
            # queue behind it and time out again rather than making progress.
            raise RuntimeError(
                f"Ferret-UI request exceeded the {timeout:.0f}s timeout "
                f"({REQUEST_TIMEOUT_ENV_VAR}). The server is likely still "
                "generating a reply for a long target string, not down; "
                "raise the timeout rather than retrying."
            ) from e
        except urllib.error.URLError as e:
            if isinstance(e.reason, ConnectionRefusedError):
                if attempt < retries:
                    # A single-threaded server with a full listen backlog
                    # refuses new connections while busy; that looks
                    # identical to "not running" but resolves once the
                    # in-flight request finishes, so it is worth retrying
                    # before concluding the server is actually down.
                    sleep_seconds = delay
                    print(
                        f"    [RETRY] Ferret-UI server refused the connection "
                        f"(likely busy); sleeping {sleep_seconds:.2f}s before "
                        f"retry {attempt + 1}/{retries}"
                    )
                    time.sleep(sleep_seconds)
                    delay = max(delay * 2, DEFAULT_RATE_LIMIT_BACKOFF_SECONDS)
                    attempt += 1
                    continue
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
