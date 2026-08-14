"""Evaluation run endpoints -- preflight, start, poll, cancel.

The preflight lives here rather than with the dataset browsing routes because
it answers a question about a *prospective run* ("how much of this is already
done, and is anything holding the lock?"), not about the dataset's contents.

Runs are subprocesses, not in-process calls -- see runs.py for why.
"""

from __future__ import annotations

import contextlib

from fastapi import APIRouter, HTTPException

import paths

from .. import keys as keys_mod
from .. import runs as runs_mod
from ..dependencies import baseline_screens, dataset_or_404, writable_dataset_or_400
from ..schemas import StartEvaluateRun

router = APIRouter()


@router.get("/api/datasets/{name}/preflight")
def evaluate_preflight(name: str, model: str, use_a11y_tree: bool = False) -> dict:
    from evaluation.config import ALL_PROFILES
    from evaluation.grounding.targets import build_expected_keys
    from evaluation.storage.locking import lock_path
    from evaluation.storage.results import load_completed_keys

    info = dataset_or_404(name)
    if not model:
        raise HTTPException(status_code=400, detail="model is required")

    labels_dir = info.path / "labels"
    expected_keys = build_expected_keys(baseline_screens(labels_dir), labels_dir, ALL_PROFILES)

    # Scoped to the selected dataset explicitly. evaluation.config's
    # module-level DATASET_DIR reflects whatever dataset this server
    # process happened to import under -- not necessarily the one the
    # caller picked in the UI -- so the preflight would otherwise count
    # another dataset's completed rows as this run's progress.
    results_csv = paths.evaluation_results_path(model, use_a11y_tree, info.path)

    already_done = len(load_completed_keys(results_csv)) if results_csv.is_file() else 0
    lock_file = lock_path(results_csv)
    lock_holder = None
    if lock_file.is_file():
        with contextlib.suppress(OSError):
            lock_holder = lock_file.read_text(encoding="utf-8", errors="replace").strip()

    return {
        "model": model,
        "results_csv": results_csv.name,
        "expected_total": len(expected_keys),
        "already_done": min(already_done, len(expected_keys)),
        "lock_present": lock_file.is_file(),
        "lock_holder": lock_holder,
    }


@router.post("/api/runs")
def start_evaluate_run(payload: StartEvaluateRun) -> dict:
    info = writable_dataset_or_400(payload.dataset)
    model = payload.model
    if not model:
        raise HTTPException(status_code=400, detail="model is required")

    extra_env = {
        "VLM_MODEL": model,
        "USE_A11Y_TREE": "true" if payload.use_a11y_tree else "false",
    }
    if payload.trials:
        extra_env["VLM_TRIALS"] = str(payload.trials)
    if payload.pace_seconds is not None:
        extra_env["VLM_PACE_SECONDS"] = str(payload.pace_seconds)
    if payload.coord_space:
        extra_env["COORD_SPACE"] = str(payload.coord_space)
    extra_env.update(keys_mod.session_env_overrides())

    args = runs_mod.evaluate_command(
        info.path,
        fresh=payload.fresh,
        force_unlock=payload.force_unlock,
    )
    env_summary = {
        "AGB_DATASET_DIR": str(info.path),
        "VLM_MODEL": model,
        "USE_A11Y_TREE": extra_env["USE_A11Y_TREE"],
        **{k: v for k, v in extra_env.items()
           if k in ("VLM_TRIALS", "VLM_PACE_SECONDS", "COORD_SPACE")},
    }
    run = runs_mod.start_run(
        "evaluate", args, extra_env=extra_env, env_summary=env_summary,
    )
    return {
        "run_id": run.id,
        "equivalent_command": runs_mod.format_equivalent_command(
            env_summary, "evaluate", args,
        ),
    }


@router.get("/api/runs")
def list_runs() -> list[dict]:
    return [r.to_dict() for r in runs_mod.list_runs()]


@router.get("/api/runs/{run_id}")
def get_run(run_id: str, since: int = 0) -> dict:
    run = runs_mod.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Unknown run")
    lines, next_since = run.tail(since)
    out = run.to_dict()
    out["lines"] = lines
    out["next_since"] = next_since
    return out


@router.post("/api/runs/{run_id}/cancel")
def cancel_run(run_id: str) -> dict:
    ok = runs_mod.cancel_run(run_id)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="Run is not cancellable (unknown or already finished)",
        )
    return {"ok": True}


__all__ = ["router"]
