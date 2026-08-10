"""Session API-key store for the web UI.

A key entered in the UI lives only in this process's memory, for this
server's lifetime -- never written to disk, never logged, never echoed back
to the browser. .env values remain the default; a session key only overrides
its provider's env var for subprocess runs launched after it was set. See
docs/setup.md / .env.example for the provider env var names this mirrors.
"""

from __future__ import annotations

import threading

PROVIDER_ENV_VARS = {
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "9router": "NINEROUTER_API_KEY",
    "openai_compatible": "OPENAI_COMPATIBLE_API_KEY",
}

_lock = threading.Lock()
_session_keys: dict[str, str] = {}


def set_key(provider: str, value: str) -> None:
    if provider not in PROVIDER_ENV_VARS:
        raise ValueError(f"Unknown provider: {provider!r}")
    with _lock:
        if value:
            _session_keys[provider] = value
        else:
            _session_keys.pop(provider, None)


def clear_key(provider: str) -> None:
    with _lock:
        _session_keys.pop(provider, None)


def session_env_overrides() -> dict[str, str]:
    """Return {ENV_VAR_NAME: value} for every provider with a session key set."""
    with _lock:
        return {PROVIDER_ENV_VARS[p]: v for p, v in _session_keys.items()}


def has_session_key(provider: str) -> bool:
    with _lock:
        return provider in _session_keys


__all__ = [
    "PROVIDER_ENV_VARS",
    "set_key",
    "clear_key",
    "session_env_overrides",
    "has_session_key",
]
