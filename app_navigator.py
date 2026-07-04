"""
app_navigator.py
----------------
ADB app navigation helper for AccessGroundBench data collection.

This module owns target-screen launch behavior so orchestrator.py can remain
the main coordinator: profile -> navigate -> capture -> extract.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from adb_utils import capture_adb, get_device_serial, resolve_adb, run_adb


SETTLE_DELAY: float = 2.0
MAX_PERMISSION_ATTEMPTS: int = 3
PERMISSION_XML_REMOTE = "/sdcard/agb_permission_dialog.xml"

PERMISSION_CONTROLLER_PACKAGES = frozenset({
    "com.google.android.permissioncontroller",
    "com.android.permissioncontroller",
})

ALLOW_RESOURCE_IDS = (
    "permission_allow_foreground_only_button",
    "permission_allow_button",
    "permission_allow_one_time_button",
)

ALLOW_TEXTS = (
    "while using the app",
    "allow",
)

DENY_TEXTS = (
    "don't allow",
    "dont allow",
    "deny",
    "not now",
    "cancel",
)


@dataclass(frozen=True)
class ScreenTarget:
    name: str
    launch_commands: tuple[tuple[str, ...], ...]
    expected_packages: frozenset[str]


@dataclass(frozen=True)
class TapTarget:
    x: int
    y: int
    score: int


SCREEN_TARGETS: dict[str, ScreenTarget] = {
    "settings_main": ScreenTarget(
        name="settings_main",
        launch_commands=(
            ("shell", "am", "start", "-a", "android.settings.SETTINGS"),
            ("shell", "monkey", "-p", "com.android.settings", "-c", "android.intent.category.LAUNCHER", "1"),
        ),
        expected_packages=frozenset({"com.android.settings"}),
    ),
    "contacts": ScreenTarget(
        name="contacts",
        launch_commands=(
            ("shell", "am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.APP_CONTACTS"),
            ("shell", "monkey", "-p", "com.google.android.contacts", "-c", "android.intent.category.LAUNCHER", "1"),
            ("shell", "monkey", "-p", "com.android.contacts", "-c", "android.intent.category.LAUNCHER", "1"),
        ),
        expected_packages=frozenset({
            "com.google.android.contacts",
            "com.android.contacts",
        }),
    ),
    "dialer": ScreenTarget(
        name="dialer",
        launch_commands=(
            ("shell", "am", "start", "-a", "android.intent.action.DIAL"),
            ("shell", "monkey", "-p", "com.google.android.dialer", "-c", "android.intent.category.LAUNCHER", "1"),
            ("shell", "monkey", "-p", "com.android.dialer", "-c", "android.intent.category.LAUNCHER", "1"),
        ),
        expected_packages=frozenset({
            "com.google.android.dialer",
            "com.android.dialer",
        }),
    ),
    "messages": ScreenTarget(
        name="messages",
        launch_commands=(
            ("shell", "am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.APP_MESSAGING"),
            ("shell", "monkey", "-p", "com.google.android.apps.messaging", "-c", "android.intent.category.LAUNCHER", "1"),
            ("shell", "monkey", "-p", "com.android.messaging", "-c", "android.intent.category.LAUNCHER", "1"),
        ),
        expected_packages=frozenset({
            "com.google.android.apps.messaging",
            "com.android.messaging",
        }),
    ),
    "clock": ScreenTarget(
        name="clock",
        launch_commands=(
            ("shell", "am", "start", "-a", "android.intent.action.SHOW_ALARMS"),
            ("shell", "monkey", "-p", "com.google.android.deskclock", "-c", "android.intent.category.LAUNCHER", "1"),
            ("shell", "monkey", "-p", "com.android.deskclock", "-c", "android.intent.category.LAUNCHER", "1"),
        ),
        expected_packages=frozenset({
            "com.google.android.deskclock",
            "com.android.deskclock",
        }),
    ),
}


def get_screen_target(screen_name: str) -> ScreenTarget:
    """Return the configured target for a screen name."""
    target = SCREEN_TARGETS.get(screen_name)
    if target is None:
        valid = ", ".join(sorted(SCREEN_TARGETS))
        print(f"[ERROR] Unknown screen '{screen_name}'.")
        print(f"        Valid screens: {valid}")
        sys.exit(1)
    return target


# ---------------------------------------------------------------------------
# Foreground package detection
# ---------------------------------------------------------------------------

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


def is_expected_package(package_name: str | None, target: ScreenTarget) -> bool:
    return package_name in target.expected_packages


def is_permission_controller(package_name: str | None) -> bool:
    return package_name in PERMISSION_CONTROLLER_PACKAGES


# ---------------------------------------------------------------------------
# Permission dialog handling
# ---------------------------------------------------------------------------

def parse_bounds(bounds_str: str) -> tuple[int, int, int, int] | None:
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds_str)
    if not match:
        return None
    return tuple(int(value) for value in match.groups())


def _button_score(resource_id: str, text: str, content_desc: str) -> int:
    haystack = " ".join((resource_id, text, content_desc)).lower()

    if any(negative in haystack for negative in DENY_TEXTS):
        return 0

    for index, allow_id in enumerate(ALLOW_RESOURCE_IDS):
        if allow_id in resource_id.lower():
            return 100 - index

    for index, allow_text in enumerate(ALLOW_TEXTS):
        if allow_text in haystack:
            return 80 - index

    return 0


def select_permission_allow_target(xml_text: str) -> tuple[int, int] | None:
    """Find the best positive permission button center in a UI hierarchy dump."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None

    best: TapTarget | None = None
    for node in root.iter("node"):
        bounds = parse_bounds(node.get("bounds", ""))
        if bounds is None:
            continue

        score = _button_score(
            node.get("resource-id", ""),
            node.get("text", ""),
            node.get("content-desc", ""),
        )
        if score <= 0:
            continue

        x1, y1, x2, y2 = bounds
        candidate = TapTarget(
            x=(x1 + x2) // 2,
            y=(y1 + y2) // 2,
            score=score,
        )
        if best is None or candidate.score > best.score:
            best = candidate

    if best is None:
        return None
    return best.x, best.y


