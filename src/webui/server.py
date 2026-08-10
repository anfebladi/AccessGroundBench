"""FastAPI app and `agb ui` entry point for the AccessGroundBench local UI.

Binds 127.0.0.1 only, always -- not configurable. Session API keys live in
this process's memory (see .keys), so the server must never accept
connections from beyond localhost.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import sys
import threading
from pathlib import Path
from typing import Any

import paths

from . import datasets as datasets_mod
from . import keys as keys_mod
from . import runs as runs_mod

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Providers workflow.api_key_exists / providers.config check by prefix.
# Mirrors that list so the UI's status page matches what a run will actually
# accept -- see evaluation/workflow.py:api_key_exists and
# evaluation/providers/config.py:model_configuration_error.
PROVIDER_ENV_VARS = {
    "openai": ["OPENAI_API_KEY"],
    "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    "9router": ["NINEROUTER_BASE_URL", "NINEROUTER_API_KEY"],
    "openai_compatible": ["OPENAI_COMPATIBLE_BASE_URL", "OPENAI_COMPATIBLE_API_KEY"],
}

# Env mutation (for the smoke test's direct call into evaluation.providers)
# is process-global; serialize it so two concurrent smoke-test requests
# cannot interleave and borrow each other's temporary key.
_env_mutation_lock = threading.Lock()

# Dataset, mode, and sample are all part of an analysis output path.
#
# The dataset, because `agb analyze` names its outputs after the analysis
# rather than the run: without it, re-analysing an archive from the browser
# would overwrite the current run's reachability/pooled/McNemar/sign tables.
# From a terminal that would at least be a deliberate act; from the browser it
# is one click on the page you land on. Archived datasets in particular must
# never be written to, and their outputs must never displace anyone else's.
# Mode and sample, because a vision run and a tree run answer different
# research questions and must never be mistaken for one another (CLAUDE.md 5),
# and because two samples would otherwise overwrite each other.
ANALYSIS_MODES = ("vision", "tree")
ANALYSIS_SAMPLES = ("all", "primary", "full", "precautionary", "uniform")


def analysis_output_dir(dataset_dir: Path, mode: str, sample: str) -> Path:
    """Return the analysis output directory for one dataset/mode/sample.

    Callers must validate mode and sample against ANALYSIS_MODES /
    ANALYSIS_SAMPLES first; dataset_dir comes from the dataset registry, so
    all three components are known-good directory names rather than free text.
    """
    return paths.analysis_output_path(mode, sample, dataset_dir)


def _evaluations_root(info) -> Path:
    """Return the evaluation outputs owned by one dataset record."""
    return paths.evaluations_dir(info.path)


def _is_configured_value(value: str | None) -> bool:
    if not value:
        return False
    lowered = value.lower()
    return not ("your-" in lowered and "-here" in lowered)


def _dataset_or_404(name: str):
    from fastapi import HTTPException

    info = next((d for d in datasets_mod.discover_datasets() if d.name == name), None)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Unknown dataset: {name}")
    return info


def _writable_dataset_or_400(name: str):
    from fastapi import HTTPException

    info = _dataset_or_404(name)
    if info.is_archived:
        raise HTTPException(
            status_code=400,
            detail=f"{name} is an archived dataset and is read-only "
            "(see CLAUDE.md/repo memory: never write into dataset/experiment_N/).",
        )
    return info


def create_app():
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse, JSONResponse

    app = FastAPI(title="AccessGroundBench UI")

    @app.get("/api/datasets")
    def list_datasets() -> list[dict]:
        return [d.to_dict() for d in datasets_mod.discover_datasets()]

    @app.get("/api/datasets/{name}/screens")
    def dataset_screens(name: str) -> dict:
        info = _dataset_or_404(name)
        labels_dir = info.path / "labels"
        screens = sorted(
            p.stem.replace("_baseline", "") for p in labels_dir.glob("*_baseline.json")
        )
        return {"screens": screens}

    @app.get("/api/datasets/{name}/targets/{screen}")
    def dataset_targets(name: str, screen: str) -> dict:
        from evaluation.grounding.targets import harvest_targets

        info = _dataset_or_404(name)
        targets = harvest_targets(screen, info.path / "labels")
        return {"targets": targets}

    @app.get("/api/datasets/{name}/image/{screen}/{profile}")
    def dataset_image(name: str, screen: str, profile: str):
        info = _dataset_or_404(name)
        image_path = info.path / "images" / f"{screen}_{profile}.png"
        if not image_path.is_file():
            raise HTTPException(status_code=404, detail=f"No image: {image_path.name}")
        return FileResponse(image_path, media_type="image/png")

    @app.get("/api/datasets/{name}/labels/{screen}/{profile}")
    def dataset_labels(name: str, screen: str, profile: str) -> list[dict]:
        info = _dataset_or_404(name)
        label_path = info.path / "labels" / f"{screen}_{profile}.json"
        if not label_path.is_file():
            raise HTTPException(status_code=404, detail=f"No labels: {label_path.name}")
        return json.loads(label_path.read_text(encoding="utf-8"))

    @app.get("/api/datasets/{name}/manifest")
    def dataset_manifest(name: str) -> dict:
        info = _dataset_or_404(name)
        manifest_path = info.path / "collection_manifest.json"
        if not manifest_path.is_file():
            return {"available": False}
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return {"available": True, "manifest": data}

    @app.get("/api/datasets/{name}/results")
    def dataset_results(name: str) -> list[dict]:
        from collections import Counter

        from analysis.data.results import (
            discover_result_csvs, load_results, model_name_from_path,
        )

        info = _dataset_or_404(name)
        out = []
        # Both arms, listed separately: discovery deliberately refuses to
        # return them together so no caller can pool them by accident.
        for mode in ANALYSIS_MODES:
            for csv_path in discover_result_csvs(info.path, mode):
                with contextlib.redirect_stdout(io.StringIO()):
                    rows = load_results(csv_path)
                statuses = Counter(r["status"] for r in rows)
                co_present = [r for r in rows if r["status"] == "co_present"]
                hits = sum(1 for r in co_present if r.get("score") == "1")
                out.append({
                    "filename": csv_path.name,
                    "model": model_name_from_path(csv_path),
                    "prompt_mode": rows[0]["prompt_mode"] if rows else "",
                    "row_count": len(rows),
                    "statuses": dict(statuses),
                    "co_present_count": len(co_present),
                    "hits": hits,
                    "accuracy": (hits / len(co_present)) if co_present else None,
                })
        return out

    @app.get("/api/datasets/{name}/results/{filename}/rows")
    def dataset_result_rows(name: str, filename: str) -> list[dict]:
        from analysis.data.results import load_results

        info = _dataset_or_404(name)
        evaluations_root = _evaluations_root(info)
        csv_path = (evaluations_root / filename).resolve()
        # Resolve first, then confirm the result is still inside the dataset's
        # own evaluations directory: `filename` is caller-supplied, and a
        # traversal must not reach another dataset's rows or the wider disk.
        if (evaluations_root.resolve() not in csv_path.parents or
                not csv_path.is_file() or not csv_path.name.endswith(".csv")):
            raise HTTPException(status_code=404, detail=f"No such results file: {filename}")
        with contextlib.redirect_stdout(io.StringIO()):
            rows = load_results(csv_path)
        # Trim to what the Results-tab miss inspector needs; the full CSV
        # (raw_response, trial_scores, coord_space, ...) stays on disk for
        # anyone who wants it -- no need to duplicate all 18 columns here.
        return [
            {
                "screen": r.get("screen", ""),
                "target_text": r.get("target_text", ""),
                "profile": r.get("profile", ""),
                "status": r.get("status", ""),
                "score": r.get("score", ""),
                "x_pred": r.get("x_pred", ""),
                "y_pred": r.get("y_pred", ""),
                "x_min": r.get("x_min", ""),
                "y_min": r.get("y_min", ""),
                "x_max": r.get("x_max", ""),
                "y_max": r.get("y_max", ""),
                "raw_response": r.get("raw_response", ""),
                "parse_method": r.get("parse_method", ""),
            }
            for r in rows
        ]

    @app.get("/api/datasets/{name}/preflight")
    def evaluate_preflight(name: str, model: str, use_a11y_tree: bool = False) -> dict:
        from evaluation.config import ALL_PROFILES
        from evaluation.grounding.targets import build_expected_keys
        from evaluation.storage.locking import lock_path
        from evaluation.storage.results import load_completed_keys

        info = _dataset_or_404(name)
        if not model:
            raise HTTPException(status_code=400, detail="model is required")

        labels_dir = info.path / "labels"
        screens = sorted(
            p.stem.replace("_baseline", "") for p in labels_dir.glob("*_baseline.json")
        )
        expected_keys = build_expected_keys(screens, labels_dir, ALL_PROFILES)

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

    @app.get("/api/providers")
    def provider_status() -> list[dict]:
        import os

        out = []
        for provider, env_vars in PROVIDER_ENV_VARS.items():
            env_configured = any(_is_configured_value(os.environ.get(v)) for v in env_vars)
            session_configured = keys_mod.has_session_key(provider)
            out.append({
                "provider": provider,
                "env_vars": env_vars,
                "env_configured": env_configured,
                "session_configured": session_configured,
                "configured": env_configured or session_configured,
            })
        return out

    @app.post("/api/keys")
    def set_key(payload: dict) -> dict:
        provider = payload.get("provider", "")
        value = payload.get("value", "")
        try:
            keys_mod.set_key(provider, value)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"ok": True}

    @app.delete("/api/keys/{provider}")
    def clear_key(provider: str) -> dict:
        keys_mod.clear_key(provider)
        return {"ok": True}

    @app.post("/api/smoke-test")
    def smoke_test(payload: dict) -> dict:
        import os

        from evaluation.smoke import smoke_test_model

        info = _dataset_or_404(payload.get("dataset", ""))
        model = payload.get("model", "")
        screen = payload.get("screen", "")
        coord_space = payload.get("coord_space", "pixel")
        if not model or not screen:
            raise HTTPException(status_code=400, detail="model and screen are required")

        overrides = keys_mod.session_env_overrides()
        with _env_mutation_lock:
            previous = {k: os.environ.get(k) for k in overrides}
            os.environ.update(overrides)
            try:
                result = smoke_test_model(
                    model, screen,
                    images_dir=info.path / "images",
                    labels_dir=info.path / "labels",
                    coord_space=coord_space,
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

    @app.post("/api/runs")
    def start_evaluate_run(payload: dict) -> dict:
        info = _writable_dataset_or_400(payload.get("dataset", ""))
        model = payload.get("model", "")
        if not model:
            raise HTTPException(status_code=400, detail="model is required")

        use_a11y_tree = bool(payload.get("use_a11y_tree", False))
        extra_env = {
            "VLM_MODEL": model,
            "USE_A11Y_TREE": "true" if use_a11y_tree else "false",
        }
        if payload.get("trials"):
            extra_env["VLM_TRIALS"] = str(payload["trials"])
        if payload.get("pace_seconds") is not None:
            extra_env["VLM_PACE_SECONDS"] = str(payload["pace_seconds"])
        if payload.get("coord_space"):
            extra_env["COORD_SPACE"] = str(payload["coord_space"])
        extra_env.update(keys_mod.session_env_overrides())

        args = runs_mod.evaluate_command(
            info.path,
            fresh=bool(payload.get("fresh", False)),
            force_unlock=bool(payload.get("force_unlock", False)),
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
        return {"run_id": run.id, "equivalent_command": _format_equivalent_command(
            env_summary, "evaluate", args,
        )}

    @app.get("/api/runs")
    def list_runs() -> list[dict]:
        return [r.to_dict() for r in runs_mod.list_runs()]

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str, since: int = 0) -> dict:
        run = runs_mod.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Unknown run")
        lines, next_since = run.tail(since)
        out = run.to_dict()
        out["lines"] = lines
        out["next_since"] = next_since
        return out

    @app.post("/api/runs/{run_id}/cancel")
    def cancel_run(run_id: str) -> dict:
        ok = runs_mod.cancel_run(run_id)
        if not ok:
            raise HTTPException(status_code=400, detail="Run is not cancellable (unknown or already finished)")
        return {"ok": True}

    @app.post("/api/analyze")
    def analyze(payload: dict) -> dict:
        from analysis.reports.reachability import DEFAULT_LABEL_CHANGED_MODE
        from analysis.workflow import run_analysis

        info = _dataset_or_404(payload.get("dataset", ""))
        sample = payload.get("sample", "all")
        mode = payload.get("mode", "vision")
        permutations = int(payload.get("permutations", 20000))
        seed = int(payload.get("seed", 0))
        label_changed = payload.get("label_changed", DEFAULT_LABEL_CHANGED_MODE)

        if sample not in ANALYSIS_SAMPLES:
            raise HTTPException(status_code=400, detail=f"Unknown sample: {sample}")
        if mode not in ANALYSIS_MODES:
            raise HTTPException(status_code=400, detail=f"Unknown mode: {mode}")

        output_dir = analysis_output_dir(info.path, mode, sample)
        output_dir.mkdir(parents=True, exist_ok=True)

        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                run_analysis(
                    info.path, None, permutations, seed, mode, sample, label_changed,
                    output_dir=output_dir,
                )
        except SystemExit as exc:
            if exc.code not in (0, None):
                raise HTTPException(
                    status_code=400,
                    detail=f"Analysis failed: {buf.getvalue().strip().splitlines()[-1] if buf.getvalue().strip() else 'see server log'}",
                )

        def _read_csv(filename: str) -> list[dict]:
            path = output_dir / filename
            if not path.is_file():
                return []
            with open(path, newline="", encoding="utf-8") as f:
                return list(csv.DictReader(f))

        try:
            shown_dir = output_dir.relative_to(paths.PROJECT_ROOT).as_posix()
        except ValueError:
            shown_dir = str(output_dir)

        return {
            "log": buf.getvalue(),
            "output_dir": shown_dir,
            "reachability": _read_csv("reachability_results.csv"),
            "pooled_permutation": _read_csv("pooled_permutation_results.csv"),
            "mcnemar_per_model": _read_csv("mcnemar_results_per_model.csv"),
            "direction_consistency": _read_csv("direction_consistency.csv"),
        }

    @app.get("/api/collect/screens")
    def collect_screens() -> dict:
        from collection.screens import SCREEN_TARGETS, SCREENS

        return {"default_order": SCREENS, "all_screens": sorted(SCREEN_TARGETS)}

    @app.get("/api/collect/preflight")
    def collect_preflight() -> dict:
        import shutil
        import subprocess as sp

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
            result = sp.run(
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

    @app.post("/api/collect/runs")
    def start_collect_run(payload: dict) -> dict:
        name = (payload.get("name") or "").strip()
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
        screens = payload.get("screens") or []
        if screens:
            args += ["--screens", *screens]
        dry_run = bool(payload.get("dry_run", False))
        if dry_run:
            args.append("--dry-run")
        if payload.get("rebuild_manifest"):
            args.append("--rebuild-manifest")

        env_summary = {"AGB_DATASET_DIR": str(dataset_path)}
        run = runs_mod.start_run("collect", args, extra_env={}, env_summary=env_summary)
        return {
            "run_id": run.id,
            "equivalent_command": f"agb collect {' '.join(args)}",
        }

    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    return app


def _format_equivalent_command(env_summary: dict, subcommand: str, args: list[str]) -> str:
    env_prefix = " ".join(f'{k}={v}' for k, v in env_summary.items() if k != "AGB_DATASET_DIR")
    quoted_args = " ".join(args)
    return f"{env_prefix} agb {subcommand} {quoted_args}".strip()


def serve(host: str, port: int) -> None:
    """Run the server in the foreground with uvicorn's own logging.

    Kept as a plain, non-interactive entry point for anything that wants the
    server without the terminal banner/menu below (e.g. a future test or
    script) -- `ui_main` is what `agb ui` actually calls.
    """
    import uvicorn

    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")


def ui_main(argv: list[str] | None = None) -> None:
    """`agb ui` entry point. Always binds 127.0.0.1 -- see module docstring."""
    if hasattr(sys.stdout, "reconfigure"):
        # The banner's rocket emoji crashes under Windows' default console
        # codepage (cp1252) otherwise -- same fix evaluation.cli.evaluate_main
        # already applies for the same reason.
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError:
        print(
            "[ERROR] The web UI needs the 'ui' extra. Install it with:\n"
            "  uv sync --extra ui\n"
            "or:\n"
            "  pip install -e .[ui]"
        )
        raise SystemExit(1)

    import time

    import uvicorn

    from .banner import run_interactive_menu

    parser = argparse.ArgumentParser(description="AccessGroundBench -- local web UI")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args(argv)

    app = create_app()
    # warning, not info: the interactive banner below replaces uvicorn's own
    # startup/access log lines, which would otherwise print through and
    # scramble the banner's redraw-in-place cursor math.
    config = uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning")
    uv_server = uvicorn.Server(config)

    server_thread = threading.Thread(target=uv_server.run, daemon=True)
    server_thread.start()

    deadline = time.monotonic() + 10
    while not uv_server.started and server_thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server_thread.is_alive():
        raise SystemExit(1)  # uvicorn failed to start (e.g. port already in use)

    url = f"http://127.0.0.1:{args.port}"

    def shutdown() -> None:
        uv_server.should_exit = True
        server_thread.join(timeout=5)

    run_interactive_menu(url, shutdown)


__all__ = ["create_app", "serve", "ui_main"]
