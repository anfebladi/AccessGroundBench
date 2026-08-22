"""Retry, timeout, and sampling policy for provider calls."""

import os
import re

MAX_RETRIES_ENV_VAR = "VLM_MAX_RETRIES"
DEFAULT_MAX_RETRIES = 3
DEFAULT_RATE_LIMIT_BACKOFF_SECONDS = 0.5
REQUEST_TIMEOUT_ENV_VAR = "VLM_REQUEST_TIMEOUT_SECONDS"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 120.0
TEMPERATURE_ENV_VAR = "VLM_TEMPERATURE"
DEFAULT_TEMPERATURE = 0.0
MAX_TOKENS_ENV_VAR = "VLM_MAX_TOKENS"
THINKING_ENV_VAR = "VLM_THINKING"
THINKING_MODES = ("adaptive", "disabled")
STRUCTURED_COORDS_ENV_VAR = "VLM_STRUCTURED_COORDS"

# Schema for a coordinate-only reply. Deliberately an array rather than
# {"x": .., "y": ..}: the rendered JSON then contains a literal "[x, y]", which
# the existing bracket parser reads unchanged, so turning this on cannot alter
# how any reply is interpreted. Item-count constraints are omitted because the
# structured-output schema subset does not support them.
COORDINATE_SCHEMA = {
    "type": "object",
    "properties": {
        "coordinates": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "exactly two integers: the x pixel then the y pixel",
        }
    },
    "required": ["coordinates"],
    "additionalProperties": False,
}

def resolve_request_timeout(
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


def resolve_temperature(temperature: float | None = None) -> float | None:
    """
    Resolve the sampling temperature, defaulting to 0 for reproducibility.

    At the provider's default temperature a score is a single stochastic
    draw, so a marginal result cannot be distinguished from a coin flip. Set
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


def resolve_max_tokens(max_tokens: int | None = None) -> int | None:
    """Resolve the reply token budget, or None to send no budget at all.

    Unset is the default because it is what every already-collected model ran
    under: sending a budget where none was sent before would change the request
    shape for the existing roster, making a re-run non-comparable with its own
    committed CSV.

    Worth setting for a model that thinks. Reasoning and the answer share this
    budget, and with nothing specified the ceiling is whatever the provider or
    LiteLLM picks (LiteLLM injects 4096 for Anthropic, which requires the
    field) -- an inherited limit that a library upgrade can move underneath a
    run.
    """
    if max_tokens is None:
        raw = os.environ.get(MAX_TOKENS_ENV_VAR, "").strip()
        if not raw:
            return None
        try:
            max_tokens = int(raw)
        except ValueError:
            print(f"[ERROR] {MAX_TOKENS_ENV_VAR} must be an integer, got: {raw}")
            raise SystemExit(1)

    if max_tokens < 1:
        print(f"[ERROR] {MAX_TOKENS_ENV_VAR} must be >= 1, got: {max_tokens}")
        raise SystemExit(1)
    return max_tokens


def resolve_thinking(thinking: str | None = None) -> dict | None:
    """Resolve the extended-thinking configuration, or None to leave it to the provider.

    Empty (the default) sends nothing, so each provider's own default applies --
    which is not uniform: Claude Opus 5 and Sonnet 5 think by default while
    Haiku 4.5 does not. Set this explicitly when a run needs every model on the
    same footing, because whether a model reasons before answering is a
    difference in test-time compute, not just in cost.
    """
    raw = (thinking if thinking is not None
           else os.environ.get(THINKING_ENV_VAR, "")).strip().lower()
    if not raw:
        return None
    if raw not in THINKING_MODES:
        print(f"[ERROR] {THINKING_ENV_VAR} must be one of "
              f"{THINKING_MODES}, got: {raw!r}")
        raise SystemExit(1)
    return {"type": raw}


def resolve_structured_coords(enabled: bool | None = None) -> dict | None:
    """Return a response_format constraining the reply to coordinates, or None.

    Off by default, because it changes the request shape: a model run with it
    is not strictly comparable to one run without. Worth turning on for a model
    that ignores the prompt's format instruction -- Haiku 4.5 answered with
    ~650 characters of prose per query where Sonnet 4.6, same prompt, answered
    in 16 -- which costs output tokens and leaves the reply's coordinates
    embedded among intermediate ones.
    """
    if enabled is None:
        raw = os.environ.get(STRUCTURED_COORDS_ENV_VAR, "").strip().lower()
        if not raw:
            return None
        if raw not in ("true", "1", "yes", "false", "0", "no"):
            print(f"[ERROR] {STRUCTURED_COORDS_ENV_VAR} must be a boolean, got: {raw!r}")
            raise SystemExit(1)
        enabled = raw in ("true", "1", "yes")
    if not enabled:
        return None
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "coordinates",
            "schema": COORDINATE_SCHEMA,
            "strict": True,
        },
    }


def is_temperature_rejection(exc: Exception) -> bool:
    """Detect providers that refuse an explicit temperature (some reasoning models)."""
    message = str(exc).lower()
    return "temperature" in message and any(
        token in message
        for token in ("unsupported", "not supported", "does not support", "invalid", "unrecognized")
    )


def resolve_max_retries(max_retries: int | None = None) -> int:
    """Resolve retry count from explicit argument or VLM_MAX_RETRIES."""
    if max_retries is not None:
        resolved = max_retries
    else:
        raw_retries = os.environ.get(MAX_RETRIES_ENV_VAR, "").strip()
        resolved = DEFAULT_MAX_RETRIES if not raw_retries else int(raw_retries)

    if resolved < 0:
        raise ValueError(f"{MAX_RETRIES_ENV_VAR} must be >= 0")

    return resolved


def is_rate_limit_error(exc: Exception) -> bool:
    """Detect LiteLLM/provider rate-limit errors without importing LiteLLM eagerly."""
    class_name = exc.__class__.__name__.lower()
    if "ratelimit" in class_name or "rate_limit" in class_name or "overload" in class_name:
        return True

    status_code = getattr(exc, "status_code", None)
    if status_code in (429, 503):
        return True

    exc_str = str(exc).lower()
    return "rate limit" in exc_str or "try again" in exc_str or "later" in exc_str or "overload" in exc_str


def is_retryable_error(exc: Exception) -> bool:
    """Detect transient provider failures worth retrying.

    Covers rate limits plus timeouts, connection drops, and 5xx responses. A
    single hung request used to abort an entire multi-hundred-call sweep,
    discarding every row already collected, because only rate limits were
    retried and the runner treats any surviving exception as fatal.
    """
    if is_rate_limit_error(exc):
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


def retry_delay_seconds(exc: Exception, fallback: float) -> float:
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
