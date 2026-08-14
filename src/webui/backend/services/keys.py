"""Session API-key store for the web UI.

A key entered in the UI lives only in this process's memory, for this
server's lifetime -- never written to disk, never logged, never echoed back
to the browser. .env values remain the default; a session key only overrides
its provider's env var for subprocess runs launched after it was set. See
docs/setup.md / .env.example for the provider env var names this mirrors.
"""

from __future__ import annotations

import threading

from .providers import PROVIDERS

# provider -> the one env var a session key sets. Derived from the provider
# catalogue rather than restated: this is not the same list as a provider's
# status vars (see providers.py), and keeping a second literal copy here is
# what let the two drift apart under the same name.
PROVIDER_ENV_VARS = {name: spec.key_env for name, spec in PROVIDERS.items()}

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
