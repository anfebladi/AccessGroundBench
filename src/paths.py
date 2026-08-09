"""Resolve repository and dataset paths for AccessGroundBench commands."""

from __future__ import annotations

from pathlib import Path


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


PROJECT_ROOT = find_project_root()
DATASET_DIR = PROJECT_ROOT / "dataset"
IMAGES_DIR = DATASET_DIR / "images"
RAW_XML_DIR = DATASET_DIR / "raw_xml"
LABELS_DIR = DATASET_DIR / "labels"
MANIFEST_PATH = DATASET_DIR / "collection_manifest.json"


def dataset_path(*parts: str | Path) -> Path:
    """Return a path beneath the active repository's dataset directory."""
    return DATASET_DIR.joinpath(*parts)


__all__ = [
    "DATASET_DIR",
    "IMAGES_DIR",
    "LABELS_DIR",
    "MANIFEST_PATH",
    "PROJECT_ROOT",
    "RAW_XML_DIR",
    "dataset_path",
    "find_project_root",
]
