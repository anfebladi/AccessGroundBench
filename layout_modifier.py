"""
layout_modifier.py
------------------
The Compounding Chaos Engine.

Programmatically injects multi-variable accessibility profiles into the
Android Emulator by combining font scale, pixel density, and RTL layout
direction simultaneously to simulate real-world elder-user UI conditions.
"""

import subprocess
import sys
import time

from adb_utils import get_device_serial, resolve_adb, run_adb

# ---------------------------------------------------------------------------
# Profile Matrix
# Each profile specifies 3 independent display vectors applied together.
# ---------------------------------------------------------------------------

ELDER_PROFILES: dict[str, dict[str, str]] = {
    "baseline": {
        "font_scale": "1.0",
        "density":    "reset",
        "rtl":        "0",
        "daltonizer": "off",
    },
    "elder_text_heavy": {
        "font_scale": "1.4",
        "density":    "reset",
        "rtl":        "0",
        "daltonizer": "off",
    },
    "elder_zoom_heavy": {
        "font_scale": "1.0",
        "density":    "480",
        "rtl":        "0",
        "daltonizer": "off",
    },
    "elder_combo_max": {
        "font_scale": "1.6",
        "density":    "520",
        "rtl":        "0",
        "daltonizer": "off",
    },
    "elder_combo_rtl": {
        "font_scale": "1.5",
        "density":    "480",
        "rtl":        "1",
        "daltonizer": "off",
    },
    # Color vector only: geometry stays at baseline so the color remap is
    # the single isolated variable versus baseline. Deuteranomaly (green-weak)
    # is the most common form of color-vision deficiency.
    "colorblind_deuteranomaly": {
        "font_scale": "1.0",
        "density":    "reset",
        "rtl":        "0",
        "daltonizer": "deuteranomaly",
    },
}

# Android on-device color-correction (daltonizer) modes, mapped to the numeric
# values the accessibility_display_daltonizer secure setting expects.
DALTONIZER_MODES: dict[str, str] = {
    "monochromacy": "0",   # grayscale / total color blindness
    "protanomaly":  "11",  # red-weak
    "deuteranomaly": "12",  # green-weak (most common)
    "tritanomaly":  "13",  # blue-weak
}

# Settling delay (seconds) — allows Android rendering loop to finish
# reflow animations and recalculate bounding boxes before capture fires.
SETTLE_DELAY: float = 2.5


# ---------------------------------------------------------------------------
# Vector Applicators
# ---------------------------------------------------------------------------

def _run(adb: str, serial: str, *args: str) -> None:
    """Fire a single ADB command with check=True error enforcement."""
    run_adb(adb, serial, *args)


def apply_font_scale(adb: str, serial: str, value: str) -> None:
    """
    Vector 1 — Text Resizing.
    Modifies the system global font_scale multiplier.
    """
    print(f"  [V1] font_scale -> {value}")
    _run(adb, serial, "shell", "settings", "put", "system", "font_scale", value)


def apply_density(adb: str, serial: str, value: str) -> None:
    """
    Vector 2 — Element Inflation (Density).
    Overrides the virtual screen PPI display scale, or resets to default.
    """
    print(f"  [V2] density    -> {value}")
    if value.lower() == "reset":
        _run(adb, serial, "shell", "wm", "density", "reset")
    else:
        _run(adb, serial, "shell", "wm", "density", value)


def apply_rtl(adb: str, serial: str, value: str) -> None:
    """
    Vector 3 — Layout Reversal (RTL Mirroring).
    Injects the developer force-RTL global override flag (0 = off, 1 = on).
    """
    print(f"  [V3] RTL        -> {'ON' if value == '1' else 'OFF'}")
    _run(
        adb, serial,
        "shell", "settings", "put", "global",
        "development_settings_force_rtl", value,
    )


