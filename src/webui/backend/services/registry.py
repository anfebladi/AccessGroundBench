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

from .stdout_capture import capture_stdout

@dataclass
class DatasetInfo:
    name: str
    path: Path
    screen_count: int
    image_count: int
    query_count: int

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": str(self.path),
            "screen_count": self.screen_count,
            "image_count": self.image_count,
            "query_count": self.query_count,
        }


def _is_dataset_dir(path: Path) -> bool:
    return (path / "images").is_dir() and (path / "labels").is_dir()


def _describe(dataset_dir: Path) -> DatasetInfo:
    """Summarise one run, named after the folder that owns its dataset/.

    The name is derived here so "a run is called whatever its directory is
    called" lives in exactly one place.
    """
    from evaluation.config import ALL_PROFILES
    from evaluation.grounding.targets import build_expected_keys

    labels_dir = dataset_dir / "labels"
    images_dir = dataset_dir / "images"
    screen_names = sorted(
        p.stem.replace("_baseline", "") for p in labels_dir.glob("*_baseline.json")
    )
    with capture_stdout():
        query_count = len(build_expected_keys(screen_names, labels_dir, ALL_PROFILES))
    return DatasetInfo(
        name=dataset_dir.parent.name,
        path=dataset_dir,
        screen_count=len(screen_names),
        image_count=len(list(images_dir.glob("*.png"))),
        query_count=query_count,
    )


def discover_datasets() -> list[DatasetInfo]:
    """Enumerate every run under the collections container.

    One uniform scan: every `collections/<name>/dataset/` is a run named
    `<name>`, and no run is privileged. The data that ships with the benchmark
    is simply one of them. There is deliberately no default, no reserved name
    and no special case here -- the previous version had three branches and had
    to skip its own first entry to avoid listing it twice.

    Rooted at paths.PROJECT_ROOT rather than the active dataset so the registry
    reflects what is on disk regardless of what any prior request selected.
    """
    root = paths.collections_dir()
    if not root.is_dir():
        return []
    return [
        _describe(child / "dataset")
        for child in sorted(root.iterdir())
        # A child with no dataset/ (a cancelled collection, a folder made by
        # hand) is skipped rather than offered as an empty dataset.
        if child.is_dir() and _is_dataset_dir(child / "dataset")
    ]


def resolve_dataset_path(name: str) -> Path | None:
    """Return the directory for a dataset name from the registry, or None."""
    for info in discover_datasets():
        if info.name == name:
            return info.path
    return None


__all__ = ["DatasetInfo", "discover_datasets", "resolve_dataset_path"]
