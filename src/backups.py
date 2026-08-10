"""Copy results aside before anything destroys them.

Several commands legitimately replace files that took real time and money to
produce: `agb evaluate` recreates a results CSV whose schema it cannot resume
into, and `agb analyze` rewrites its result tables on every run. Both used to
truncate in place, so a column rename or a stray `--permutations` was enough to
lose ~930 rows of paid API calls, or the numbers behind a committed table.

The protection is deliberately passive. It never refuses, never prompts, and
needs no flag, because the data most at risk belongs to someone who just
finished an experiment and has not yet marked it as anything -- they did
nothing wrong and should not have to know this module exists.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

BACKUP_DIR_NAME = ".backups"


class BackupError(RuntimeError):
    """A backup could not be made, so the caller must not destroy anything."""


def _timestamp() -> str:
    """Return a sortable, filesystem-safe UTC timestamp."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%f")[:-3] + "Z"


def backup_dir_for(target: Path) -> Path:
    """Return the backup directory that would hold copies of *target*.

    A subdirectory, never a sibling. `discover_result_csvs` globs
    `*_<mode>.csv` directly inside a dataset's evaluations directory, so a
    backup left beside the originals would be discovered as an extra model and
    silently inflate the pooled permutation test's sample. The non-recursive
    glob cannot see into a subdirectory.
    """
    return target.parent / BACKUP_DIR_NAME


def preserve(target: Path, *, reason: str) -> Path | None:
    """Copy *target* aside before the caller destroys it.

    Returns the backup path, or None when there is nothing to preserve.
    Handles both files and directories.

    Raises BackupError if the copy fails. Callers must let that propagate:
    proceeding to truncate after a failed backup is the exact outcome this
    module exists to prevent, so a swallowed error here is worse than no
    backup at all.
    """
    if not target.exists():
        return None

    # Timestamped, so repeated runs accumulate rather than overwrite each
    # other. The older `.bak` convention was a single slot -- the second run
    # destroyed the first run's backup, which made it useless in exactly the
    # repeated-experiment case that needs it most.
    stem = target.stem if target.is_file() else target.name
    suffix = target.suffix if target.is_file() else ""
    destination = backup_dir_for(target) / f"{stem}_{_timestamp()}{suffix}"

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if target.is_dir():
            shutil.copytree(target, destination)
        else:
            shutil.copy2(target, destination)
    except OSError as e:
        raise BackupError(
            f"Could not back up {target} before replacing it: {e}. "
            f"Nothing has been changed."
        ) from e

    print(f"  [BACKUP] {target.name} -> {destination.relative_to(target.parent)}  ({reason})")
    return destination


__all__ = ["BACKUP_DIR_NAME", "BackupError", "backup_dir_for", "preserve"]
