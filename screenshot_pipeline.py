"""
screenshot_pipeline.py
----------------------
Automated data-collection pipeline for capturing synchronized visual (.png)
and structural (.xml) interface data from an Android emulator via ADB.

Pipeline Phases:
  [1. Verification] -> [2. Device Capture] -> [3. Data Transfer] -> [4. Cleanup]
"""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path



# Remote paths on the emulator's sdcard (temporary staging area)
REMOTE_XML = "/sdcard/ui_layout.xml"
REMOTE_PNG = "/sdcard/ui_screen.png"

# Output directory: data/ subfolder inside the project root
OUTPUT_DIR = Path(__file__).parent / "data"
OUTPUT_DIR.mkdir(exist_ok=True)


def resolve_adb() -> str:
    """
    Dynamically resolve the adb binary path from the Android SDK installed
    under %LOCALAPPDATA%, ensuring cross-machine compatibility.

    Returns the absolute path string to adb.exe, or falls back to bare 'adb'
    if the SDK cannot be located (relies on PATH then).
    """
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    sdk_adb = Path(local_app_data) / "Android" / "Sdk" / "platform-tools" / "adb.exe"

    if sdk_adb.is_file():
        print(f"[PATH]  ADB found: {sdk_adb}")
        return str(sdk_adb)

    # Fallback: hope adb is on the system PATH
    print("[PATH]  SDK path not found under LOCALAPPDATA — falling back to 'adb' on PATH.")
    return "adb"


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

    result = subprocess.run(
        [adb, "devices"],
        capture_output=True,
        text=True,
        check=True,
    )

    lines = result.stdout.strip().splitlines()
    # First line is always "List of devices attached"
    device_lines = [l for l in lines[1:] if l.strip()]

    if not device_lines:
        print("[ERROR]  No devices found. Start the emulator and re-run.")
        sys.exit(1)

    devices = []
    for line in device_lines:
        parts = line.split()
        serial, status = parts[0], parts[1]
        if status == "device":
            devices.append(serial)
        elif status in ("unauthorized", "offline"):
            print(f"[ERROR]  Device '{serial}' is {status}. "
                  "Check USB debugging / emulator state.")
            sys.exit(1)

    if not devices:
        print("[ERROR]  No authorized device available.")
        sys.exit(1)

    serial = devices[0]
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
    subprocess.run(
        [adb, "-s", serial, "shell", "uiautomator", "dump", REMOTE_XML],
        check=True,
        capture_output=True,
        text=True,
    )
    print("  [OK]  UI layout dump complete.")

    # 2b — Visual snapshot (PNG) immediately after
    print("  [2b] Capturing screen -> /sdcard/ui_screen.png")
    subprocess.run(
        [adb, "-s", serial, "shell", "screencap", "-p", REMOTE_PNG],
        check=True,
        capture_output=True,
        text=True,
    )
    print("  [OK]  Screenshot capture complete.")



def pull_files(adb: str, serial: str, output_name: str) -> tuple[Path, Path]:
    """
    Pull the captured XML and PNG from the emulator sdcard to the local
    project output directory using the provided output_name stem.

    Returns the local (xml_path, png_path) as Path objects.
    """
    print(f"\n[PHASE 3] Transferring files to local disk (stem='{output_name}')...")

    local_xml = OUTPUT_DIR / f"{output_name}.xml"
    local_png = OUTPUT_DIR / f"{output_name}.png"

    # Pull XML
    print(f"  [3a] Pulling {REMOTE_XML} -> {local_xml}")
    subprocess.run(
        [adb, "-s", serial, "pull", REMOTE_XML, str(local_xml)],
        check=True,
        capture_output=True,
        text=True,
    )
    print("  [OK]  XML transferred.")

    # Pull PNG
    print(f"  [3b] Pulling {REMOTE_PNG} -> {local_png}")
    subprocess.run(
        [adb, "-s", serial, "pull", REMOTE_PNG, str(local_png)],
        check=True,
        capture_output=True,
        text=True,
    )
    print("  [OK]  PNG transferred.")

    return local_xml, local_png



def cleanup_device(adb: str, serial: str) -> None:
    """
    Remove temporary files from the emulator sdcard so stale data cannot
    bleed into subsequent pipeline runs after a crash or partial execution.
    """
    print("\n[PHASE 4] Cleaning up temporary files on device...")

    for remote_path in (REMOTE_XML, REMOTE_PNG):
        subprocess.run(
            [adb, "-s", serial, "shell", "rm", "-f", remote_path],
            check=True,
            capture_output=True,
            text=True,
        )
        print(f"  [OK]  Deleted {remote_path}")



def run_pipeline(output_name: str | None = None) -> None:
    """
    Execute the full four-phase capture pipeline.

    Args:
        output_name: File stem for saved assets. Defaults to a UTC timestamp
                     (e.g. 'capture_20260702_184055') for automatic uniqueness.
    """
    if output_name is None:
        output_name = "capture_" + datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    print("=" * 60)
    print("  AccessGroundBench — Screenshot Pipeline")
    print(f"  Output stem : {output_name}")
    print(f"  Save dir    : {OUTPUT_DIR}")
    print("=" * 60)

    # Resolve ADB binary
    adb = resolve_adb()

    try:
        # Phase 1 — verify device
        serial = verify_device(adb)

        # Phase 2 — capture on device
        capture_on_device(adb, serial)

        # Phase 3 — pull to local disk
        local_xml, local_png = pull_files(adb, serial, output_name)

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


if __name__ == "__main__":
    # Optional: pass a custom output name as the first CLI argument
    # Usage: python screenshot_pipeline.py [output_name]
    name_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run_pipeline(output_name=name_arg)
