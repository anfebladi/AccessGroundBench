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


# Legacy private name retained as an identity alias for compatibility.
_is_retryable_error = is_retryable_error
