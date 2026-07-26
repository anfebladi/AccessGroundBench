"""Target-screen definitions for AccessGroundBench navigation."""

from __future__ import annotations

from dataclasses import dataclass


class UnknownScreenError(ValueError):
    """Raised when a caller requests a screen that is not registered."""


@dataclass(frozen=True)
class ScreenTarget:
    name: str
    launch_commands: tuple[tuple[str, ...], ...]
    expected_packages: frozenset[str]
    default_enabled: bool = True


def _target(
    name: str,
    launch_commands: tuple[tuple[str, ...], ...],
    expected_packages: frozenset[str],
    *,
    default_enabled: bool = True,
) -> ScreenTarget:
    return ScreenTarget(
        name=name,
        launch_commands=launch_commands,
        expected_packages=expected_packages,
        default_enabled=default_enabled,
    )


SCREEN_TARGETS: dict[str, ScreenTarget] = {
    "settings_main": _target(
        "settings_main",
        (
            ("shell", "am", "start", "-a", "android.settings.SETTINGS"),
            ("shell", "monkey", "-p", "com.android.settings", "-c", "android.intent.category.LAUNCHER", "1"),
        ),
        frozenset({"com.android.settings", "com.google.android.settings.intelligence"}),
    ),
    "settings_display": _target(
        "settings_display",
        (("shell", "am", "start", "-a", "android.settings.DISPLAY_SETTINGS"),),
        frozenset({"com.android.settings", "com.google.android.settings.intelligence"}),
    ),
    "settings_network": _target(
        "settings_network",
        (("shell", "am", "start", "-a", "android.settings.WIRELESS_SETTINGS"),),
        frozenset({"com.android.settings", "com.google.android.settings.intelligence"}),
    ),
    "settings_accessibility": _target(
        "settings_accessibility",
        (("shell", "am", "start", "-a", "android.settings.ACCESSIBILITY_SETTINGS"),),
        frozenset({"com.android.settings", "com.google.android.settings.intelligence"}),
    ),
    "contacts": _target(
        "contacts",
        (
            ("shell", "am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.APP_CONTACTS"),
            ("shell", "monkey", "-p", "com.google.android.contacts", "-c", "android.intent.category.LAUNCHER", "1"),
            ("shell", "monkey", "-p", "com.android.contacts", "-c", "android.intent.category.LAUNCHER", "1"),
        ),
        frozenset({"com.google.android.contacts", "com.android.contacts"}),
    ),
    "dialer": _target(
        "dialer",
        (
            ("shell", "am", "start", "-a", "android.intent.action.DIAL"),
            ("shell", "monkey", "-p", "com.google.android.dialer", "-c", "android.intent.category.LAUNCHER", "1"),
            ("shell", "monkey", "-p", "com.android.dialer", "-c", "android.intent.category.LAUNCHER", "1"),
        ),
        frozenset({"com.google.android.dialer", "com.android.dialer"}),
    ),
    "messages": _target(
        "messages",
        (
            ("shell", "am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.APP_MESSAGING"),
            ("shell", "monkey", "-p", "com.google.android.apps.messaging", "-c", "android.intent.category.LAUNCHER", "1"),
            ("shell", "monkey", "-p", "com.android.messaging", "-c", "android.intent.category.LAUNCHER", "1"),
        ),
        frozenset({"com.google.android.apps.messaging", "com.android.messaging"}),
    ),
    "clock": _target(
        "clock",
        (
            ("shell", "am", "start", "-a", "android.intent.action.SHOW_ALARMS"),
            ("shell", "monkey", "-p", "com.google.android.deskclock", "-c", "android.intent.category.LAUNCHER", "1"),
            ("shell", "monkey", "-p", "com.android.deskclock", "-c", "android.intent.category.LAUNCHER", "1"),
        ),
        frozenset({"com.google.android.deskclock", "com.android.deskclock"}),
    ),
    "calculator": _target(
        "calculator",
        (
            ("shell", "monkey", "-p", "com.google.android.calculator", "-c", "android.intent.category.LAUNCHER", "1"),
            ("shell", "monkey", "-p", "com.android.calculator2", "-c", "android.intent.category.LAUNCHER", "1"),
        ),
        frozenset({"com.google.android.calculator", "com.android.calculator2"}),
        default_enabled=False,
    ),
    "calendar": _target(
        "calendar",
        (
            ("shell", "monkey", "-p", "com.google.android.calendar", "-c", "android.intent.category.LAUNCHER", "1"),
            ("shell", "monkey", "-p", "com.android.calendar", "-c", "android.intent.category.LAUNCHER", "1"),
        ),
        frozenset({"com.google.android.calendar", "com.android.calendar"}),
        default_enabled=False,
    ),
    "chrome": _target(
        "chrome",
        (
            ("shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", "https://www.google.com"),
            ("shell", "monkey", "-p", "com.android.chrome", "-c", "android.intent.category.LAUNCHER", "1"),
        ),
        frozenset({"com.android.chrome"}),
        default_enabled=False,
    ),
    "maps": _target(
        "maps",
        (("shell", "monkey", "-p", "com.google.android.apps.maps", "-c", "android.intent.category.LAUNCHER", "1"),),
        frozenset({"com.google.android.apps.maps"}),
    ),
    "camera": _target(
        "camera",
        (
            ("shell", "am", "start", "-a", "android.media.action.IMAGE_CAPTURE"),
            ("shell", "monkey", "-p", "com.google.android.GoogleCamera", "-c", "android.intent.category.LAUNCHER", "1"),
            ("shell", "monkey", "-p", "com.android.camera2", "-c", "android.intent.category.LAUNCHER", "1"),
        ),
        frozenset({"com.google.android.GoogleCamera", "com.android.camera2"}),
        default_enabled=False,
    ),
    "files": _target(
        "files",
        (
            ("shell", "monkey", "-p", "com.google.android.apps.nbu.files", "-c", "android.intent.category.LAUNCHER", "1"),
            ("shell", "monkey", "-p", "com.android.documentsui", "-c", "android.intent.category.LAUNCHER", "1"),
        ),
        frozenset({"com.google.android.apps.nbu.files", "com.android.documentsui"}),
        default_enabled=False,
    ),
    "play_store": _target(
        "play_store",
        (("shell", "monkey", "-p", "com.android.vending", "-c", "android.intent.category.LAUNCHER", "1"),),
        frozenset({"com.android.vending"}),
    ),
    "gmail": _target(
        "gmail",
        (("shell", "monkey", "-p", "com.google.android.gm", "-c", "android.intent.category.LAUNCHER", "1"),),
        frozenset({"com.google.android.gm"}),
    ),
    "youtube": _target(
        "youtube",
        (("shell", "monkey", "-p", "com.google.android.youtube", "-c", "android.intent.category.LAUNCHER", "1"),),
        frozenset({"com.google.android.youtube"}),
    ),
    "photos": _target(
        "photos",
        (
            ("shell", "monkey", "-p", "com.google.android.apps.photos", "-c", "android.intent.category.LAUNCHER", "1"),
            ("shell", "monkey", "-p", "com.android.gallery3d", "-c", "android.intent.category.LAUNCHER", "1"),
        ),
        frozenset({"com.google.android.apps.photos", "com.android.gallery3d"}),
    ),
}


def get_screen_target(screen_name: str) -> ScreenTarget:
    """Return a registered target or raise a caller-handleable error."""
    target = SCREEN_TARGETS.get(screen_name)
    if target is None:
        valid = ", ".join(sorted(SCREEN_TARGETS))
        raise UnknownScreenError(
            f"Unknown screen '{screen_name}'. Valid screens: {valid}"
        )
    return target


def default_screen_names() -> tuple[str, ...]:
    """Return targets enabled for the default collection run."""
    return tuple(
        name for name, target in SCREEN_TARGETS.items() if target.default_enabled
    )
