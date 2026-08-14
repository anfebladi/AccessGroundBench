"""Analysis endpoints -- the Analyze view.

Two routes over the same four result tables: GET reads whatever a previous run
(browser or `agb analyze`) already wrote, POST runs the workflow and returns
what it just wrote. Both return the identical shape via read_analysis_tables,
so the Analyze view needs no branch for "loaded fresh" versus "loaded existing".

POST runs the permutation test *in-process and synchronously*, which can block
the request for minutes. That is a deliberate, documented choice (see
docs/ui.md), unlike evaluate/collect which go through the run supervisor.
"""

from __future__ import annotations

import io

from fastapi import APIRouter, HTTPException

from ..services.analysis_tables import analysis_output_dir, read_analysis_tables
from .dependencies import (
    dataset_or_404,
    display_path,
    validate_analysis_sample,
    validate_mode,
)
from .schemas import AnalyzeRequest
from ..services.stdout_capture import capture_stdout

router = APIRouter()


@router.get("/api/datasets/{name}/analysis")
def dataset_analysis(name: str, mode: str = "vision", sample: str = "all") -> dict:
    """Read whatever analysis tables already exist for this mode/sample,
    without running anything.

    This is the direct fix for the Analyze view only ever showing a
    chart after a multi-minute permutation run: `agb analyze` (or a
    previous browser run) may have already written these CSVs, and
    without this endpoint they were unreachable from the UI.
    """
    info = dataset_or_404(name)
    validate_mode(mode)
    validate_analysis_sample(sample)

    output_dir = analysis_output_dir(info.path, mode, sample)
    tables = read_analysis_tables(output_dir)
    available = any(tables.values())
    shown_dir = display_path(output_dir)

    return {"available": available, "output_dir": shown_dir if available else None, **tables}


@router.post("/api/analyze")
def analyze(payload: AnalyzeRequest) -> dict:
    from analysis.reports.reachability import DEFAULT_LABEL_CHANGED_MODE
    from analysis.workflow import run_analysis

    info = dataset_or_404(payload.dataset)
    sample = payload.sample
    mode = payload.mode
    label_changed = (
        DEFAULT_LABEL_CHANGED_MODE if payload.label_changed is None else payload.label_changed
    )

    validate_analysis_sample(sample)
    validate_mode(mode)

    output_dir = analysis_output_dir(info.path, mode, sample)
    output_dir.mkdir(parents=True, exist_ok=True)

    buf = io.StringIO()
    try:
        with capture_stdout(buf):
            run_analysis(
                info.path, None, payload.permutations, payload.seed, mode, sample, label_changed,
                output_dir=output_dir,
            )
    except SystemExit as exc:
        if exc.code not in (0, None):
            raise HTTPException(
                status_code=400,
                detail=f"Analysis failed: {buf.getvalue().strip().splitlines()[-1] if buf.getvalue().strip() else 'see server log'}",
            )

    return {
        "log": buf.getvalue(),
        "output_dir": display_path(output_dir),
        **read_analysis_tables(output_dir),
    }


__all__ = ["router"]
