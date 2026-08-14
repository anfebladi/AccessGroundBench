"""Request bodies for the POST/PUT endpoints.

Every field carries the same default its `payload.get(...)` call carried when
these endpoints took an untyped dict, and no field is required. That is
deliberate: a request that was accepted before this module existed must still
be accepted, so the endpoints keep their own hand-written 400s ("model is
required") rather than delegating to schema validation. What these models buy
is a documented, typed, introspectable request shape -- and coercion errors
that surface as a 422 instead of an unhandled 500.

Absent-versus-null matters in a few places, so those fields are `| None` and
are normalised in the handler rather than here: `screens: null` used to read as
an empty list, and `pace_seconds` is only forwarded when explicitly provided.
"""

from __future__ import annotations

from pydantic import BaseModel


class StartEvaluateRun(BaseModel):
    """POST /api/runs -- start a tracked `agb evaluate` subprocess."""

    dataset: str = ""
    model: str = ""
    use_a11y_tree: bool = False
    trials: int | None = None
    pace_seconds: float | None = None
    coord_space: str | None = None
    fresh: bool = False
    force_unlock: bool = False


class SetKey(BaseModel):
    """POST /api/keys -- store one provider's session key in memory."""

    provider: str = ""
    value: str = ""


class SmokeTest(BaseModel):
    """POST /api/smoke-test -- one live model call against one screen."""

    dataset: str = ""
    model: str = ""
    screen: str = ""
    coord_space: str = "pixel"


class AnalyzeRequest(BaseModel):
    """POST /api/analyze -- run the analysis workflow in-process.

    label_changed defaults to None rather than to
    analysis.reports.reachability.DEFAULT_LABEL_CHANGED_MODE so that importing
    this module does not pull in the analysis layer; the handler substitutes the
    real default.
    """

    dataset: str = ""
    sample: str = "all"
    mode: str = "vision"
    permutations: int = 20000
    seed: int = 0
    label_changed: str | None = None


class StartCollectRun(BaseModel):
    """POST /api/collect/runs -- start a tracked `agb collect` subprocess."""

    name: str = ""
    screens: list[str] | None = None
    dry_run: bool = False
    rebuild_manifest: bool = False


__all__ = [
    "AnalyzeRequest",
    "SetKey",
    "SmokeTest",
    "StartCollectRun",
    "StartEvaluateRun",
]
