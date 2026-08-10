"""Colored startup banner and interactive terminal menu for `agb ui`.

No new dependency: colors are raw ANSI escape codes, and the arrow-key menu
reads single keypresses via the stdlib (`msvcrt` on Windows, `termios`/`tty`
on POSIX) rather than a TUI library. The web UI itself is unaffected either
way -- this only changes what prints in the terminal that launched it.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import sys
import time
import webbrowser
from importlib.metadata import PackageNotFoundError, version

_RESET = "\033[0m"
_BOLD = "\033[1m"
_PRIMARY = "\033[38;5;51m"       # bright cyan -- borders, title
_ACCENT = "\033[38;5;213m"       # pink/magenta -- the URL
_HIGHLIGHT = "\033[48;5;23m\033[97m\033[1m"  # deep-teal bg, bold white fg -- selected menu row
_DIM = "\033[2m"

_TARGET_EMOJI = "\U0001f3af"  # a target, not a rocket -- this benchmark scores taps on targets

MENU_ITEMS = ("Open in Browser", "Copy URL", "Exit")


def _package_version() -> str:
    try:
        return version("accessgroundbench")
    except PackageNotFoundError:
        return "dev"


def _enable_windows_ansi() -> None:
    """Turn on virtual-terminal (ANSI escape code) processing on Windows.

    Modern Windows Terminal/PowerShell already support ANSI codes natively,
    but legacy conhost (plain cmd.exe) needs this enabled per-process, or
    every color code below prints as literal garbage instead of a color.
    A no-op, and safe to call unconditionally, on any other platform.
    """
    if os.name != "nt":
        return
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return
        enable_vt = 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        kernel32.SetConsoleMode(handle, mode.value | enable_vt)
    except Exception:
        pass  # Best-effort -- worst case, colors don't render.


def _terminal_width() -> int:
    try:
        return max(40, shutil.get_terminal_size().columns)
    except OSError:
        return 60


def _copy_to_clipboard(text: str) -> bool:
    """Best-effort clipboard copy via a platform command; no pip dependency."""
    import subprocess

    try:
        if os.name == "nt":
            proc = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
        elif sys.platform == "darwin":
            proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        else:
            proc = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
        proc.communicate(text.encode("utf-8"), timeout=3)
        return proc.returncode == 0
    except Exception:
        return False


def _read_key() -> str:
    """Block for one keypress; returns 'up' / 'down' / 'enter' / 'quit' / ''."""
    if os.name == "nt":
        import msvcrt

        ch = msvcrt.getch()
        if ch in (b"\x00", b"\xe0"):  # arrow-key prefix
            ch2 = msvcrt.getch()
            return {b"H": "up", b"P": "down"}.get(ch2, "")
        if ch in (b"\r", b"\n"):
            return "enter"
        if ch == b"\x03":
            return "quit"
        if ch.lower() == b"q":
            return "quit"
        return ""

    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            ch2 = sys.stdin.read(1)
            if ch2 == "[":
                ch3 = sys.stdin.read(1)
                return {"A": "up", "B": "down"}.get(ch3, "")
            return "quit"
        if ch in ("\r", "\n"):
            return "enter"
        if ch == "\x03":
            return "quit"
        if ch.lower() == "q":
            return "quit"
        return ""
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _render(url: str, selected: int, status: str) -> list[str]:
    rule = _PRIMARY + ("=" * _terminal_width()) + _RESET
    lines = [
        rule,
        f"  {_BOLD}{_PRIMARY}AccessGroundBench UI (v{_package_version()}){_RESET}",
        rule,
        f"{_TARGET_EMOJI} {_DIM}Server:{_RESET} {_ACCENT}{url}{_RESET}",
        rule,
        "",
    ]
    for i, label in enumerate(MENU_ITEMS):
        if i == selected:
            lines.append(f"  {_HIGHLIGHT}> {label}{_RESET}")
        else:
            lines.append(f"    {label}")
    lines.append("")
    lines.append(status)
    return lines


def _draw(lines: list[str], previous_line_count: int) -> None:
    if previous_line_count:
        sys.stdout.write(f"\033[{previous_line_count}A")
    for line in lines:
        sys.stdout.write("\033[2K" + line + "\n")
    sys.stdout.flush()


def run_interactive_menu(url: str, on_exit) -> None:
    """Render the banner and an arrow-key menu until the user exits.

    on_exit() is called once, after the user chooses Exit or presses q/Ctrl+C,
    to let the caller shut down the server before this function returns.
    """
    _enable_windows_ansi()
    is_tty = sys.stdin.isatty() and sys.stdout.isatty()

    selected = 0
    status = "  ↑/↓ to navigate, Enter to select, q to quit"
    lines = _render(url, selected, status)
    _draw(lines, 0)

    if not is_tty:
        # Not an interactive terminal (piped output, a background launch,
        # CI, etc.): there is nothing to navigate, but the server must keep
        # running until interrupted -- returning here would let ui_main's
        # caller fall through and the daemon server thread would be killed
        # with it. Block the same way a plain foreground server would.
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            on_exit()
        return

    try:
        while True:
            key = _read_key()
            if key == "up":
                selected = (selected - 1) % len(MENU_ITEMS)
            elif key == "down":
                selected = (selected + 1) % len(MENU_ITEMS)
            elif key == "quit":
                break
            elif key == "enter":
                choice = MENU_ITEMS[selected]
                if choice == "Open in Browser":
                    webbrowser.open(url)
                    status = f"  Opened {url} in your browser."
                elif choice == "Copy URL":
                    status = "  URL copied to clipboard." if _copy_to_clipboard(url) \
                        else "  Could not copy automatically -- copy it manually above."
                elif choice == "Exit":
                    break
            new_lines = _render(url, selected, status)
            _draw(new_lines, len(lines))
            lines = new_lines
    finally:
        on_exit()


__all__ = ["run_interactive_menu"]
