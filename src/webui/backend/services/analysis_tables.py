"""Analysis output locations and the four analysis-workflow result tables.

Shared by the GET (read whatever already exists) and POST (run, then read
what was just written) analysis endpoints, so both return identically shaped
responses and the Analyze view's rendering code never needs to know which one
produced its data.
"""

from __future__ import annotations

import csv
from pathlib import Path

import paths

# Dataset, mode, and sample are all part of an analysis output path.
#
# The dataset, because `agb analyze` names its outputs after the analysis
# rather than the run: without it, re-analysing an archive from the browser
# would overwrite the current run's reachability/pooled/McNemar/sign tables.
# From a terminal that would at least be a deliberate act; from the browser it
# is one click on the page you land on. Archived datasets in particular must
# never be written to, and their outputs must never displace anyone else's.
# Mode and sample, because a vision run and a tree run answer different
# research questions and must never be mistaken for one another, and because
# two samples would otherwise overwrite each other.
ANALYSIS_MODES = ("vision", "tree")

ANALYSIS_TABLE_FILES = {
    "reachability": "reachability_results.csv",
    "pooled_permutation": "pooled_permutation_results.csv",
    "mcnemar_per_model": "mcnemar_results_per_model.csv",
    "direction_consistency": "direction_consistency.csv",
}


def analysis_samples() -> tuple[str, ...]:
    """The sample names the analysis endpoints accept.

    Derived from analysis.data.samples rather than restated, so adding a
    sample there cannot leave the UI silently rejecting it. "all" is the
    UI-only extra: it means "do not restrict to one named sample" and has no
    entry in SAMPLES.

    Imported lazily to keep importing this module cheap -- analysis.data pulls
    in the evaluation layer transitively.
    """
    from analysis.data.samples import SAMPLE_NAMES

    return ("all", *SAMPLE_NAMES)


def analysis_output_dir(dataset_dir: Path, mode: str, sample: str) -> Path:
    """Return the analysis output directory for one dataset/mode/sample.

    Callers must validate mode and sample first (see dependencies.validate_mode
    / validate_analysis_sample); dataset_dir comes from the dataset registry, so
    all three components are known-good directory names rather than free text.
    """
    return paths.analysis_output_path(mode, sample, dataset_dir)


def read_analysis_tables(output_dir: Path) -> dict[str, list[dict]]:
    """Read the four analysis-workflow CSVs from one output directory.

    A table whose file does not exist reads as an empty list rather than being
    absent, so the response shape is the same whether or not a run has happened.
    """
    tables: dict[str, list[dict]] = {}
    for key, filename in ANALYSIS_TABLE_FILES.items():
        path = output_dir / filename
        if not path.is_file():
            tables[key] = []
            continue
        with open(path, newline="", encoding="utf-8") as f:
            tables[key] = list(csv.DictReader(f))
    return tables


__all__ = [
    "ANALYSIS_MODES",
    "ANALYSIS_TABLE_FILES",
    "analysis_output_dir",
    "analysis_samples",
    "read_analysis_tables",
]
