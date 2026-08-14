"""Supported Android screen and tap target declarations."""

from __future__ import annotations

import sys
from dataclasses import dataclass

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
        expected_packages=frozenset({
            "com.android.settings",
            "com.google.android.settings.intelligence",
        }),
    ),
    "settings_display": ScreenTarget(
        name="settings_display",
        launch_commands=(
            ("shell", "am", "start", "-a", "android.settings.DISPLAY_SETTINGS"),
        ),
        expected_packages=frozenset({
            "com.android.settings",
            "com.google.android.settings.intelligence",
        }),
    ),
    "settings_network": ScreenTarget(
        name="settings_network",
        launch_commands=(
            ("shell", "am", "start", "-a", "android.settings.WIRELESS_SETTINGS"),
        ),
        expected_packages=frozenset({
            "com.android.settings",
            "com.google.android.settings.intelligence",
        }),
    ),
    "settings_accessibility": ScreenTarget(
        name="settings_accessibility",
        launch_commands=(
            ("shell", "am", "start", "-a", "android.settings.ACCESSIBILITY_SETTINGS"),
        ),
        expected_packages=frozenset({
            "com.android.settings",
            "com.google.android.settings.intelligence",
        }),
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
    "calculator": ScreenTarget(
        name="calculator",
        launch_commands=(
            ("shell", "monkey", "-p", "com.google.android.calculator", "-c", "android.intent.category.LAUNCHER", "1"),
            ("shell", "monkey", "-p", "com.android.calculator2", "-c", "android.intent.category.LAUNCHER", "1"),
        ),
        expected_packages=frozenset({
            "com.google.android.calculator",
            "com.android.calculator2",
        }),
    ),
    "calendar": ScreenTarget(
        name="calendar",
        launch_commands=(
            ("shell", "monkey", "-p", "com.google.android.calendar", "-c", "android.intent.category.LAUNCHER", "1"),
            ("shell", "monkey", "-p", "com.android.calendar", "-c", "android.intent.category.LAUNCHER", "1"),
        ),
        expected_packages=frozenset({
            "com.google.android.calendar",
            "com.android.calendar",
        }),
    ),
    "chrome": ScreenTarget(
        name="chrome",
        launch_commands=(
            ("shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", "https://www.google.com"),
            ("shell", "monkey", "-p", "com.android.chrome", "-c", "android.intent.category.LAUNCHER", "1"),
        ),
        expected_packages=frozenset({
            "com.android.chrome",
        }),
    ),
    "maps": ScreenTarget(
        name="maps",
        launch_commands=(
            ("shell", "monkey", "-p", "com.google.android.apps.maps", "-c", "android.intent.category.LAUNCHER", "1"),
        ),
        expected_packages=frozenset({
            "com.google.android.apps.maps",
        }),
    ),
    "camera": ScreenTarget(
        name="camera",
        launch_commands=(
            ("shell", "am", "start", "-a", "android.media.action.IMAGE_CAPTURE"),
            ("shell", "monkey", "-p", "com.google.android.GoogleCamera", "-c", "android.intent.category.LAUNCHER", "1"),
            ("shell", "monkey", "-p", "com.android.camera2", "-c", "android.intent.category.LAUNCHER", "1"),
        ),
        expected_packages=frozenset({
            "com.google.android.GoogleCamera",
            "com.android.camera2",
        }),
    ),
    "files": ScreenTarget(
        name="files",
        launch_commands=(
            ("shell", "monkey", "-p", "com.google.android.apps.nbu.files", "-c", "android.intent.category.LAUNCHER", "1"),
            ("shell", "monkey", "-p", "com.android.documentsui", "-c", "android.intent.category.LAUNCHER", "1"),
        ),
        expected_packages=frozenset({
            "com.google.android.apps.nbu.files",
            "com.android.documentsui",
        }),
    ),
    "play_store": ScreenTarget(
        name="play_store",
        launch_commands=(
            ("shell", "monkey", "-p", "com.android.vending", "-c", "android.intent.category.LAUNCHER", "1"),
        ),
        expected_packages=frozenset({
            "com.android.vending",
        }),
    ),
    "gmail": ScreenTarget(
        name="gmail",
        launch_commands=(
            ("shell", "monkey", "-p", "com.google.android.gm", "-c", "android.intent.category.LAUNCHER", "1"),
        ),
        expected_packages=frozenset({
            "com.google.android.gm",
        }),
    ),
    "youtube": ScreenTarget(
        name="youtube",
        launch_commands=(
            ("shell", "monkey", "-p", "com.google.android.youtube", "-c", "android.intent.category.LAUNCHER", "1"),
        ),
        expected_packages=frozenset({
            "com.google.android.youtube",
        }),
    ),
    "photos": ScreenTarget(
        name="photos",
        launch_commands=(
            ("shell", "monkey", "-p", "com.google.android.apps.photos", "-c", "android.intent.category.LAUNCHER", "1"),
            ("shell", "monkey", "-p", "com.android.gallery3d", "-c", "android.intent.category.LAUNCHER", "1"),
        ),
        expected_packages=frozenset({
            "com.google.android.apps.photos",
            "com.android.gallery3d",
        }),
    ),
}

# Screens that stay fully supported but are not captured by default.
#
# Gmail renders the signed-in account's real inbox -- sender names, subject
# lines, body previews, and receipt times -- so a capture of it is a capture of
# whoever's account the emulator is signed into. The published dataset omits it
# for that reason, not because the screen is unsupported: it is still in
# SCREEN_TARGETS, and `agb collect --screens gmail` collects it normally. Anyone
# reproducing the benchmark on their own account can opt back in.
OPT_IN_SCREENS: frozenset[str] = frozenset({"gmail"})

# Stable capture order for a full benchmark collection.
SCREENS: list[str] = [
    "settings_main", "settings_display", "settings_network", "settings_accessibility",
    "contacts", "dialer", "messages",
    "clock",
    "maps", "play_store",
    "youtube", "photos",
]


def get_screen_target(screen_name: str) -> ScreenTarget:
    """Return the configured target for a screen name."""
    target = SCREEN_TARGETS.get(screen_name)
    if target is None:
        valid = ", ".join(sorted(SCREEN_TARGETS))
        print(f"[ERROR] Unknown screen '{screen_name}'.")
        print(f"        Valid screens: {valid}")
        sys.exit(1)
    return target
