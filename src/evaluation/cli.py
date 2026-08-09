"""Command-line adapters for evaluation and offline result maintenance."""

import argparse
import sys

from .storage.maintenance import canonicalize_main as _canonicalize_main
from .storage.maintenance import rescore_main as _rescore_main
from .workflow import evaluate


def evaluate_main(argv: list[str] | None = None) -> None:
    """Run the VLM grounding evaluation command."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="AccessGroundBench -- VLM grounding evaluator"
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Discard existing result rows and restart from scratch "
        "(default resumes an interrupted run)",
    )
    parser.add_argument(
        "--force-unlock",
        action="store_true",
        help="Remove a stale .lock file left by a killed run before starting",
    )
    args = parser.parse_args(argv)
    evaluate(fresh=args.fresh, force_unlock=args.force_unlock)


def canonicalize_main(argv: list[str] | None = None) -> None:
    """Canonicalize one or more evaluation result files."""
    _canonicalize_main(argv)


def rescore_main(argv: list[str] | None = None) -> None:
    """Re-score stored coordinates under another coordinate convention."""
    _rescore_main(argv)


__all__ = ["evaluate_main", "canonicalize_main", "rescore_main"]
