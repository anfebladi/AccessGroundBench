"""Dataset discovery for the web UI's dataset dropdown.

A "dataset" here is any directory with images/ and labels/ subdirectories --
the same portable unit evaluation.workflow.discover_screens and
analysis.workflow.run_analysis already operate on via --data-dir. This module
only enumerates candidates; it never mutates AGB_DATASET_DIR itself (that
would be global process state shared by every request) -- each API call and
each subprocess run receives its target dataset's path explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import paths

# dataset/experiment_1 and dataset/experiment_2 are archived research runs
# (see CLAUDE.md and repo memory: "never write to dataset/experiment_N/").
# They are valid datasets structurally, but must never be offered as a
# target for a new evaluation or collection run.
ARCHIVED_NAMES = {"experiment_1", "experiment_2"}


@dataclass
class DatasetInfo:
    name: str
    path: Path
    is_default: bool
    is_archived: bool
    screen_count: int
    image_count: int

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": str(self.path),
            "is_default": self.is_default,
            "is_archived": self.is_archived,
            "screen_count": self.screen_count,
            "image_count": self.image_count,
        }


def _is_dataset_dir(path: Path) -> bool:
    return (path / "images").is_dir() and (path / "labels").is_dir()


def _describe(path: Path, name: str, *, is_default: bool, is_archived: bool) -> DatasetInfo:
    labels_dir = path / "labels"
    images_dir = path / "images"
    screen_count = len(list(labels_dir.glob("*_baseline.json")))
    image_count = len(list(images_dir.glob("*.png")))
    return DatasetInfo(
        name=name, path=path, is_default=is_default, is_archived=is_archived,
        screen_count=screen_count, image_count=image_count,
    )


def discover_datasets() -> list[DatasetInfo]:
    """Enumerate every dataset directory under the repository root.

    Always relative to paths.PROJECT_ROOT (not paths.DATASET_DIR, which may
    already be overridden by AGB_DATASET_DIR in this process) so the registry
    reflects everything on disk regardless of what a prior request selected.
    """
    root = paths.PROJECT_ROOT
    found: list[DatasetInfo] = []

    default_dir = root / "dataset"
    if _is_dataset_dir(default_dir):
        found.append(_describe(default_dir, "dataset", is_default=True, is_archived=False))
        for child in sorted(default_dir.iterdir()):
            if child.is_dir() and child.name in ARCHIVED_NAMES and _is_dataset_dir(child):
                found.append(_describe(child, child.name, is_default=False, is_archived=True))

    datasets_dir = root / "datasets"
    if datasets_dir.is_dir():
        for child in sorted(datasets_dir.iterdir()):
            if child.is_dir() and _is_dataset_dir(child):
                found.append(_describe(child, child.name, is_default=False, is_archived=False))

    return found


def resolve_dataset_path(name: str) -> Path | None:
    """Return the directory for a dataset name from the registry, or None."""
    for info in discover_datasets():
        if info.name == name:
            return info.path
    return None


__all__ = ["ARCHIVED_NAMES", "DatasetInfo", "discover_datasets", "resolve_dataset_path"]
