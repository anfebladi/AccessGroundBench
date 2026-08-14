"""Collection endpoints -- the Collect view.

Collection needs a physical Android device, so the preflight shells out to adb
to report what is attached before the user commits to a run.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException

import paths

from .. import datasets as datasets_mod
from .. import runs as runs_mod
from ..schemas import StartCollectRun

router = APIRouter()


@router.get("/api/collect/screens")
def collect_screens() -> dict:
    from collection.screens import SCREEN_TARGETS, SCREENS

    return {"default_order": SCREENS, "all_screens": sorted(SCREEN_TARGETS)}


@router.get("/api/collect/preflight")
def collect_preflight() -> dict:
    from collection.runtime.device import resolve_adb

    adb_path = resolve_adb()
    adb_available = Path(adb_path).is_file() or shutil.which(adb_path) is not None
    if not adb_available:
        return {
            "adb_path": adb_path, "adb_available": False, "devices": [],
            "error": "adb not found on PATH or under "
            r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe.",
        }

    try:
        result = subprocess.run(
            [adb_path, "devices"], capture_output=True, text=True, timeout=10, check=True,
        )
    except Exception as exc:
        return {
            "adb_path": adb_path, "adb_available": True, "devices": [],
            "error": f"{type(exc).__name__}: {exc}",
        }

    devices = []
    for line in result.stdout.strip().splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            devices.append({"serial": parts[0], "status": parts[1]})

    return {"adb_path": adb_path, "adb_available": True, "devices": devices, "error": None}


@router.post("/api/collect/runs")
def start_collect_run(payload: StartCollectRun) -> dict:
    name = payload.name.strip()
    # Collection always targets datasets/<name>/, never the shipped
    # dataset/ directory or the archived experiment_N/ dirs -- the
    # dataset dropdown intentionally keeps those separate (see the
    # discovery conversation this UI's plan settled on) so collecting
    # into a new name can never overwrite the paper's committed data.
    if not name or name in ("dataset", *datasets_mod.ARCHIVED_NAMES) \
            or any(sep in name for sep in ("/", "\\")) or ".." in name:
        raise HTTPException(
            status_code=400,
            detail="name must be a plain directory name, not 'dataset' or an archived experiment name.",
        )

    dataset_path = paths.PROJECT_ROOT / "datasets" / name
    args = ["--data-dir", str(dataset_path)]
    screens = payload.screens or []
    if screens:
        args += ["--screens", *screens]
    if payload.dry_run:
        args.append("--dry-run")
    if payload.rebuild_manifest:
        args.append("--rebuild-manifest")

    env_summary = {"AGB_DATASET_DIR": str(dataset_path)}
    run = runs_mod.start_run("collect", args, extra_env={}, env_summary=env_summary)
    return {
        "run_id": run.id,
        # AGB_DATASET_DIR is the only entry in env_summary and the formatter
        # drops it (--data-dir already carries it), so this renders exactly the
        # "agb collect ..." string this endpoint has always returned.
        "equivalent_command": runs_mod.format_equivalent_command(
            env_summary, "collect", args,
        ),
    }


__all__ = ["router"]
