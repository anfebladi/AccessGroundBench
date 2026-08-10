"""Subprocess run supervisor for evaluate/collect runs launched from the UI.

Runs execute as a subprocess rather than in-process for three reasons
documented in the plan: evaluation.workflow.evaluate() and
collection.workflow.run_collection() call sys.exit(1) on validation failure
and on a partial run, which would otherwise kill this web server; every
config knob is read from os.environ, which is process-global and unsafe to
mutate per-request in a long-lived server; and a subprocess is trivially
killable, unlike an in-process call already deep in a retry loop.

PYTHONUNBUFFERED is not optional here: nothing in src/ calls
print(flush=True), so piped stdout is block-buffered and progress would
arrive in multi-KB lumps instead of line by line.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import paths

MAX_LOG_LINES = 5000

STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"


@dataclass
class Run:
    id: str
    command: list[str]
    env_summary: dict[str, str]
    started_at: float
    process: subprocess.Popen | None = None
    status: str = STATUS_RUNNING
    exit_code: int | None = None
    lines: deque = field(default_factory=lambda: deque(maxlen=MAX_LOG_LINES))
    lock: threading.Lock = field(default_factory=threading.Lock)
    finished_at: float | None = None

    def append_line(self, line: str) -> None:
        with self.lock:
            self.lines.append(line)

    def tail(self, since: int = 0) -> tuple[list[str], int]:
        """Return (new_lines, next_since) for lines appended after index `since`."""
        with self.lock:
            total = len(self.lines)
            all_lines = list(self.lines)
        # The deque can silently drop the oldest lines once MAX_LOG_LINES is
        # exceeded; `since` is treated as best-effort rather than an exact
        # offset into a file, so a long run's UI tail may skip ahead instead
        # of erroring.
        start = max(0, since)
        return all_lines[start:], total

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "command": self.command,
            "status": self.status,
            "exit_code": self.exit_code,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "env_summary": self.env_summary,
        }


_runs: dict[str, Run] = {}
_runs_lock = threading.Lock()


def _reader_thread(run: Run) -> None:
    assert run.process is not None and run.process.stdout is not None
    for raw_line in run.process.stdout:
        run.append_line(raw_line.rstrip("\n"))
    run.process.stdout.close()
    exit_code = run.process.wait()
    run.exit_code = exit_code
    run.finished_at = time.monotonic()
    if run.status != STATUS_CANCELLED:
        run.status = STATUS_COMPLETED if exit_code == 0 else STATUS_FAILED


def start_run(
    subcommand: str,
    args: list[str],
    *,
    extra_env: dict[str, str],
    env_summary: dict[str, str],
) -> Run:
    """Launch `agb <subcommand> <args>` as a tracked subprocess.

    extra_env is merged over the current environment (so .env values loaded
    by this server process are inherited, then overridden per-run).
    env_summary is what gets shown back to the UI/run log -- deliberately
    excludes API key values even when extra_env carries one.
    """
    run_id = uuid.uuid4().hex[:12]
    code = "import sys, cli; sys.exit(cli.main(sys.argv[1:]) or 0)"
    command = [sys.executable, "-c", code, subcommand, *args]

    env = dict(os.environ)
    env.update(extra_env)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    process = subprocess.Popen(
        command,
        cwd=str(paths.PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    run = Run(
        id=run_id, command=command, env_summary=env_summary,
        started_at=time.monotonic(), process=process,
    )
    with _runs_lock:
        _runs[run_id] = run

    thread = threading.Thread(target=_reader_thread, args=(run,), daemon=True)
    thread.start()
    return run


def get_run(run_id: str) -> Run | None:
    with _runs_lock:
        return _runs.get(run_id)


def list_runs() -> list[Run]:
    with _runs_lock:
        return sorted(_runs.values(), key=lambda r: r.started_at, reverse=True)


def cancel_run(run_id: str) -> bool:
    run = get_run(run_id)
    if run is None or run.process is None or run.status != STATUS_RUNNING:
        return False
    run.status = STATUS_CANCELLED
    run.process.terminate()
    try:
        run.process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        run.process.kill()
    return True


def evaluate_command(
    dataset_path: Path,
    *,
    fresh: bool = False,
    force_unlock: bool = False,
) -> list[str]:
    args = ["--data-dir", str(dataset_path)]
    if fresh:
        args.append("--fresh")
    if force_unlock:
        args.append("--force-unlock")
    return args


__all__ = [
    "Run",
    "STATUS_RUNNING", "STATUS_COMPLETED", "STATUS_FAILED", "STATUS_CANCELLED",
    "start_run", "get_run", "list_runs", "cancel_run", "evaluate_command",
]
