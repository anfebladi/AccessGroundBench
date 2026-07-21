"""
orchestrator.py
---------------
Master data-collection driver for AccessGroundBench.

Automates the full Phase 1 pipeline:
  For each target screen x each accessibility profile ->
    1. Apply the accessibility profile via layout_modifier
    2. Launch and validate the target app via app_navigator
    3. Capture screenshot + UI hierarchy via screenshot_pipeline
    4. Validate the captured XML belongs to the requested screen
    5. Extract bounding-box labels via bound_extractor
    6. Reset the emulator to baseline

All assets are routed into the deterministic dataset/ directory structure:
  dataset/images/{screen}_{profile}.png
  dataset/raw_xml/{screen}_{profile}.xml
  dataset/labels/{screen}_{profile}.json

Usage:
  python orchestrator.py                  # interactive run (requires emulator)
  python orchestrator.py --dry-run        # validate logic without emulator
"""

import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent
DATASET_DIR = PROJECT_ROOT / "dataset"
IMAGES_DIR = DATASET_DIR / "images"
RAW_XML_DIR = DATASET_DIR / "raw_xml"
LABELS_DIR = DATASET_DIR / "labels"

# ---------------------------------------------------------------------------
# Target screen list -- add screens here as needed
# ---------------------------------------------------------------------------
SCREENS: list[str] = [
    "settings_main",
    "contacts",
    "dialer",
    "messages",
    "clock",
]

# ---------------------------------------------------------------------------
# Imports from sibling scripts (used as libraries)
# ---------------------------------------------------------------------------
import layout_modifier
import app_navigator
import screenshot_pipeline
import bound_extractor


def ensure_dirs() -> None:
    """Create the dataset directory structure if it doesn't exist."""
    for d in (IMAGES_DIR, RAW_XML_DIR, LABELS_DIR):
        d.mkdir(parents=True, exist_ok=True)
        print(f"  [DIR] {d}")


def run_screen(screen_name: str, dry_run: bool = False) -> None:
    """
    Run all accessibility profile captures for a single target screen.

    Steps:
      1. Iterate through every profile in ELDER_PROFILES
      2. Apply profile -> navigate -> capture -> validate -> extract labels
      3. Reset emulator to baseline when all profiles are done
    """
    app_navigator.get_screen_target(screen_name)
    profiles = layout_modifier.ELDER_PROFILES

    for profile_name in profiles:
        stem = f"{screen_name}_{profile_name}"
        print(f"\n{'-' * 60}")
        print(f"  Screen: {screen_name}  |  Profile: {profile_name}")
        print(f"  Stem:   {stem}")
        print(f"{'-' * 60}")

        if dry_run:
            print(f"  [DRY-RUN] Would apply profile: {profile_name}")
            print(f"  [DRY-RUN] Would navigate to screen: {screen_name}")
            print(f"  [DRY-RUN] Would capture -> {IMAGES_DIR / f'{stem}.png'}")
            print(f"  [DRY-RUN] Would dump XML -> {RAW_XML_DIR / f'{stem}.xml'}")
            print(f"  [DRY-RUN] Would validate XML package for: {screen_name}")
            print(f"  [DRY-RUN] Would extract  -> {LABELS_DIR / f'{stem}.json'}")
            continue

        # Step 1: Apply the accessibility profile
        print(f"\n  [1/4] Applying profile: {profile_name}")
        layout_modifier.apply_profile(profile_name)

        # Step 2: Navigate to the requested screen after profile reflow
        print(f"\n  [2/4] Navigating to target screen...")
        app_navigator.navigate_to_screen(screen_name)

        # Step 3: Capture screenshot + UI hierarchy
        # The on-device daltonizer is not captured by screencap, so apply the
        # profile's color-vision transform to the PNG in software instead.
        color_mode = layout_modifier.ELDER_PROFILES[profile_name].get("daltonizer", "off")
        print(f"\n  [3/4] Capturing screen assets...")
        xml_path, png_path, status_bar_h, nav_bar_h = screenshot_pipeline.run_pipeline(
            output_name=stem,
            image_dir=IMAGES_DIR,
            xml_dir=RAW_XML_DIR,
            color_mode=color_mode,
        )
        app_navigator.validate_xml_package(xml_path, screen_name)

        # Step 4: Extract bounding-box labels from the XML
        print(f"\n  [4/4] Extracting bounding-box labels...")
        label_path = LABELS_DIR / f"{stem}.json"
        bound_extractor.run(
            str(xml_path),
            output_path=str(label_path),
            y_offset=status_bar_h,
            bottom_crop=nav_bar_h,
        )

        print(f"\n  [DONE] {stem}")
        print(f"    PNG   -> {png_path}")
        print(f"    XML   -> {xml_path}")
        print(f"    JSON  -> {label_path}")

    # Safety reversion: reset emulator back to baseline after all profiles
    if not dry_run:
        print(f"\n  [RESET] Reverting emulator to baseline for screen: {screen_name}")
        layout_modifier.reset_all()


def main() -> None:
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
    args = parser.parse_args()

    screens = args.screens or SCREENS
    dry_run = args.dry_run

    print("=" * 60)
    print("  AccessGroundBench -- Orchestrator")
    print(f"  Mode    : {'DRY-RUN' if dry_run else 'LIVE'}")
    print(f"  Screens : {', '.join(screens)}")
    print(f"  Profiles: {', '.join(layout_modifier.ELDER_PROFILES.keys())}")
    print("=" * 60)

    # Ensure dataset directories exist
    ensure_dirs()

    for screen_name in screens:
        run_screen(screen_name, dry_run=dry_run)

    print("\n" + "=" * 60)
    total = len(screens) * len(layout_modifier.ELDER_PROFILES)
    print(f"  Orchestrator complete!")
    print(f"  Total captures: {total} ({len(screens)} screens x "
          f"{len(layout_modifier.ELDER_PROFILES)} profiles)")
    print(f"  Dataset dir:    {DATASET_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
