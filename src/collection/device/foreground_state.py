"""Android foreground-package parsing and inspection helpers."""

from __future__ import annotations

import re
import subprocess

from .adb_utils import capture_adb


FOREGROUND_PATTERNS = (
    re.compile(r"\bu\d+\s+([A-Za-z0-9_.]+)/[A-Za-z0-9_.$]+"),
    re.compile(r"\b([A-Za-z0-9_.]+)/[A-Za-z0-9_.$]+\b"),
    re.compile(r"\bpackageName=([A-Za-z0-9_.]+)\b"),
)

FOCUS_MARKERS = (
    "mCurrentFocus",
    "mFocusedApp",
    "topResumedActivity",
    "ResumedActivity",
    "mResumedActivity",
)


def parse_foreground_package(dumpsys_output: str) -> str | None:
    """Extract the foreground package from common dumpsys output formats."""
    focus_lines = [
        line for line in dumpsys_output.splitlines()
        if any(marker in line for marker in FOCUS_MARKERS)
    ]

    for source in (*focus_lines, dumpsys_output):
        for pattern in FOREGROUND_PATTERNS:
            match = pattern.search(source)
            if match:
                package_name = match.group(1)
                if "." in package_name:
                    return package_name
    return None


def get_foreground_package(adb: str, serial: str) -> str | None:
    """Read Android focus state and return the active foreground package."""
    dumpsys_commands = (
        ("shell", "dumpsys", "window"),
        ("shell", "dumpsys", "activity", "activities"),
    )

    for command in dumpsys_commands:
        try:
            package_name = parse_foreground_package(capture_adb(adb, serial, *command))
        except subprocess.CalledProcessError:
            continue
        if package_name:
            return package_name
    return None
