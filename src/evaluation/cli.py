"""Command-line adapters for evaluation and offline result maintenance."""

import argparse
import os
import sys
from pathlib import Path

# Deliberately NOT `from paths import DATASET_DIR_ENV_VAR`: kept hardcoded so this
# module has no import-time dependency on `paths` at all, which is what lets
# --data-dir be parsed and published to the environment before the domain
# packages are imported. Kept in sync with paths.DATASET_DIR_ENV_VAR by
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
        f"(or set ${_DATASET_DIR_ENV_VAR}; no default)",
    )
    args = parser.parse_args(argv)
    # No default dataset: evaluating one the user never named is how paid API
    # calls end up appended to the wrong run's CSV.
    if args.data_dir is not None:
        os.environ[_DATASET_DIR_ENV_VAR] = str(args.data_dir.expanduser().resolve())
    elif not os.environ.get(_DATASET_DIR_ENV_VAR, "").strip():
        parser.error(
            f"--data-dir is required (or set ${_DATASET_DIR_ENV_VAR}). "
            "There is no default dataset."
        )

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
