"""Command-line adapters for evaluation and offline result maintenance."""

import argparse
import os
import sys
from pathlib import Path

# Deliberately NOT `from paths import DATASET_DIR_ENV_VAR`: importing the
# `paths` module at all runs its top-level DATASET_DIR computation
# immediately, before --data-dir has been parsed below -- which would freeze
# DATASET_DIR to the default and silently ignore the override for the rest
# of the process. Kept in sync with paths.DATASET_DIR_ENV_VAR by
# tests/test_dataset_dir_and_byo_model.py.
_DATASET_DIR_ENV_VAR = "AGB_DATASET_DIR"


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
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Directory holding images/ and labels/ "
        "(default: ./experiment/dataset, or $AGB_DATASET_DIR if set)",
    )
    args = parser.parse_args(argv)
    if args.data_dir is not None:
        # Must land in os.environ before `paths` (and anything importing it,
        # e.g. .workflow) is first imported in this process -- paths.py reads
        # this once at import time. Hence the lazy import below.
        os.environ[_DATASET_DIR_ENV_VAR] = str(args.data_dir.expanduser().resolve())

    from .workflow import evaluate

    evaluate(fresh=args.fresh, force_unlock=args.force_unlock)


def canonicalize_main(argv: list[str] | None = None) -> None:
    """Canonicalize one or more evaluation result files."""
    from .storage.maintenance import canonicalize_main as _canonicalize_main

    _canonicalize_main(argv)


def rescore_main(argv: list[str] | None = None) -> None:
    """Re-score stored coordinates under another coordinate convention."""
    from .storage.maintenance import rescore_main as _rescore_main

    _rescore_main(argv)


__all__ = ["evaluate_main", "canonicalize_main", "rescore_main"]
