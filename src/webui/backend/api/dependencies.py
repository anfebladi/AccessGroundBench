"""Shared request-handling helpers for the API routers.

Dataset lookup, mode/sample validation and display-path formatting are each
needed by several routers. They lived as closures and private helpers inside
server.create_app(), which meant a router could not be split out without either
duplicating them or reaching back into the app factory.

Everything here raises fastapi.HTTPException with a *string* `detail`. That is
load-bearing: the frontend's ApiError (see frontend/src/lib/api.ts) reads
`detail` and renders it directly, so a non-string detail shows the user an
object.
"""

from __future__ import annotations

from pathlib import Path

import paths

from ..services import registry
from ..services.analysis_tables import ANALYSIS_MODES, analysis_samples


def dataset_or_404(name: str) -> registry.DatasetInfo:
    """Look up one dataset by name, or 404."""
    from fastapi import HTTPException

    info = next((d for d in registry.discover_datasets() if d.name == name), None)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Unknown dataset: {name}")
    return info


def evaluations_root(info: registry.DatasetInfo) -> Path:
    """Return the evaluation outputs owned by one dataset record."""
    return paths.evaluations_dir(info.path)


def baseline_screens(labels_dir: Path) -> list[str]:
    """Return the screen names a dataset has baseline labels for.

    A screen counts as present when it has a baseline label file: the baseline
    profile is the reference every other profile is compared against, so a
    screen without one cannot take part in an evaluation. Shared by the Dataset
    view's screen list and the evaluate preflight's expected-key count, which
    must agree on what "the screens in this dataset" means.
    """
    return sorted(
        p.stem.replace("_baseline", "") for p in labels_dir.glob("*_baseline.json")
    )


def validate_mode(mode: str) -> str:
    """Reject a prompt mode that is not one of the two evaluation arms."""
    from fastapi import HTTPException

    if mode not in ANALYSIS_MODES:
        raise HTTPException(status_code=400, detail=f"Unknown mode: {mode!r}")
    return mode


def validate_analysis_sample(sample: str) -> str:
    """Reject an unknown sample, allowing the UI-only "all"."""
    from fastapi import HTTPException

    if sample not in analysis_samples():
        raise HTTPException(status_code=400, detail=f"Unknown sample: {sample!r}")
    return sample


def validate_named_sample(sample: str) -> str:
    """Reject an unknown sample, and also "all".

    Deliberately stricter than validate_analysis_sample: Compare reports a
    per-model statistic computed over one named exclusion sample, so "do not
    restrict to a sample" is not a meaningful request here.
    """
    from fastapi import HTTPException

    from analysis.data.samples import SAMPLE_NAMES

    if sample not in SAMPLE_NAMES:
        raise HTTPException(status_code=400, detail=f"Unknown sample: {sample!r}")
    return sample


def display_path(path: Path) -> str:
    """Format a path for display in the UI, relative to the project root.

    Falls back to the absolute path when it lies outside the checkout -- a
    dataset directory can be pointed anywhere via AGB_DATASET_DIR.

    Retried against the resolved root because a collection's output root is
    derived from a resolved dataset path, so any symlink between the checkout
    and the filesystem (`/var` -> `/private/var` on macOS) makes the two sides
    disagree on spelling while naming the same directory. Without the retry the
    UI would show an absolute temp-looking path for a dataset that is plainly
    inside the checkout.
    """
    for root in (paths.PROJECT_ROOT, paths.PROJECT_ROOT.resolve()):
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            continue
    return str(path)


__all__ = [
    "baseline_screens",
    "dataset_or_404",
    "display_path",
    "evaluations_root",
    "validate_analysis_sample",
    "validate_mode",
    "validate_named_sample",
]
