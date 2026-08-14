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


# One run is a dataset plus everything derived from it, so both live under a
# single root, and every run lives under one container:
#
#   collections/<name>/dataset/  captures, labels, raw XML, manifest
#   collections/<name>/outputs/  that run's evaluation results and tables
#
# No run is privileged. The data that ships with the benchmark happens to be
# called `experiment`, but nothing in the code knows that name: discovery scans
# the container and loads whatever is there, naming each run after its folder.
COLLECTIONS_DIR_NAME = "collections"

PROJECT_ROOT = find_project_root()
PROMPT_MODES = ("vision", "tree")


class NoDatasetSpecified(RuntimeError):
    """Raised when an operation needs a dataset and none was given.

    A deliberate error rather than a default. Picking a dataset on the caller's
    behalf is how an evaluation ends up appending to the wrong run's CSV, or a
    collection overwrites captures that were never named on the command line.
    """


def collections_dir() -> Path:
    """Return the container every run lives under."""
    return PROJECT_ROOT / COLLECTIONS_DIR_NAME


def active_dataset_dir() -> Path:
    """Return the active dataset directory. Unset is an error, not a default.

    Read from the environment on *every* call rather than captured once at
    import time. That is what lets `--data-dir` work at all: the CLI adapters
    set AGB_DATASET_DIR before importing the domain packages, and a test or a
    subprocess that sets it later is still seen. The previous import-time
    constants forced every caller to be imported in the right order.

    Named `active_` rather than plain `dataset_dir` because several functions
    here take a `dataset_dir` parameter, which would shadow it.
    """
    override = os.environ.get(DATASET_DIR_ENV_VAR, "").strip()
    if not override:
        raise NoDatasetSpecified(
            "no dataset specified. Pass --data-dir <dir> or set "
            f"{DATASET_DIR_ENV_VAR}."
        )
    return Path(override).expanduser().resolve()


def images_dir() -> Path:
    """Return the active dataset's screenshots."""
    return active_dataset_dir() / "images"


def raw_xml_dir() -> Path:
    """Return the active dataset's raw UI-hierarchy dumps."""
    return active_dataset_dir() / "raw_xml"


def labels_dir() -> Path:
    """Return the active dataset's label JSON."""
    return active_dataset_dir() / "labels"


def manifest_path() -> Path:
    """Return the active dataset's collection manifest."""
    return active_dataset_dir() / "collection_manifest.json"


def captures_dir() -> Path:
    """Return the scratch directory for standalone `agb capture` output."""
    return outputs_root_for(active_dataset_dir()) / "captures"


def outputs_root_for(dataset_dir: str | Path | None = None) -> Path:
    """Return the output root owned by one dataset.

    Every generated file -- evaluation results, analysis tables, comparisons --
    lives beneath the root of the run it was derived from, and nothing writes
    outside it. Two runs can therefore never reach the same file: evaluating the
    same model against a second run cannot append into (or be skipped against)
    the first run's rows, and re-analysing one run cannot overwrite another's
    tables.

    A directory named `dataset` is one half of a run root -- the
    `{dataset,outputs}/` pair under `collections/<name>/` -- so its outputs are
    its *sibling*, not a folder buried inside its own captures. A directory of
    any other shape, such as a bare path passed to --data-dir, owns an
    `outputs/` inside itself so that it stays self-contained.

    An output root is always derived from the dataset's own location, never from
    its basename. Roots used to be keyed on the basename, so two runs with the
    same folder name silently shared one; deriving from the location makes that
    impossible regardless of naming.
    """
    resolved = Path(dataset_dir or active_dataset_dir()).expanduser().resolve()
    if resolved.name == "dataset":
        return resolved.parent / "outputs"
    return resolved / "outputs"


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
    """Return a path beneath the active dataset directory."""
    return active_dataset_dir().joinpath(*parts)


__all__ = [
    "COLLECTIONS_DIR_NAME",
    "DATASET_DIR_ENV_VAR",
    "PROJECT_ROOT",
    "PROMPT_MODES",
    "NoDatasetSpecified",
    "active_dataset_dir",
    "analysis_dir",
    "analysis_output_path",
    "captures_dir",
    "collections_dir",
    "dataset_path",
    "evaluation_results_path",
    "evaluations_dir",
    "find_project_root",
    "images_dir",
    "labels_dir",
    "manifest_path",
    "outputs_root_for",
    "raw_xml_dir",
]
