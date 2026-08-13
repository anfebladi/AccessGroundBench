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


# One experiment is a dataset plus everything derived from it, so both live
# under a single root rather than as unrelated top-level directories:
#
#   experiment/dataset/  captures, labels, raw XML, manifest
#   experiment/outputs/  evaluation results and analysis tables
#   experiment/archive/  superseded runs (local only; gitignored)
EXPERIMENT_DIR_NAME = "experiment"


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
    return project_root / EXPERIMENT_DIR_NAME / "dataset"


PROJECT_ROOT = find_project_root()
DATASET_DIR = _resolve_dataset_dir(PROJECT_ROOT)
IMAGES_DIR = DATASET_DIR / "images"
RAW_XML_DIR = DATASET_DIR / "raw_xml"
LABELS_DIR = DATASET_DIR / "labels"
MANIFEST_PATH = DATASET_DIR / "collection_manifest.json"
PROMPT_MODES = ("vision", "tree")


def outputs_dir() -> Path:
    """Return the repository's generated-output root."""
    return PROJECT_ROOT / EXPERIMENT_DIR_NAME / "outputs"


def captures_dir() -> Path:
    """Return the scratch directory for standalone `agb capture` output."""
    return outputs_dir() / "captures"


def dataset_name(dataset_dir: str | Path | None = None) -> str:
    """Return the registry name for *dataset_dir* (default: the active one).

    Matches the names webui.backend.datasets.discover_datasets assigns, so the UI's
    dataset dropdown and the CLI's --data-dir agree on where a run's outputs
    belong: `dataset` for the default, otherwise the directory's own name
    (`experiment_2`, or whatever archived run was pointed at).

    Names are basenames, so two datasets sharing one directory name would share
    an output root. That is why archives keep distinct names
    (`experiment/archive/experiment_2`, not `.../archive/dataset`).
    """
    resolved = Path(dataset_dir or DATASET_DIR).expanduser().resolve()
    default = (PROJECT_ROOT / EXPERIMENT_DIR_NAME / "dataset").resolve()
    return "dataset" if resolved == default else resolved.name


def outputs_root_for(dataset_dir: str | Path | None = None) -> Path:
    """Return the output root owned by one dataset.

    Every generated file -- evaluation results, analysis tables, comparisons --
    lives beneath the root of the dataset it was derived from, and nothing
    writes outside it. Two datasets can therefore never reach the same file:
    evaluating the same model against a second dataset cannot append into (or
    be skipped against) the first dataset's rows, and re-analysing an archive
    cannot overwrite the current run's tables.

    These are functions rather than module constants because the dataset is
    not always known at import time: `agb analyze --data-dir` and the web UI
    both choose one per call, while `agb evaluate` and `agb collect` inherit
    theirs from AGB_DATASET_DIR before import. A constant would freeze
    whichever dataset happened to be active first.
    """
    return outputs_dir() / dataset_name(dataset_dir)


def evaluations_dir(dataset_dir: str | Path | None = None) -> Path:
    """Return one dataset's evaluation-results directory."""
    return outputs_root_for(dataset_dir) / "evaluations"


def analysis_dir(dataset_dir: str | Path | None = None) -> Path:
    """Return one dataset's analysis-output directory."""
    return outputs_root_for(dataset_dir) / "analysis"


def evaluation_results_path(
    model: str, use_a11y_tree: bool = False, dataset_dir: str | Path | None = None
) -> Path:
    """Return the evaluation result file for one model and prompt mode.

    The prompt mode is part of the filename because vision and tree results
    answer different research questions and must never be pooled; naming them
    apart is what lets discover_result_csvs separate the arms.
    """
    from evaluation.config import sanitize_model_filename

    mode = "tree" if use_a11y_tree else "vision"
    return evaluations_dir(dataset_dir) / f"{sanitize_model_filename(model)}_{mode}.csv"


def analysis_output_path(
    mode: str, sample: str, dataset_dir: str | Path | None = None
) -> Path:
    """Return the analysis output directory for one mode/sample of a dataset.

    Mode and sample are in the path because the result tables are named after
    the analysis, not the run: re-analysing with a different --sample or --mode
    would otherwise overwrite the previous tables in place.
    """
    return analysis_dir(dataset_dir) / f"{mode}_{sample}"


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
    "PROMPT_MODES",
    "analysis_dir",
    "captures_dir",
    "outputs_dir",
    "analysis_output_path",
    "dataset_name",
    "evaluation_results_path",
    "evaluations_dir",
    "outputs_root_for",
    "dataset_path",
    "find_project_root",
]
