"""Statistical analysis for AccessGroundBench."""

from __future__ import annotations


def analyze_main(argv: list[str] | None = None) -> None:
    """Lazily invoke the analysis command without eager CLI imports."""
    from .cli import analyze_main as _analyze_main

    _analyze_main(argv)


__all__ = ["analyze_main"]
