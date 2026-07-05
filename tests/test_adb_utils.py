import contextlib
import io
import subprocess
import unittest
from unittest import mock

import adb_utils


class AdbUtilsTests(unittest.TestCase):
    @mock.patch("adb_utils.Path.is_file", return_value=False)
    @mock.patch.dict("adb_utils.os.environ", {}, clear=True)
    def test_resolve_adb_falls_back_to_path(self, _is_file):
        self.assertEqual("adb", adb_utils.resolve_adb())

    @mock.patch("adb_utils.subprocess.run")
    def test_get_device_serial_returns_first_authorized_device(self, run_mock):
        run_mock.return_value = subprocess.CompletedProcess(
            args=["adb", "devices"],
            returncode=0,
            stdout="List of devices attached\nemulator-5554\tdevice\nemulator-5556\tdevice\n",
            stderr="",
        )

        self.assertEqual("emulator-5554", adb_utils.get_device_serial("adb"))
        run_mock.assert_called_once_with(
            ["adb", "devices"],
            capture_output=True,
            text=True,
            check=True,
        )

    @mock.patch("adb_utils.subprocess.run")
    def test_get_device_serial_exits_without_authorized_device(self, run_mock):
        run_mock.return_value = subprocess.CompletedProcess(
            args=["adb", "devices"],
            returncode=0,
            stdout="List of devices attached\n",
            stderr="",
        )

        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit):
                adb_utils.get_device_serial("adb")

    @mock.patch("adb_utils.subprocess.run")
    def test_run_adb_builds_device_command(self, run_mock):
        run_mock.return_value = subprocess.CompletedProcess(
            args=["adb", "-s", "emulator-5554", "shell", "echo", "ok"],
            returncode=0,
            stdout="ok\n",
            stderr="",
        )

        result = adb_utils.run_adb("adb", "emulator-5554", "shell", "echo", "ok")

        self.assertEqual("ok\n", result.stdout)
        run_mock.assert_called_once_with(
            ["adb", "-s", "emulator-5554", "shell", "echo", "ok"],
            capture_output=True,
            text=True,
            check=True,
        )

    @mock.patch("adb_utils.run_adb")
    def test_capture_adb_returns_stdout(self, run_adb_mock):
        run_adb_mock.return_value = subprocess.CompletedProcess(
            args=["adb", "-s", "emulator-5554", "shell", "pwd"],
            returncode=0,
            stdout="/\n",
            stderr="",
        )

        self.assertEqual(
            "/\n",
            adb_utils.capture_adb("adb", "emulator-5554", "shell", "pwd"),
        )
        run_adb_mock.assert_called_once_with("adb", "emulator-5554", "shell", "pwd")


if __name__ == "__main__":
    unittest.main()
