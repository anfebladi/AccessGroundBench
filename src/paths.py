"""Resolve repository and dataset paths for AccessGroundBench commands."""

from __future__ import annotations

import os
from pathlib import Path

DATASET_DIR_ENV_VAR = "AGB_DATASET_DIR"


def _is_project_root(path: Path) -> bool:
    """Return whether *path* is the AccessGroundBench repository root."""
    pyproject = path / "pyproject.toml"
    if not pyproject.is_file():
        return False
    try:
        contents = pyproject.read_text(encoding="utf-8")
    except OSError:
        return False
    return 'name = "accessgroundbench"' in contents


def _parents_inclusive(path: Path):
    yield path
    yield from path.parents


def find_project_root(start: str | Path | None = None) -> Path:
    """Find the nearest AccessGroundBench repository.

    An explicit *start* is searched first. Otherwise the current working
    directory is preferred, preserving the legacy commands' repository-root
    behavior. The source package location is the fallback used by editable
    installs and imports launched from a repository subdirectory.
    """
    candidates = []
    if start is not None:
        candidates.append(Path(start).expanduser().resolve())
    else:
        candidates.append(Path.cwd().resolve())
    candidates.append(Path(__file__).resolve().parent)

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate.is_file():
            candidate = candidate.parent
        for path in _parents_inclusive(candidate):
            if path in seen:
                continue
            seen.add(path)
            if _is_project_root(path):
                return path

    # A wheel installation does not necessarily include repository metadata.
    # Falling back to the invocation directory keeps relative dataset paths
    # predictable instead of silently targeting site-packages.
    return Path(start).expanduser().resolve() if start is not None else Path.cwd().resolve()


def _resolve_dataset_dir(project_root: Path) -> Path:
    """Return the active dataset directory.

    AGB_DATASET_DIR, when set, overrides the default `<project_root>/dataset`
    so a caller (the web UI, or a --data-dir CLI flag) can point commands at a
    different dataset without the emulator-collection code ever seeing it --
    it reads DATASET_DIR the same way regardless of where the value came
    from. This is only read once, at import time: every downstream module
    that does `from paths import DATASET_DIR` captures the value at its own
    import time, so the override must be set in the environment before this
    module (or anything importing it) is first imported in the process.
    """
    override = os.environ.get(DATASET_DIR_ENV_VAR, "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return project_root / "dataset"


PROJECT_ROOT = find_project_root()
DATASET_DIR = _resolve_dataset_dir(PROJECT_ROOT)
IMAGES_DIR = DATASET_DIR / "images"
RAW_XML_DIR = DATASET_DIR / "raw_xml"
LABELS_DIR = DATASET_DIR / "labels"
MANIFEST_PATH = DATASET_DIR / "collection_manifest.json"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
EVALUATIONS_DIR = OUTPUTS_DIR / "evaluations"
ANALYSIS_DIR = OUTPUTS_DIR / "analysis"


def evaluation_results_path(model: str, use_a11y_tree: bool = False) -> Path:
    """Return the organized evaluation result path for *model*."""
    from evaluation.config import sanitize_model_filename

    mode = "tree" if use_a11y_tree else "vision"
    return EVALUATIONS_DIR / sanitize_model_filename(model) / mode / "results.csv"


def analysis_output_path(mode: str, sample: str) -> Path:
    """Return the organized analysis output directory."""
    return ANALYSIS_DIR / f"{mode}_{sample}"


def dataset_path(*parts: str | Path) -> Path:
    """Return a path beneath the active repository's dataset directory."""
    return DATASET_DIR.joinpath(*parts)


__all__ = [
    "DATASET_DIR",
    "DATASET_DIR_ENV_VAR",
    "IMAGES_DIR",
    "LABELS_DIR",
    "MANIFEST_PATH",
    "PROJECT_ROOT",
    "RAW_XML_DIR",
    "OUTPUTS_DIR",
    "EVALUATIONS_DIR",
    "ANALYSIS_DIR",
    "evaluation_results_path",
    "analysis_output_path",
    "dataset_path",
    "find_project_root",
]
