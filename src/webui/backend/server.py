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
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import paths

from . import datasets as datasets_mod
from . import keys as keys_mod
from . import runs as runs_mod
from .stdout_capture import capture_stdout

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"

# Providers workflow.api_key_exists / providers.config check by prefix.
# Mirrors that list so the UI's status page matches what a run will actually
# accept -- see evaluation/workflow.py:api_key_exists and
# evaluation/providers/config.py:model_configuration_error.
PROVIDER_ENV_VARS = {
    "openai": ["OPENAI_API_KEY"],
    "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    "9router": ["NINEROUTER_BASE_URL", "NINEROUTER_API_KEY"],
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
# research questions and must never be mistaken for one another, and because
# two samples would otherwise overwrite each other.
ANALYSIS_MODES = ("vision", "tree")
ANALYSIS_SAMPLES = ("all", "primary", "full", "precautionary", "uniform")


def analysis_output_dir(dataset_dir: Path, mode: str, sample: str) -> Path:
    """Return the analysis output directory for one dataset/mode/sample.

    Callers must validate mode and sample against ANALYSIS_MODES /
    ANALYSIS_SAMPLES first; dataset_dir comes from the dataset registry, so
    all three components are known-good directory names rather than free text.
    """
    return paths.analysis_output_path(mode, sample, dataset_dir)


ANALYSIS_TABLE_FILES = {
    "reachability": "reachability_results.csv",
    "pooled_permutation": "pooled_permutation_results.csv",
    "mcnemar_per_model": "mcnemar_results_per_model.csv",
    "direction_consistency": "direction_consistency.csv",
}


def read_analysis_tables(output_dir: Path) -> dict[str, list[dict]]:
    """Read the four analysis-workflow CSVs from one output directory.

    Shared by the GET (read whatever already exists) and POST (read what a
    fresh run just wrote) analysis endpoints, so both return identically
    shaped responses and the Analyze view's rendering code never needs to
    know which one produced its data.
    """
    tables: dict[str, list[dict]] = {}
    for key, filename in ANALYSIS_TABLE_FILES.items():
        path = output_dir / filename
        if not path.is_file():
            tables[key] = []
            continue
        with open(path, newline="", encoding="utf-8") as f:
            tables[key] = list(csv.DictReader(f))
    return tables


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
            detail=f"{name} is an archived dataset and is read-only. "
            "Archived runs are a fixed record of a past experiment; writing to "
            "one would alter results that have already been reported.",
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
        with capture_stdout():
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
                with capture_stdout():
                    rows = load_results(csv_path)
                statuses = Counter(r["status"] for r in rows)
                co_present = [r for r in rows if r["status"] == "co_present"]
                hits = sum(1 for r in co_present if r.get("score") == "1")
                # Restricted to the baseline profile only -- a plain
                # proportion, not an inferential statistic, so computing it
                # here rather than in analysis.stats carries no drift risk
                # the way McNemar/Holm would (see backend.compare's docstring).
                # Lets Results show whether a model's blended accuracy is
                # hiding degradation under altered profiles at a glance.
                baseline_rows = [r for r in co_present if r.get("profile") == "baseline"]
                baseline_hits = sum(1 for r in baseline_rows if r.get("score") == "1")
                out.append({
                    "filename": csv_path.name,
                    "model": model_name_from_path(csv_path),
                    "prompt_mode": rows[0]["prompt_mode"] if rows else "",
                    "row_count": len(rows),
                    "statuses": dict(statuses),
                    "co_present_count": len(co_present),
                    "hits": hits,
                    "accuracy": (hits / len(co_present)) if co_present else None,
                    "baseline_accuracy": (baseline_hits / len(baseline_rows)) if baseline_rows else None,
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
        with capture_stdout():
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

    @app.get("/api/datasets/{name}/results/compare")
    def dataset_compare(
        name: str, model: str, mode: str = "vision", sample: str = "primary"
    ) -> dict:
        """Baseline-vs-profile comparison for one model -- the Compare view.

        Takes a model id and searches the dataset's own result files for it,
        rather than a single filename: the Holm-Bonferroni correction has to
        run across every model discovered for this dataset/mode (see
        backend.compare's module docstring), which needs all of them loaded
        regardless of which one is being displayed.
        """
        from analysis.data.samples import SAMPLE_NAMES

        from .compare import CompareError, compare_model

        info = _dataset_or_404(name)
        if mode not in ANALYSIS_MODES:
            raise HTTPException(status_code=400, detail=f"Unknown mode: {mode!r}")
        if sample not in SAMPLE_NAMES:
            raise HTTPException(status_code=400, detail=f"Unknown sample: {sample!r}")
        try:
            return compare_model(info.path, model, mode=mode, sample=sample)
        except CompareError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

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
                with capture_stdout():
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

    @app.get("/api/datasets/{name}/analysis")
    def dataset_analysis(name: str, mode: str = "vision", sample: str = "all") -> dict:
        """Read whatever analysis tables already exist for this mode/sample,
        without running anything.

        This is the direct fix for the Analyze view only ever showing a
        chart after a multi-minute permutation run: `agb analyze` (or a
        previous browser run) may have already written these CSVs, and
        without this endpoint they were unreachable from the UI. Returns
        the identical shape POST /api/analyze does (via the same
        read_analysis_tables helper), so the Analyze view's render() needs
        no branch for "loaded fresh" versus "loaded existing".
        """
        info = _dataset_or_404(name)
        if mode not in ANALYSIS_MODES:
            raise HTTPException(status_code=400, detail=f"Unknown mode: {mode!r}")
        if sample not in ANALYSIS_SAMPLES:
            raise HTTPException(status_code=400, detail=f"Unknown sample: {sample!r}")

        output_dir = analysis_output_dir(info.path, mode, sample)
        tables = read_analysis_tables(output_dir)
        available = any(tables.values())

        try:
            shown_dir = output_dir.relative_to(paths.PROJECT_ROOT).as_posix()
        except ValueError:
            shown_dir = str(output_dir)

        return {"available": available, "output_dir": shown_dir if available else None, **tables}

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
            with capture_stdout(buf):
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

        try:
            shown_dir = output_dir.relative_to(paths.PROJECT_ROOT).as_posix()
        except ValueError:
            shown_dir = str(output_dir)

        return {
            "log": buf.getvalue(),
            "output_dir": shown_dir,
            **read_analysis_tables(output_dir),
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
    """Launch the loopback FastAPI API and local Vite development server."""
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

    import uvicorn

    from .banner import run_interactive_menu

    parser = argparse.ArgumentParser(description="AccessGroundBench -- local web UI")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--api-port", type=int, default=8081)
    args = parser.parse_args(argv)

    npm = shutil.which("npm")
    vite = FRONTEND_DIR / "node_modules" / ".bin" / ("vite.cmd" if os.name == "nt" else "vite")
    if npm is None or not vite.is_file():
        print(
            "[ERROR] Frontend dependencies are missing. Install them with:\n"
            "  cd src/webui/frontend && npm ci"
        )
        raise SystemExit(1)

    app = create_app()
    # warning, not info: the interactive banner below replaces uvicorn's own
    # startup/access log lines, which would otherwise print through and
    # scramble the banner's redraw-in-place cursor math.
    config = uvicorn.Config(app, host="127.0.0.1", port=args.api_port, log_level="warning")
    uv_server = uvicorn.Server(config)

    server_thread = threading.Thread(target=uv_server.run, daemon=True)
    server_thread.start()

    deadline = time.monotonic() + 10
    while not uv_server.started and server_thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not uv_server.started:
        raise SystemExit(1)  # uvicorn failed to start (e.g. port already in use)

    vite_process: subprocess.Popen[bytes] | None = None
    vite_stderr = tempfile.TemporaryFile(mode="w+b")

    def cleanup() -> None:
        if vite_process is not None and vite_process.poll() is None:
            vite_process.terminate()
            try:
                vite_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                vite_process.kill()
                vite_process.wait()
        uv_server.should_exit = True
        server_thread.join(timeout=5)
        if not vite_stderr.closed:
            vite_stderr.close()

    try:
        vite_process = subprocess.Popen(
            [str(vite), "--host", "127.0.0.1", "--port", str(args.port)],
            cwd=FRONTEND_DIR,
            env={**os.environ, "AGB_API_PORT": str(args.api_port)},
            stdout=subprocess.DEVNULL,
            stderr=vite_stderr,
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if vite_process.poll() is not None:
                vite_stderr.seek(0)
                stderr = vite_stderr.read().decode(errors="replace")
                if isinstance(stderr, str) and stderr.strip():
                    print(f"[ERROR] Vite failed to start:\n{stderr.strip()}")
                raise SystemExit(1)
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{args.port}/", timeout=0.5):
                    break
            except (urllib.error.URLError, OSError):
                time.sleep(0.05)
        else:
            raise SystemExit(1)

        url = f"http://127.0.0.1:{args.port}"

        run_interactive_menu(url, cleanup)
    except BaseException:
        cleanup()
        raise


__all__ = ["create_app", "serve", "ui_main"]
