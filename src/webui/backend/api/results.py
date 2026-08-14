"""Evaluation result endpoints -- the Results and Compare views.

Route declaration order matters in this module: `/results/compare` is declared
before `/results/{filename}/rows` so the literal segment is matched before the
path parameter can swallow it.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..services.analysis_tables import ANALYSIS_MODES
from .dependencies import (
    dataset_or_404,
    evaluations_root,
    validate_mode,
    validate_named_sample,
)
from ..services.stdout_capture import capture_stdout

router = APIRouter()


@router.get("/api/datasets/{name}/results")
def dataset_results(name: str) -> list[dict]:
    from collections import Counter

    from analysis.data.results import (
        discover_result_csvs, load_results, model_name_from_path,
    )

    info = dataset_or_404(name)
    out = []
    # Both arms, listed separately: discovery deliberately refuses to
    # return them together so no caller can pool them by accident.
    for mode in ANALYSIS_MODES:
        for csv_path in discover_result_csvs(info.path, mode):
            with capture_stdout():
                rows = load_results(csv_path)
            statuses = Counter(r["status"] for r in rows)
            co_present = [r for r in rows if r["status"] == "co_present"]
            hits = sum(1 for r in co_present if r.get("score") == "1")
            # Restricted to the baseline profile only -- a plain
            # proportion, not an inferential statistic, so computing it
            # here rather than in analysis.stats carries no drift risk
            # the way McNemar/Holm would (see backend.services.compare's docstring).
            # Lets Results show whether a model's blended accuracy is
            # hiding degradation under altered profiles at a glance.
            baseline_rows = [r for r in co_present if r.get("profile") == "baseline"]
            baseline_hits = sum(1 for r in baseline_rows if r.get("score") == "1")
            out.append({
                "filename": csv_path.name,
                "model": model_name_from_path(csv_path),
                "prompt_mode": rows[0]["prompt_mode"] if rows else "",
                "row_count": len(rows),
                "statuses": dict(statuses),
                "co_present_count": len(co_present),
                "hits": hits,
                "accuracy": (hits / len(co_present)) if co_present else None,
                "baseline_accuracy": (baseline_hits / len(baseline_rows)) if baseline_rows else None,
            })
    return out


@router.get("/api/datasets/{name}/results/compare")
def dataset_compare(
    name: str, model: str, mode: str = "vision", sample: str = "primary"
) -> dict:
    """Baseline-vs-profile comparison for one model -- the Compare view.

    Takes a model id and searches the dataset's own result files for it,
    rather than a single filename: the Holm-Bonferroni correction has to
    run across every model discovered for this dataset/mode (see
    backend.services.compare's module docstring), which needs all of them loaded
    regardless of which one is being displayed.
    """
    from ..services.compare import CompareError, compare_model

    info = dataset_or_404(name)
    validate_mode(mode)
    validate_named_sample(sample)
    try:
        return compare_model(info.path, model, mode=mode, sample=sample)
    except CompareError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/api/datasets/{name}/results/{filename}/rows")
def dataset_result_rows(name: str, filename: str) -> list[dict]:
    from analysis.data.results import load_results

    info = dataset_or_404(name)
    results_root = evaluations_root(info)
    csv_path = (results_root / filename).resolve()
    # Resolve first, then confirm the result is still inside the dataset's
    # own evaluations directory: `filename` is caller-supplied, and a
    # traversal must not reach another dataset's rows or the wider disk.
    if (results_root.resolve() not in csv_path.parents or
            not csv_path.is_file() or not csv_path.name.endswith(".csv")):
        raise HTTPException(status_code=404, detail=f"No such results file: {filename}")
    with capture_stdout():
        rows = load_results(csv_path)
    # Trim to what the Results-tab miss inspector needs; the full CSV
    # (raw_response, trial_scores, coord_space, ...) stays on disk for
    # anyone who wants it -- no need to duplicate all 18 columns here.
    return [
        {
            "screen": r.get("screen", ""),
            "target_text": r.get("target_text", ""),
            "profile": r.get("profile", ""),
            "status": r.get("status", ""),
            "score": r.get("score", ""),
            "x_pred": r.get("x_pred", ""),
            "y_pred": r.get("y_pred", ""),
            "x_min": r.get("x_min", ""),
            "y_min": r.get("y_min", ""),
            "x_max": r.get("x_max", ""),
            "y_max": r.get("y_max", ""),
            "raw_response": r.get("raw_response", ""),
            "parse_method": r.get("parse_method", ""),
        }
        for r in rows
    ]


__all__ = ["router"]
