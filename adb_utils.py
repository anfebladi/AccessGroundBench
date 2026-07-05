"""
adb_utils.py
------------
Shared ADB helpers for AccessGroundBench scripts.
"""

from __future__ import annotations

import os
import subprocess
import sys
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


def capture_adb(adb: str, serial: str, *args: str) -> str:
    """Run an ADB command and return stdout."""
    return run_adb(adb, serial, *args).stdout
