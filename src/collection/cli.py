"""Command-line adapters for collection workflows."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Deliberately NOT `from paths import DATASET_DIR_ENV_VAR`: kept hardcoded so
# this module has no import-time dependency on `paths` at all, which is what lets
# --data-dir be parsed and published to the environment before the domain
# packages are imported. Kept in sync with paths.DATASET_DIR_ENV_VAR by
# tests/test_dataset_dir_and_byo_model.py.
_DATASET_DIR_ENV_VAR = "AGB_DATASET_DIR"

from .runtime import profiles
from .screens import SCREENS


def _add_data_dir_argument(parser: argparse.ArgumentParser, help_text: str) -> None:
    parser.add_argument("--data-dir", type=Path, default=None, help=help_text)


def _publish_data_dir(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Put --data-dir in the environment, or fail with usage.

    There is no default dataset: guessing one is how a collection ends up
    overwriting captures nobody named on the command line.
    """
    if args.data_dir is not None:
        os.environ[_DATASET_DIR_ENV_VAR] = str(args.data_dir.expanduser().resolve())
    elif not os.environ.get(_DATASET_DIR_ENV_VAR, "").strip():
        parser.error(
            f"--data-dir is required (or set ${_DATASET_DIR_ENV_VAR}). "
            "There is no default dataset."
        )


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
    _add_data_dir_argument(
        parser,
        f"Directory to capture into (or set ${_DATASET_DIR_ENV_VAR}; no default)",
    )
    args = parser.parse_args(argv)
    _publish_data_dir(parser, args)

    # Imported after the environment is set. The path helpers read it per call,
    # so import order no longer freezes anything -- but keeping the import here
    # means a missing --data-dir fails on usage rather than deep in the workflow.
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
    # A standalone capture writes to the dataset's outputs/captures/ scratch dir,
    # so it needs to know which dataset owns it.
    _add_data_dir_argument(
        parser,
        f"Dataset whose captures/ dir receives the assets (or set "
        f"${_DATASET_DIR_ENV_VAR}; no default)",
    )
    args = parser.parse_args(argv)
    _publish_data_dir(parser, args)

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
