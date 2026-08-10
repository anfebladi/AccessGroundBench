import os
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = PROJECT_ROOT / "scripts" / "agb"
INSTALLER = PROJECT_ROOT / "scripts" / "install-agb.sh"


class AgbLauncherTests(unittest.TestCase):
    def test_launcher_uses_project_root_through_symlink_and_forwards_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            fake_bin = work / "bin"
            fake_bin.mkdir()
            log = work / "uv.log"
            fake_uv = fake_bin / "uv"
            fake_uv.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$PWD\" > \"$UV_TEST_LOG\"\n"
                "printf '%s\\n' \"$@\" >> \"$UV_TEST_LOG\"\n"
            )
            fake_uv.chmod(0o755)

            link = work / "nested" / "agb"
            link.parent.mkdir()
            link.symlink_to(LAUNCHER)
            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
            env["UV_TEST_LOG"] = str(log)

            result = subprocess.run(
                [str(link), "--example", "value with spaces"],
                cwd=work,
                env=env,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            lines = log.read_text().splitlines()
            self.assertEqual(lines[0], str(PROJECT_ROOT))
            self.assertEqual(
                lines[1:],
                ["run", "--project", str(PROJECT_ROOT), "agb", "--example", "value with spaces"],
            )


class AgbInstallerTests(unittest.TestCase):
    def run_installer(self, bin_home: Path, *args: str):
        env = os.environ.copy()
        env["XDG_BIN_HOME"] = str(bin_home)
        # Keep the fallback home isolated as well; the installer must not touch
        # the real user's home even when XDG_BIN_HOME handling regresses.
        env["HOME"] = str(bin_home.parent / "home")
        return subprocess.run(
            [str(INSTALLER), *args],
            cwd=PROJECT_ROOT,
            env=env,
            text=True,
            capture_output=True,
        )

    def test_installer_creates_and_reuses_desired_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_home = Path(tmp) / "bin"
            first = self.run_installer(bin_home)
            self.assertEqual(first.returncode, 0, first.stderr)
            target = bin_home / "agb"
            self.assertTrue(target.is_symlink())
            self.assertEqual(target.resolve(), LAUNCHER.resolve())

            second = self.run_installer(bin_home)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertTrue(target.is_symlink())
            self.assertEqual(target.resolve(), LAUNCHER.resolve())

    def test_installer_refuses_conflict_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_home = Path(tmp) / "bin"
            bin_home.mkdir()
            target = bin_home / "agb"
            target.write_text("keep me")

            result = self.run_installer(bin_home)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(target.is_symlink())
            self.assertEqual(target.read_text(), "keep me")

    def test_installer_force_replaces_conflicting_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_home = Path(tmp) / "bin"
            bin_home.mkdir()
            target = bin_home / "agb"
            target.write_text("replace me")

            result = self.run_installer(bin_home, "--force")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(target.is_symlink())
            self.assertEqual(target.resolve(), LAUNCHER.resolve())


if __name__ == "__main__":
    unittest.main()
