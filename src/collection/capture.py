"""
capture.py
----------------------
Automated data-collection pipeline for capturing synchronized visual (.png)
and structural (.xml) interface data from an Android emulator via ADB.

Pipeline Phases:
  [1. Verification] -> [2. Device Capture] -> [3. Data Transfer] -> [4. Cleanup]
"""

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from paths import PROJECT_ROOT

from .imaging import COLOR_TRANSFORMS, apply_color_transform, crop_screenshot

from .device import (
    get_device_serial,
    get_system_bar_heights,
    resolve_adb,
    run_adb,
    run_adb_with_retries,
)


# Remote paths on the emulator's sdcard (temporary staging area)
REMOTE_XML = "/sdcard/ui_layout.xml"
REMOTE_PNG = "/sdcard/ui_screen.png"

# Output directory: outputs/ subfolder inside the project root
OUTPUT_DIR = PROJECT_ROOT / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Phase 1: Environment & Device Verification
# ---------------------------------------------------------------------------

def verify_device(adb: str) -> str:
    """
    Run `adb devices` and parse the output to confirm exactly one device is
    available and authorized.

    Returns the device serial string on success.
    Raises SystemExit if no device is found, or the device is offline/unauthorized.
    """
    print("\n[PHASE 1] Verifying ADB device connection...")

    serial = get_device_serial(adb)
    print(f"[OK]     Device ready: {serial}")
    return serial



def capture_on_device(adb: str, serial: str) -> None:
    """
    Dump the UI layout tree and then capture the screen on the device.

    XML dump happens BEFORE the screenshot so that any transient UI elements
    (cursors, indicators) are locked in the same state for both assets.
    """
    print("\n[PHASE 2] Capturing UI layout and screenshot on device...")

    # 2a — Structural snapshot (XML) first
    print("  [2a] Dumping UI layout tree -> /sdcard/ui_layout.xml")
    for attempt in range(3):
        try:
            res = subprocess.run(
                [adb, "-s", serial, "shell", "uiautomator", "dump", REMOTE_XML],
                capture_output=True,
                text=True,
                timeout=15,  # never hang more than 15s on a frozen popup
            )
            out = res.stdout + res.stderr
            if "dumped" in out and "ERROR" not in out:
                break
        except subprocess.TimeoutExpired:
            out = ""
            print(f"  [WARN] uiautomator dump timed out (attempt {attempt+1}/3). Retrying in 2s...")
            time.sleep(2)
            continue
        print(f"  [WARN] uiautomator dump failed (attempt {attempt+1}/3). Retrying in 2s...")
        time.sleep(2)
    else:
        raise RuntimeError(f"uiautomator dump failed completely. Output: {out}")
    print("  [OK]  UI layout dump complete.")

    # 2b — Visual snapshot (PNG) immediately after
    print("  [2b] Capturing screen -> /sdcard/ui_screen.png")
    run_adb_with_retries(adb, serial, "shell", "screencap", "-p", REMOTE_PNG)
    print("  [OK]  Screenshot capture complete.")



def pull_files(
    adb: str,
    serial: str,
    output_name: str,
    image_dir: Path | None = None,
    xml_dir: Path | None = None,
) -> tuple[Path, Path]:
    """
    Pull the captured XML and PNG from the emulator sdcard to local disk.

    Args:
        image_dir: Directory to save the .png into. Defaults to OUTPUT_DIR.
        xml_dir:   Directory to save the .xml into. Defaults to OUTPUT_DIR.

    Returns the local (xml_path, png_path) as Path objects.
    """
    png_dir = image_dir or OUTPUT_DIR
    xdir = xml_dir or OUTPUT_DIR
    png_dir.mkdir(parents=True, exist_ok=True)
    xdir.mkdir(parents=True, exist_ok=True)

    print(f"\n[PHASE 3] Transferring files to local disk (stem='{output_name}')...")

    local_xml = xdir / f"{output_name}.xml"
    local_png = png_dir / f"{output_name}.png"

    # Pull XML
    print(f"  [3a] Pulling {REMOTE_XML} -> {local_xml}")
    run_adb_with_retries(adb, serial, "pull", REMOTE_XML, str(local_xml))
    print("  [OK]  XML transferred.")

    # Pull PNG
    print(f"  [3b] Pulling {REMOTE_PNG} -> {local_png}")
    run_adb_with_retries(adb, serial, "pull", REMOTE_PNG, str(local_png))
    print("  [OK]  PNG transferred.")

    return local_xml, local_png


def cleanup_device(adb: str, serial: str) -> None:
    """
    Remove temporary files from the emulator sdcard so stale data cannot
    bleed into subsequent pipeline runs after a crash or partial execution.
    """
    print("\n[PHASE 4] Cleaning up temporary files on device...")

    for remote_path in (REMOTE_XML, REMOTE_PNG):
        run_adb(adb, serial, "shell", "rm", "-f", remote_path)
        print(f"  [OK]  Deleted {remote_path}")



def run_pipeline(
    output_name: str | None = None,
    image_dir: Path | None = None,
    xml_dir: Path | None = None,
    color_mode: str | None = None,
) -> tuple[Path, Path, int, int]:
    """
    Execute the full four-phase capture pipeline.

    Args:
        output_name: File stem for saved assets. Defaults to a UTC timestamp
                     (e.g. 'capture_20260702_184055') for automatic uniqueness.
        image_dir:   Directory to save the .png into. Defaults to OUTPUT_DIR.
        xml_dir:     Directory to save the .xml into. Defaults to OUTPUT_DIR.
        color_mode:  Optional color-vision transform to apply to the captured
                     PNG (e.g. "deuteranomaly"). "off"/None leaves colors
                     unchanged. See COLOR_TRANSFORMS.

    Returns:
        (xml_path, png_path, status_bar_h, nav_bar_h) — local paths of the
        saved files plus the pixel heights of the cropped system bars.
    """
    if output_name is None:
        output_name = "capture_" + datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    save_info = image_dir or OUTPUT_DIR
    print("=" * 60)
    print("  AccessGroundBench — Screenshot Pipeline")
    print(f"  Output stem : {output_name}")
    print(f"  Save dir    : {save_info}")
    print("=" * 60)

    # Resolve ADB binary
    adb = resolve_adb(verbose=True)

    # Initialise return variables so they're always defined
    local_xml: Path
    local_png: Path
    status_bar_h: int = 0
    nav_bar_h: int = 0

    try:
        # Phase 1 — verify device
        serial = verify_device(adb)

        # Phase 2 — capture on device
        capture_on_device(adb, serial)

        # Query system bar heights for cropping
        status_bar_h, nav_bar_h = get_system_bar_heights(adb, serial)

        # Phase 3 — pull to local disk
        local_xml, local_png = pull_files(
            adb, serial, output_name,
            image_dir=image_dir, xml_dir=xml_dir,
        )

        # Phase 3.5 — crop out status bar and navigation bar
        crop_screenshot(local_png, status_bar_h, nav_bar_h)

        # Phase 3.6 — apply software color-vision transform if requested
        if color_mode and color_mode != "off":
            apply_color_transform(local_png, color_mode)

        # Phase 4 — clean up sdcard
        cleanup_device(adb, serial)

    except subprocess.CalledProcessError as exc:
        print(f"\n[FATAL]  ADB command failed:\n  {exc.cmd}\n  {exc.stderr}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  Pipeline complete!")
    print(f"  XML  -> {local_xml}")
    print(f"  PNG  -> {local_png}")
    print("=" * 60)

    return local_xml, local_png, status_bar_h, nav_bar_h
