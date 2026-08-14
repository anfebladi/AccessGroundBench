"""Baseline-vs-profile model comparison for the web UI's Compare view.

Reuses the exact same statistical pipeline `analysis.workflow.run_analysis`
uses for the canonical per-dataset tables (`report_per_model`,
`report_reachability`) rather than a separate on-the-fly computation, so a
model's numbers here can never disagree with what `agb analyze` writes to the
dataset's own `analysis/` directory.

The Holm-Bonferroni correction specifically MUST run across the full
model x profile family, not just the requested model's profiles: the same
p-value can survive Holm correction in a smaller family and fail it in the
canonical one, or vice versa. `report_per_model` already corrects across
whatever `indices` it is given, so this always passes it every discovered
model for the dataset and mode, then filters the corrected rows down to the
one requested for display -- the correction itself is never re-scoped.
"""
from __future__ import annotations

import contextlib
import io
from pathlib import Path

from evaluation.config import ALL_PROFILES

from analysis.data.results import (
    discover_result_csvs, index_rows, load_results, model_name_from_path,
    reclassify_label_changed, reclassify_off_frame,
)
from analysis.data.samples import DEFAULT_SAMPLE, compute_b2_targets
from analysis.reports.grounding import report_per_model
from analysis.reports.reachability import report_reachability

EXPERIMENTAL_PROFILES = [p for p in ALL_PROFILES if p != "baseline"]


class CompareError(ValueError):
    """A Compare request could not be satisfied -- callers map this to a 404."""


def compare_model(
    dataset_dir: Path,
    model_id: str,
    mode: str = "vision",
    sample: str = DEFAULT_SAMPLE,
) -> dict:
    """Baseline-vs-each-profile comparison for one model.

    Returns the same Holm-corrected significance, power flag and paired
    difference interval the canonical analysis tables carry, plus
    model-independent reachability per profile. Raises CompareError if the
    mode has no result files for this dataset, or if `model_id` is not
    among the discovered models.
    """
    csv_files = discover_result_csvs(dataset_dir, mode)
    if not csv_files:
        raise CompareError(f"No {mode!r} result files found for this dataset.")

    # report_per_model and its dependencies print a verbose progress table
    # to stdout (the same output `agb analyze` shows in a terminal); the web
    # server has no terminal for it to usefully land in.
    with contextlib.redirect_stdout(io.StringIO()):
        indices = {model_name_from_path(p): index_rows(load_results(p)) for p in csv_files}

        if model_id not in indices:
            raise CompareError(f"No {mode!r} results for model {model_id!r} in this dataset.")

        first_index = next(iter(indices.values()))
        available_profiles = {prof for (_screen, _text, prof) in first_index}
        profiles = [p for p in EXPERIMENTAL_PROFILES if p in available_profiles]

        reclassify_label_changed(list(first_index.values()), dataset_dir / "labels")
        for index in indices.values():
            reclassify_off_frame(list(index.values()), dataset_dir / "images")

        baseline_rows = [row for (_s, _t, prof), row in first_index.items() if prof == "baseline"]
        b2_targets = compute_b2_targets(baseline_rows)

        # Full family: every discovered model x every profile. This is what
        # makes the Holm correction match the canonical analysis exactly --
        # see the module docstring.
        per_model_rows = report_per_model(indices, profiles, sample, b2_targets)
        reachability_rows = report_reachability(
            first_index, profiles, sample=sample, b2_targets=b2_targets
        )

    reach_by_profile = {r["profile"]: r for r in reachability_rows}
    model_rows = [r for r in per_model_rows if r["model"] == model_id]

    profiles_out = []
    for row in model_rows:
        reach = reach_by_profile.get(row["profile"], {})
        if row["power"]:
            state = "underpowered"
        elif row["significant"]:
            state = "significant"
        else:
            state = "no_change"
        profiles_out.append({
            "profile": row["profile"],
            "baseline_accuracy": row["base_acc"],
            "profile_accuracy": row["exp_acc"],
            "delta": row["diff"],
            "delta_low": row["diff_low"],
            "delta_high": row["diff_high"],
            "b": row["b"],
            "c": row["c"],
            "total": row["total"],
            "p_value": row["p_value"],
            "holm_threshold": row["holm_threshold"],
            "significant": row["significant"],
            "power_flag": row["power"],
            "significance_state": state,
            "reachability": reach.get("rate"),
            "reachability_low": reach.get("ci_low"),
            "reachability_high": reach.get("ci_high"),
        })

    return {
        "model": model_id,
        "mode": mode,
        "sample": sample,
        # Every model this dataset/mode's Holm correction was run across --
        # surfaced so the UI can show "corrected across N models" rather
        # than leaving the family size implicit.
        "models_in_family": sorted(indices),
        "profiles": profiles_out,
    }
