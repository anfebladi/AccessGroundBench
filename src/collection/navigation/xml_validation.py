"""Validation helpers for captured Android UI hierarchy XML files."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from .navigation_targets import get_screen_target
from ..device.permission_dialog import PERMISSION_CONTROLLER_PACKAGES


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
    """Raise if a captured UI hierarchy does not contain the target package."""
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
    raise RuntimeError(f"Captured XML package mismatch for {screen_name}")
