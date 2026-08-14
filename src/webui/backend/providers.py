"""Provider catalogue -- the single source of truth for provider env var names.

Two different questions get asked about a provider's environment, and they
have different answers:

* *Which variable does a session key write?* Exactly one per provider. A key
  typed into the UI has to land somewhere specific, and `NINEROUTER_BASE_URL`
  is a base URL, not a credential -- setting a key into it would be wrong.
* *Which variables count as "configured"?* Possibly several. Gemini accepts
  either `GEMINI_API_KEY` or `GOOGLE_API_KEY`, and 9router needs its base URL
  as well as its key before a run will work.

Both lists used to exist, under the same name `PROVIDER_ENV_VARS`, in
keys.py and server.py -- so the obvious-looking import was a coin flip
between two different meanings. They live here as one table with two named
fields instead.

Mirrors what a run will actually accept, so the UI's status page cannot
disagree with the evaluation layer -- see evaluation/workflow.py:api_key_exists
and evaluation/providers/config.py:model_configuration_error, which check by
the same prefixes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSpec:
    """One provider's environment contract."""

    key_env: str
    """The single env var a session key sets for this provider."""

    status_env: tuple[str, ...]
    """Every env var that, if set, makes this provider count as configured."""


PROVIDERS: dict[str, ProviderSpec] = {
    "openai": ProviderSpec(
        key_env="OPENAI_API_KEY",
        status_env=("OPENAI_API_KEY",),
    ),
    "gemini": ProviderSpec(
        key_env="GEMINI_API_KEY",
        status_env=("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    ),
    "anthropic": ProviderSpec(
        key_env="ANTHROPIC_API_KEY",
        status_env=("ANTHROPIC_API_KEY",),
    ),
    "9router": ProviderSpec(
        key_env="NINEROUTER_API_KEY",
        status_env=("NINEROUTER_BASE_URL", "NINEROUTER_API_KEY"),
    ),
}


def is_configured_value(value: str | None) -> bool:
    """Whether an env var's value is a real credential rather than a placeholder.

    .env.example ships `your-openai-key-here`-style placeholders; treating one
    as configured would tell the user a run is ready when it will fail on the
    first request.
    """
    if not value:
        return False
    lowered = value.lower()
    return not ("your-" in lowered and "-here" in lowered)


__all__ = ["PROVIDERS", "ProviderSpec", "is_configured_value"]
