"""Provider, session-key, and smoke-test endpoints -- the Models view.

The smoke test is the one endpoint that calls a model provider directly from
this process instead of going through the run supervisor, because it is a
single request whose result the UI shows immediately. That means mutating
os.environ, which is process-global -- hence the lock below.
"""

from __future__ import annotations

import os
import threading

from fastapi import APIRouter, HTTPException

from ..services import keys as keys_mod
from .dependencies import dataset_or_404
from ..services.providers import PROVIDERS, is_configured_value
from .schemas import SetKey, SmokeTest
from ..services.stdout_capture import capture_stdout

router = APIRouter()

# Env mutation (for the smoke test's direct call into evaluation.providers)
# is process-global; serialize it so two concurrent smoke-test requests
# cannot interleave and borrow each other's temporary key.
_env_mutation_lock = threading.Lock()


@router.get("/api/providers")
def provider_status() -> list[dict]:
    out = []
    for provider, spec in PROVIDERS.items():
        env_vars = list(spec.status_env)
        env_configured = any(is_configured_value(os.environ.get(v)) for v in env_vars)
        session_configured = keys_mod.has_session_key(provider)
        out.append({
            "provider": provider,
            "env_vars": env_vars,
            "env_configured": env_configured,
            "session_configured": session_configured,
            "configured": env_configured or session_configured,
        })
    return out


@router.post("/api/keys")
def set_key(payload: SetKey) -> dict:
    try:
        keys_mod.set_key(payload.provider, payload.value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@router.delete("/api/keys/{provider}")
def clear_key(provider: str) -> dict:
    keys_mod.clear_key(provider)
    return {"ok": True}


@router.post("/api/smoke-test")
def smoke_test(payload: SmokeTest) -> dict:
    from evaluation.smoke import smoke_test_model

    info = dataset_or_404(payload.dataset)
    if not payload.model or not payload.screen:
        raise HTTPException(status_code=400, detail="model and screen are required")

    overrides = keys_mod.session_env_overrides()
    with _env_mutation_lock:
        previous = {k: os.environ.get(k) for k in overrides}
        os.environ.update(overrides)
        try:
            with capture_stdout():
                result = smoke_test_model(
                    payload.model, payload.screen,
                    images_dir=info.path / "images",
                    labels_dir=info.path / "labels",
                    coord_space=payload.coord_space,
                )
        finally:
            for k, v in previous.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    return {
        "ok": result.ok,
        "model": result.model,
        "screen": result.screen,
        "target_text": result.target_text,
        "raw_response": result.raw_response,
        "x_pred": result.x_pred,
        "y_pred": result.y_pred,
        "box": result.box,
        "hit": result.hit,
        "latency_seconds": result.latency_seconds,
        "coord_space_detected": result.coord_space_detected,
        "coord_space_used": result.coord_space_used,
        "coord_space_mismatch": result.coord_space_mismatch,
        "error": result.error,
    }


__all__ = ["router"]
