"""Android runtime-permission dialog detection and interaction."""

from __future__ import annotations

import re
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from .adb_utils import capture_adb, run_adb


SETTLE_DELAY: float = 2.0
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
class TapTarget:
    x: int
    y: int
    score: int


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


def is_permission_controller(package_name: str | None) -> bool:
    return package_name in PERMISSION_CONTROLLER_PACKAGES
