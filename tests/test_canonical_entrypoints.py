"""Smoke tests for canonical packages and supported CLI entrypoints."""

import os
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def subprocess_environment() -> dict[str, str]:
    """Make the src-layout packages importable in child Python processes."""
    environment = os.environ.copy()
    src_path = str(PROJECT_ROOT / "src")
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        f"{src_path}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else src_path
    )
    return environment


class CanonicalPackageSmokeTests(unittest.TestCase):
    def test_canonical_packages_import(self):
        import collection.capture.bound_extractor
        import collection.capture.screenshot_pipeline
        import collection.device.adb_utils
        import collection.device.foreground_state
        import collection.device.layout_modifier
        import collection.device.permission_dialog
        import collection.navigation.app_navigator
        import collection.navigation.navigation_targets
        import collection.navigation.xml_validation
        import collection.orchestrator
        import mcnemar.cli
        import vlm_eval.cli
        import vlm_eval.provider


class CanonicalCliTests(unittest.TestCase):
    def assert_help_succeeds(self, *command: str) -> None:
        completed = subprocess.run(
            [sys.executable, *command],
            check=False,
            capture_output=True,
            text=True,
            env=subprocess_environment(),
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("usage:", completed.stdout.lower())

    def test_collection_command_supports_help(self):
        self.assert_help_succeeds("-m", "collection.orchestrator", "--help")

    def test_layout_modifier_command_supports_usage(self):
        completed = subprocess.run(
            [sys.executable, "-m", "collection.device.layout_modifier"],
            check=False,
            capture_output=True,
            text=True,
            env=subprocess_environment(),
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("usage:", completed.stdout.lower())

    def test_analysis_command_supports_help(self):
        self.assert_help_succeeds("-m", "mcnemar.cli", "--help")