def dump_permission_dialog_xml(adb: str, serial: str) -> str:
    run_adb(adb, serial, "shell", "uiautomator", "dump", PERMISSION_XML_REMOTE)
    xml_text = capture_adb(adb, serial, "shell", "cat", PERMISSION_XML_REMOTE)
    try:
        run_adb(adb, serial, "shell", "rm", "-f", PERMISSION_XML_REMOTE)
    except subprocess.CalledProcessError:
        pass
    return xml_text


def handle_permission_dialog(adb: str, serial: str) -> bool:
    """Tap an allow button on the current Android runtime permission dialog."""
    print("  [PERMISSION] Runtime permission dialog detected.")

    try:
        xml_text = dump_permission_dialog_xml(adb, serial)
    except subprocess.CalledProcessError as exc:
        print(f"  [WARN] Could not dump permission dialog XML: {exc.stderr.strip()}")
        return False

    tap_target = select_permission_allow_target(xml_text)
    if tap_target is None:
        print("  [WARN] No positive permission button found.")
        return False

    x, y = tap_target
    print(f"  [PERMISSION] Tapping allow button at ({x}, {y})")
    try:
        run_adb(adb, serial, "shell", "input", "tap", str(x), str(y))
    except subprocess.CalledProcessError as exc:
        print(f"  [WARN] Could not tap permission button: {exc.stderr.strip()}")
        return False

    time.sleep(SETTLE_DELAY)
    return True


# ---------------------------------------------------------------------------
# Target app launch and validation
# ---------------------------------------------------------------------------

def navigate_to_screen(screen_name: str) -> None:
    """
    Launch a target app/screen and validate that it became foreground.

    Raises SystemExit with a readable error if the target is unknown, launch
    commands fail, or Android stays on a different foreground package.
    """
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
    print(f"[ERROR] Failed to navigate to '{screen_name}'.")
    print(f"        Expected foreground package: {expected}")
    print(f"        Actual foreground package:   {last_foreground or 'unknown'}")
    if last_error:
        print(f"        Last launch error: {last_error}")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Captured XML package validation
# ---------------------------------------------------------------------------

def read_xml_packages(xml_path: str | Path) -> set[str]:
    """Return non-empty package names present in a captured UI hierarchy XML."""
    tree = ET.parse(xml_path)
    packages: set[str] = set()
    for node in tree.getroot().iter("node"):
        package_name = node.get("package", "")
        if package_name:
            packages.add(package_name)
    return packages


def validate_xml_package(xml_path: str | Path, screen_name: str) -> None:
    """Abort if a captured UI hierarchy does not contain the target package."""
    target = get_screen_target(screen_name)
    packages = read_xml_packages(xml_path)
    if packages & target.expected_packages:
        print(f"  [VALIDATE] XML package matches {screen_name}.")
        return

    expected = ", ".join(sorted(target.expected_packages))
    actual = ", ".join(sorted(packages)) if packages else "none"
    print(f"[ERROR] Captured XML does not match screen '{screen_name}'.")
    print(f"        Expected one of: {expected}")
    print(f"        Found packages:   {actual}")
    if packages & PERMISSION_CONTROLLER_PACKAGES:
        print("        Permission dialog was captured; navigation should handle it before capture.")
    sys.exit(1)
