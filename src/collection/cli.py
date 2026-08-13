"""Command-line adapters for collection workflows."""

from __future__ import annotations

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

from .runtime import profiles
from .screens import SCREENS


def collect_main(argv: list[str] | None = None) -> None:
    """Run the complete collection workflow."""
    parser = argparse.ArgumentParser(
        description="AccessGroundBench -- Master Data Collection Orchestrator"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate pipeline logic without an emulator (no ADB calls)",
    )
    parser.add_argument(
        "--screens",
        nargs="+",
        default=None,
        help="Override the default screen list (e.g., --screens settings_main dialer)",
    )
    parser.add_argument(
        "--rebuild-manifest",
        action="store_true",
        help="Reconstruct the manifest for --screens (default: all) from "
             "images/raw_xml/labels already on disk. No emulator, no ADB, no "
             "new captures -- use this to recover the manifest after a "
             "subset run overwrote it, or to get a provenance record for a "
             "dataset collected before this flag existed.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Directory to capture into (default: ./experiment/dataset, or "
             "$AGB_DATASET_DIR if set)",
    )
    args = parser.parse_args(argv)
    if args.data_dir is not None:
        # Must land in os.environ before `paths` (and anything importing it,
        # e.g. .workflow) is first imported in this process -- paths.py reads
        # this once at import time. Hence the lazy import below.
        os.environ[_DATASET_DIR_ENV_VAR] = str(args.data_dir.expanduser().resolve())

    from . import workflow

    workflow.run_collection(
        args.screens or SCREENS,
        dry_run=args.dry_run,
        rebuild_manifest=args.rebuild_manifest,
    )


def profile_main(argv: list[str] | None = None) -> None:
    """Apply an accessibility profile or reset all profile vectors."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments in (["-h"], ["--help"]):
        print("Usage:")
        print("  layout_modifier <profile_name>   # apply a profile")
        print("  layout_modifier reset            # factory reset all vectors")
        print("\nAvailable profiles:")
        for name, config in profiles.ELDER_PROFILES.items():
            print(
                f"  {name:<26} font={config['font_scale']}  "
                f"density={config['density']:<6}  rtl={config['rtl']}  "
                f"color={config['daltonizer']}"
            )
        return
    if len(arguments) != 1:
        print("[ERROR] Expected exactly one profile name or 'reset'.")
        raise SystemExit(1)
    profile_name = arguments[0].strip().lower()
    if profile_name == "reset":
        profiles.reset_all()
    else:
        profiles.apply_profile(profile_name)


def capture_main(argv: list[str] | None = None) -> None:
    """Capture one synchronized screenshot and UI hierarchy."""
    parser = argparse.ArgumentParser(description="Capture synchronized Android UI assets")
    parser.add_argument("output_name", nargs="?", default=None)
    args = parser.parse_args(argv)

    from .pipeline import capture

    capture.run_pipeline(output_name=args.output_name)


def extract_main(argv: list[str] | None = None) -> None:
    """Extract normalized labels from one Android UI hierarchy."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        print("Usage: bound_extractor <path_to_xml>")
        raise SystemExit(1)
    parser = argparse.ArgumentParser(description="Extract bounding-box labels from UI XML")
    parser.add_argument("xml_path")
    parser.add_argument("--output", default=None)
    parser.add_argument("--y-offset", type=int, default=0)
    parser.add_argument("--bottom-crop", type=int, default=0)
    args = parser.parse_args(arguments)

    from .artifacts import labels

    labels.run(
        args.xml_path,
        output_path=args.output,
        y_offset=args.y_offset,
        bottom_crop=args.bottom_crop,
    )


main = collect_main
