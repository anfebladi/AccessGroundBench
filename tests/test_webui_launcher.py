import io
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from webui.backend import server


class _FakeConfig:
    def __init__(self, app, **kwargs):
        self.app = app
        self.kwargs = kwargs


class _FakeServer:
    def __init__(self, config):
        self.config = config
        self.started = False
        self.should_exit = False

    def run(self):
        self.started = True


class _FakeThread:
    def __init__(self, target):
        self.target = target
        self.running = False

    def start(self):
        self.target()
        self.running = True

    def is_alive(self):
        return self.running

    def join(self, timeout=None):
        return None


class WebuiLauncherTests(unittest.TestCase):
    def _uvicorn(self, server_obj):
        return types.SimpleNamespace(Config=_FakeConfig, Server=lambda config: server_obj)

    # The name must match what ui_main actually looks for -- npm installs
    # vite.cmd on Windows, not vite. Spelling it "vite" here made the launcher
    # bail at its missing-dependency guard before reaching any of the behaviour
    # below, so three of these tests failed on the only platform this project
    # runs on while passing everywhere else.
    VITE_BIN = "vite.cmd" if os.name == "nt" else "vite"

    def _frontend(self):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        vite = root / "node_modules" / ".bin" / self.VITE_BIN
        vite.parent.mkdir(parents=True)
        vite.touch()
        return td, root

    def test_missing_frontend_dependency_reports_install_command(self):
        out = io.StringIO()
        with mock.patch.object(server.shutil, "which", return_value=None), mock.patch(
            "sys.stdout", out
        ):
            with self.assertRaises(SystemExit) as cm:
                server.ui_main([])
        self.assertEqual(1, cm.exception.code)
        self.assertIn("npm ci", out.getvalue())

    def test_starts_api_and_vite_and_passes_menu_url(self):
        td, frontend = self._frontend()
        self.addCleanup(td.cleanup)
        fake_server = _FakeServer(None)
        process = mock.Mock()
        process.poll.return_value = None
        process.wait.return_value = None
        seen = {}
        stderr_state = {}

        def launch_vite(*args, **kwargs):
            stderr_state["stream"] = kwargs["stderr"]
            stderr_state["writable"] = kwargs["stderr"].writable()
            return process

        def menu(url, shutdown):
            seen["url"] = url
            shutdown()

        with mock.patch.object(server, "FRONTEND_DIR", frontend), mock.patch.object(
            server.shutil, "which", return_value="/usr/bin/npm"
        ), mock.patch.dict(sys.modules, {"uvicorn": self._uvicorn(fake_server)}), mock.patch(
            "webui.backend.server.subprocess.Popen", side_effect=launch_vite
        ) as popen, mock.patch("webui.backend.server.urllib.request.urlopen") as opener, mock.patch(
            "webui.backend.banner.run_interactive_menu", side_effect=menu
        ), mock.patch("webui.backend.server.create_app", return_value=object()):
            opener.return_value.__enter__.return_value = object()
            server.ui_main(["--port", "5173", "--api-port", "8081"])

        self.assertEqual("http://127.0.0.1:5173", seen["url"])
        cmd = popen.call_args.args[0]
        expected_vite = str(frontend / "node_modules" / ".bin" / self.VITE_BIN)
        self.assertEqual([expected_vite, "--host", "127.0.0.1", "--port", "5173"], cmd)
        popen_kwargs = popen.call_args.kwargs
        self.assertIs(popen_kwargs["stdout"], server.subprocess.DEVNULL)
        self.assertIsNot(popen_kwargs["stderr"], sys.stderr)
        self.assertTrue(stderr_state["writable"])
        self.assertTrue(hasattr(stderr_state["stream"], "write"))
        self.assertTrue(fake_server.should_exit)
        process.terminate.assert_called_once_with()

    def test_vite_startup_failure_stops_api_server(self):
        td, frontend = self._frontend()
        self.addCleanup(td.cleanup)
        fake_server = _FakeServer(None)
        process = mock.Mock()
        process.poll.return_value = 1
        out = io.StringIO()

        def launch_vite(*args, **kwargs):
            kwargs["stderr"].write(b"error: port already in use")
            return process

        with mock.patch.object(server, "FRONTEND_DIR", frontend), mock.patch.object(
            server.shutil, "which", return_value="/usr/bin/npm"
        ), mock.patch.dict(sys.modules, {"uvicorn": self._uvicorn(fake_server)}), mock.patch(
            "webui.backend.server.subprocess.Popen", side_effect=launch_vite
        ), mock.patch("webui.backend.server.create_app", return_value=object()), mock.patch(
            "sys.stdout", out
        ):
            with self.assertRaises(SystemExit):
                server.ui_main([])
        self.assertIn("[ERROR] Vite failed to start:", out.getvalue())
        self.assertIn("error: port already in use", out.getvalue())
        self.assertTrue(fake_server.should_exit)

    def test_cleanup_kills_vite_when_terminate_does_not_finish(self):
        td, frontend = self._frontend()
        self.addCleanup(td.cleanup)
        fake_server = _FakeServer(None)
        process = mock.Mock()
        process.poll.return_value = None
        process.wait.side_effect = [server.subprocess.TimeoutExpired("vite", 5), None]

        def menu(_url, shutdown):
            shutdown()

        with mock.patch.object(server, "FRONTEND_DIR", frontend), mock.patch.object(
            server.shutil, "which", return_value="/usr/bin/npm"
        ), mock.patch.dict(sys.modules, {"uvicorn": self._uvicorn(fake_server)}), mock.patch(
            "webui.backend.server.subprocess.Popen", return_value=process
        ), mock.patch("webui.backend.server.urllib.request.urlopen") as opener, mock.patch(
            "webui.backend.banner.run_interactive_menu", side_effect=menu
        ), mock.patch("webui.backend.server.create_app", return_value=object()):
            opener.return_value.__enter__.return_value = object()
            server.ui_main([])
        process.terminate.assert_called_once_with()
        process.kill.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
