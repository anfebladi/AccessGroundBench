"""ADB target-screen navigation facade for AccessGroundBench.

Target definitions, foreground inspection, permission handling, and XML
validation live in focused modules. This facade preserves the original public
imports while owning the launch/retry workflow used by the orchestrator.
"""

from __future__ import annotations

import subprocess
import time

from ..device.adb_utils import get_device_serial, resolve_adb, run_adb
from ..device.foreground_state import (
    FOCUS_MARKERS,
    FOREGROUND_PATTERNS,
    get_foreground_package,
    parse_foreground_package,
)
from .navigation_targets import (
    SCREEN_TARGETS,
    ScreenTarget,
    UnknownScreenError,
    default_screen_names,
    get_screen_target,
)
from ..device.permission_dialog import (
    ALLOW_RESOURCE_IDS,
    ALLOW_TEXTS,
    DENY_TEXTS,
    PERMISSION_CONTROLLER_PACKAGES,
    PERMISSION_XML_REMOTE,
    SETTLE_DELAY,
    TapTarget,
    dump_permission_dialog_xml,
    handle_permission_dialog,
    is_permission_controller,
    parse_bounds,
    select_permission_allow_target,
)
from .xml_validation import read_xml_packages, validate_xml_package


MAX_PERMISSION_ATTEMPTS: int = 3


class NavigationError(RuntimeError):
    """Raised when a registered target cannot be brought to the foreground."""


def is_expected_package(package_name: str | None, target: ScreenTarget) -> bool:
    return package_name in target.expected_packages


def navigate_to_screen(screen_name: str) -> None:
    """Launch a target app/screen and validate that it became foreground."""
    target = get_screen_target(screen_name)
    adb = resolve_adb()
    serial = get_device_serial(adb)

    print("\n[NAV] Launching target screen")
    print(f"  Screen: {screen_name}")
    print(f"  Expect: {', '.join(sorted(target.expected_packages))}")

    last_error = ""
    last_foreground = None

    for command in target.launch_commands:
        print(f"  [TRY] adb -s {serial} {' '.join(command)}")
        try:
            run_adb(adb, serial, *command)
        except subprocess.CalledProcessError as exc:
            last_error = exc.stderr.strip() or exc.stdout.strip() or str(exc)
            print(f"  [WARN] Launch command failed: {last_error}")
            continue

        for permission_attempt in range(MAX_PERMISSION_ATTEMPTS + 1):
            time.sleep(SETTLE_DELAY)
            last_foreground = get_foreground_package(adb, serial)
            print(f"  [FOREGROUND] {last_foreground or 'unknown'}")
            if is_expected_package(last_foreground, target):
                print("  [OK] Target screen is foreground.")
                return

            if not is_permission_controller(last_foreground):
                break

            if permission_attempt >= MAX_PERMISSION_ATTEMPTS:
                print("  [WARN] Permission dialog retry limit reached.")
                break

            if not handle_permission_dialog(adb, serial):
                break

            print("  [RETRY] Relaunching target after permission grant.")
            try:
                run_adb(adb, serial, *command)
            except subprocess.CalledProcessError as exc:
                last_error = exc.stderr.strip() or exc.stdout.strip() or str(exc)
                print(f"  [WARN] Relaunch command failed: {last_error}")
                break

    expected = ", ".join(sorted(target.expected_packages))
    actual = last_foreground or "unknown"
    print(f"[ERROR] Failed to navigate to '{screen_name}'.")
    print(f"        Expected foreground package: {expected}")
    print(f"        Actual foreground package:   {actual}")
    if last_error:
        print(f"        Last launch error: {last_error}")
    raise NavigationError(
        f"Failed to navigate to '{screen_name}' "
        f"(expected {expected}; actual {actual})"
    )


__all__ = [
    "ALLOW_RESOURCE_IDS",
    "ALLOW_TEXTS",
    "DENY_TEXTS",
    "FOCUS_MARKERS",
    "FOREGROUND_PATTERNS",
    "MAX_PERMISSION_ATTEMPTS",
    "NavigationError",
    "PERMISSION_CONTROLLER_PACKAGES",
    "PERMISSION_XML_REMOTE",
    "SCREEN_TARGETS",
    "SETTLE_DELAY",
    "ScreenTarget",
    "TapTarget",
    "UnknownScreenError",
    "default_screen_names",
    "dump_permission_dialog_xml",
    "get_foreground_package",
    "get_screen_target",
    "handle_permission_dialog",
    "is_expected_package",
    "is_permission_controller",
    "navigate_to_screen",
    "parse_bounds",
    "parse_foreground_package",
    "read_xml_packages",
    "select_permission_allow_target",
    "validate_xml_package",
]