def apply_daltonizer(adb: str, serial: str, value: str) -> None:
    """
    Vector 4 — Color Remap (color-blindness correction filter).

    Toggles Android's on-device daltonizer, a display-level color transform.
    `value` is "off" or a key of DALTONIZER_MODES (e.g. "deuteranomaly").

    NOTE: The daltonizer is applied by the display composition pipeline, not
    baked into individual app surfaces. On some Android/emulator versions
    `adb screencap` captures buffers BEFORE this transform, so the saved PNG
    may not show the color change. Always visually confirm a captured
    colorblind screenshot differs from baseline before trusting a run.
    """
    if value == "off":
        print("  [V4] color      -> OFF")
        _run(
            adb, serial,
            "shell", "settings", "put", "secure",
            "accessibility_display_daltonizer_enabled", "0",
        )
        return

    mode = DALTONIZER_MODES.get(value)
    if mode is None:
        valid = ", ".join(["off", *DALTONIZER_MODES])
        print(f"[ERROR] Unknown daltonizer mode '{value}'. Valid: {valid}")
        sys.exit(1)

    print(f"  [V4] color      -> {value} (daltonizer mode {mode})")
    _run(
        adb, serial,
        "shell", "settings", "put", "secure",
        "accessibility_display_daltonizer_enabled", "1",
    )
    _run(
        adb, serial,
        "shell", "settings", "put", "secure",
        "accessibility_display_daltonizer", mode,
    )


# ---------------------------------------------------------------------------
# Global Failsafe Reset
# ---------------------------------------------------------------------------

def reset_all(adb: str | None = None, serial: str | None = None) -> None:
    """
    Force-reset all three display vectors to clean factory baselines:
      font_scale = 1.0 | density = reset | RTL = 0

    Can be called standalone (resolves ADB/device automatically) or
    injected with pre-resolved adb/serial strings by the orchestrator.
    """
    if adb is None:
        adb = resolve_adb()
    if serial is None:
        serial = get_device_serial(adb)

    print("\n[RESET] Restoring all display vectors to factory baseline...")
    apply_font_scale(adb, serial, "1.0")
    apply_density(adb, serial, "reset")
    apply_rtl(adb, serial, "0")
    apply_daltonizer(adb, serial, "off")
    print("[RESET] Complete. Emulator is back to baseline.")


# ---------------------------------------------------------------------------
# Core Profile Applicator
# ---------------------------------------------------------------------------

def apply_profile(profile_name: str) -> None:
    """
    Apply a named accessibility profile to the active emulator.

    Steps:
      1. Validate the profile name against ELDER_PROFILES.
      2. Resolve ADB and detect the active device serial.
      3. Apply all three vectors sequentially.
      4. Block for SETTLE_DELAY seconds so the Android rendering loop
         finishes reflow before any downstream capture tool fires.

    Args:
        profile_name: Key into ELDER_PROFILES (e.g. "elder_combo_max").
    """
    if profile_name not in ELDER_PROFILES:
        valid = ", ".join(ELDER_PROFILES.keys())
        print(f"[ERROR] Unknown profile '{profile_name}'.")
        print(f"        Valid options: {valid}")
        sys.exit(1)

    profile = ELDER_PROFILES[profile_name]

    print("=" * 60)
    print(f"  Layout Modifier — Chaos Engine")
    print(f"  Profile : {profile_name}")
    print(f"  Vectors : font={profile['font_scale']}  "
          f"density={profile['density']}  "
          f"rtl={profile['rtl']}  "
          f"color={profile['daltonizer']}")
    print("=" * 60)

    adb = resolve_adb()
    serial = get_device_serial(adb)
    print(f"[DEVICE] {serial}\n")

    try:
        apply_font_scale(adb, serial, profile["font_scale"])
        apply_density(adb, serial, profile["density"])
        apply_rtl(adb, serial, profile["rtl"])
        apply_daltonizer(adb, serial, profile["daltonizer"])

    except subprocess.CalledProcessError as exc:
        print(f"\n[FATAL] ADB command failed:\n  {exc.cmd}\n  {exc.stderr}")
        print("[INFO]  Attempting emergency reset...")
        reset_all(adb, serial)
        sys.exit(1)

    print(f"\n[SETTLE] Waiting {SETTLE_DELAY}s for Android rendering loop to stabilize...")
    time.sleep(SETTLE_DELAY)
    print("[SETTLE] Reflow complete. Ready for capture.\n")
    print("=" * 60)
    print(f"  Profile '{profile_name}' applied successfully.")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python layout_modifier.py <profile_name>   # apply a profile")
        print("  python layout_modifier.py reset            # factory reset all vectors")
        print()
        print("Available profiles:")
        for name, cfg in ELDER_PROFILES.items():
            print(f"  {name:<26} font={cfg['font_scale']}  "
                  f"density={cfg['density']:<6}  rtl={cfg['rtl']}  "
                  f"color={cfg['daltonizer']}")
        sys.exit(0)

    arg = sys.argv[1].strip().lower()

    if arg == "reset":
        reset_all()
    else:
        apply_profile(arg)
