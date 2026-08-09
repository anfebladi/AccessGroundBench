"""Exclusive filesystem locking for evaluation result CSVs."""

import os
from datetime import datetime, timezone
from pathlib import Path


class CsvLockError(RuntimeError):
    """Raised when another run already holds the lock for a results CSV."""


def lock_path(results_csv: Path) -> Path:
    """Return the sidecar lock path for a results CSV."""
    return results_csv.with_name(results_csv.name + ".lock")


def acquire_lock(results_csv: Path) -> None:
    """Atomically claim exclusive ownership of a results CSV."""
    path = lock_path(results_csv)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        holder = ""
        try:
            holder = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            pass
        raise CsvLockError(
            f"{results_csv.name} is locked by another run"
            f"{f' ({holder})' if holder else ''}. If that run crashed without "
            f"cleaning up, delete {path.name} or re-run with --force-unlock."
        )
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(
            f"pid={os.getpid()} started={datetime.now(timezone.utc).isoformat()}\n"
        )


def release_lock(results_csv: Path) -> None:
    """Release a results CSV lock, tolerating an absent sidecar."""
    lock_path(results_csv).unlink(missing_ok=True)
