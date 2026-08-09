"""
device.py
------------
Shared ADB helpers for AccessGroundBench scripts.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


def resolve_adb(verbose: bool = False) -> str:
    """
    Resolve adb from the standard Android SDK location, falling back to PATH.
    """
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    sdk_adb = Path(local_app_data) / "Android" / "Sdk" / "platform-tools" / "adb.exe"

    if sdk_adb.is_file():
        if verbose:
            print(f"[PATH]  ADB found: {sdk_adb}")
        return str(sdk_adb)

    if verbose:
        print("[PATH]  SDK path not found under LOCALAPPDATA - falling back to 'adb' on PATH.")
    return "adb"


def get_device_serial(adb: str) -> str:
    """
    Return the first authorized ADB device serial, or exit on failure.
    """
    result = subprocess.run(
        [adb, "devices"],
        capture_output=True,
        text=True,
        check=True,
    )

    lines = result.stdout.strip().splitlines()[1:]
    for line in lines:
        parts = line.split()
        if len(parts) < 2:
            continue

        serial, status = parts[0], parts[1]
        if status == "device":
            return serial
        if status in ("unauthorized", "offline"):
            print(f"[ERROR] Device '{serial}' is {status}. Check USB debugging / emulator state.")
            sys.exit(1)

    print("[ERROR] No authorized device found. Start the emulator and retry.")
    sys.exit(1)


def run_adb(adb: str, serial: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run an ADB command for a specific device with check=True."""
    return subprocess.run(
        [adb, "-s", serial, *args],
        capture_output=True,
        text=True,
        check=True,
    )


def run_adb_with_retries(
    adb: str,
    serial: str,
    *args: str,
    retries: int = 2,
    delay: float = 1.0,
) -> subprocess.CompletedProcess[str]:
    """
    Run an ADB command, retrying on failure.

    Transient `adb pull`/`screencap` failures (empty stderr, flaky transfers)
    otherwise abort a whole collection run. Retries `retries` times with a
    `delay`-second pause between attempts before re-raising the last error.
    """
    last_exc: subprocess.CalledProcessError | None = None
    for attempt in range(retries + 1):
        try:
            return run_adb(adb, serial, *args)
        except subprocess.CalledProcessError as exc:
            last_exc = exc
            if attempt < retries:
                print(
                    f"  [RETRY] adb {args[0] if args else '?'} failed "
                    f"(attempt {attempt + 1}/{retries + 1}); retrying in {delay}s..."
                )
                time.sleep(delay)
    assert last_exc is not None
    raise last_exc


def capture_adb(adb: str, serial: str, *args: str) -> str:
    """Run an ADB command and return stdout."""
    return run_adb(adb, serial, *args).stdout


def get_system_bar_heights(adb: str, serial: str) -> tuple[int, int]:
    """
    Query the device for the status bar and navigation bar heights in pixels.

    Parses `dumpsys window displays` output to find the frame rectangles for
    statusBars and navigationBars InsetsSources.
    """
    import re

    result = run_adb(adb, serial, "shell", "dumpsys", "window", "displays")
    stdout = result.stdout
    lines = stdout.splitlines()

    status_height = 0
    nav_height = 0

    for line in lines:
        if "InsetsSource" in line and "type=statusBars" in line:
            m = re.search(r"frame=\[(\d+),(\d+)\]\[(\d+),(\d+)\]", line)
            if m:
                status_height = int(m.group(4)) - int(m.group(2))
        elif "InsetsSource" in line and "type=navigationBars" in line:
            m = re.search(r"frame=\[(\d+),(\d+)\]\[(\d+),(\d+)\]", line)
            if m:
                nav_height = int(m.group(4)) - int(m.group(2))

    if status_height:
        print(f"  [BARS] Status bar: {status_height}px")
    else:
        print("  [BARS] Could not detect status bar height (defaulting to 0)")

    if nav_height:
        print(f"  [BARS] Navigation bar: {nav_height}px")
    else:
        print("  [BARS] Could not detect navigation bar height (defaulting to 0)")

    return status_height, nav_height
