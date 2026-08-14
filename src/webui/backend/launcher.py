"""Process launcher for the local AccessGroundBench web UI -- the `agb ui` entry point.

Separate from server.py on purpose: server.py answers HTTP requests, this
module manages operating-system processes. Running the UI means supervising
two of them -- a uvicorn thread serving the API and a Vite child process
serving the frontend -- plus an interactive terminal menu that owns the
foreground until the user quits. None of that is the API's concern, and
mixing the two made server.py both an app and a process manager.

Binds 127.0.0.1 only, always -- not configurable. Session API keys live in
the API process's memory (see .keys), so the server must never accept
connections from beyond localhost.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from .server import create_app

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"


def serve(host: str, port: int) -> None:
    """Run the server in the foreground with uvicorn's own logging.

    Kept as a plain, non-interactive entry point for anything that wants the
    server without the terminal banner/menu below -- `ui_main` is what
    `agb ui` actually calls.
    """
    import uvicorn

    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")


def ui_main(argv: list[str] | None = None) -> None:
    """Launch the loopback FastAPI API and local Vite development server."""
    if hasattr(sys.stdout, "reconfigure"):
        # The banner's rocket emoji crashes under Windows' default console
        # codepage (cp1252) otherwise -- same fix evaluation.cli.evaluate_main
        # already applies for the same reason.
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError:
        print(
            "[ERROR] The web UI needs the 'ui' extra. Install it with:\n"
            "  uv sync --extra ui\n"
            "or:\n"
            "  pip install -e .[ui]"
        )
        raise SystemExit(1)

    import uvicorn

    from .banner import run_interactive_menu

    parser = argparse.ArgumentParser(description="AccessGroundBench -- local web UI")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--api-port", type=int, default=8081)
    args = parser.parse_args(argv)

    npm = shutil.which("npm")
    vite = FRONTEND_DIR / "node_modules" / ".bin" / ("vite.cmd" if os.name == "nt" else "vite")
    if npm is None or not vite.is_file():
        print(
            "[ERROR] Frontend dependencies are missing. Install them with:\n"
            "  cd src/webui/frontend && npm ci"
        )
        raise SystemExit(1)

    app = create_app()
    # warning, not info: the interactive banner below replaces uvicorn's own
    # startup/access log lines, which would otherwise print through and
    # scramble the banner's redraw-in-place cursor math.
    config = uvicorn.Config(app, host="127.0.0.1", port=args.api_port, log_level="warning")
    uv_server = uvicorn.Server(config)

    server_thread = threading.Thread(target=uv_server.run, daemon=True)
    server_thread.start()

    deadline = time.monotonic() + 10
    while not uv_server.started and server_thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not uv_server.started:
        raise SystemExit(1)  # uvicorn failed to start (e.g. port already in use)

    vite_process: subprocess.Popen[bytes] | None = None
    vite_stderr = tempfile.TemporaryFile(mode="w+b")

    def cleanup() -> None:
        if vite_process is not None and vite_process.poll() is None:
            vite_process.terminate()
            try:
                vite_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                vite_process.kill()
                vite_process.wait()
        uv_server.should_exit = True
        server_thread.join(timeout=5)
        if not vite_stderr.closed:
            vite_stderr.close()

    try:
        vite_process = subprocess.Popen(
            [str(vite), "--host", "127.0.0.1", "--port", str(args.port)],
            cwd=FRONTEND_DIR,
            env={**os.environ, "AGB_API_PORT": str(args.api_port)},
            stdout=subprocess.DEVNULL,
            stderr=vite_stderr,
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if vite_process.poll() is not None:
                vite_stderr.seek(0)
                stderr = vite_stderr.read().decode(errors="replace")
                if isinstance(stderr, str) and stderr.strip():
                    print(f"[ERROR] Vite failed to start:\n{stderr.strip()}")
                raise SystemExit(1)
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{args.port}/", timeout=0.5):
                    break
            except (urllib.error.URLError, OSError):
                time.sleep(0.05)
        else:
            raise SystemExit(1)

        url = f"http://127.0.0.1:{args.port}"

        run_interactive_menu(url, cleanup)
    except BaseException:
        cleanup()
        raise


__all__ = ["FRONTEND_DIR", "serve", "ui_main"]
