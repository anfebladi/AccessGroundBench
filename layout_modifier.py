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

from adb_utils import capture_adb, get_device_serial, resolve_adb, run_adb


class ProfileVerificationError(RuntimeError):
    """Raised when an applied profile cannot be confirmed on the device.

    Collection must abort rather than continue: an unverified profile silently
    produces data that looks valid but measures the wrong condition. A previous
    run of this benchmark wrote an RTL setting key that Android never reads, and
    because nothing checked, an entire study's RTL arm turned out to be a plain
    font-and-density condition.
    """

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
    "elder_combo_mid": {
        "font_scale": "1.5",
        "density":    "480",
        "rtl":        "0",
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


# AOSP exposes the developer "Force RTL layout direction" toggle as
# Settings.Global.DEVELOPMENT_FORCE_RTL, whose string value is "debug.force_rtl".
# The Settings app writes BOTH the global setting and the matching system
# property, so we do the same -- writing only the setting is not enough to make
# the framework reflow.
#
# An earlier revision wrote "development_settings_force_rtl", which is not a key
# Android reads. Verified against the resulting captures: 0 of 68 off-centre
# elements mirrored. Hence verify_rtl_applied() below -- but even with the
# correct key, re-collection still measured 0% mirroring across every screen,
# so no ELDER_PROFILES entry requests rtl="1" anymore (the dropped arm,
# elder_combo_rtl, was renamed elder_combo_mid and is RTL-free). The reflow
# this key is meant to trigger likely needs a full app/process restart to
# take effect, which nothing in this pipeline currently does; a real fix
# would need that, not just the correct setting key.
RTL_SETTING_KEY = "debug.force_rtl"


def apply_rtl(adb: str, serial: str, value: str) -> None:
    """
    Vector 3 — Layout Reversal (RTL Mirroring).
    Injects the developer force-RTL global override flag (0 = off, 1 = on).
    """
    print(f"  [V3] RTL        -> {'ON' if value == '1' else 'OFF'}")
    _run(
        adb, serial,
        "shell", "settings", "put", "global", RTL_SETTING_KEY, value,
    )
    # The framework reads the system property; the setting alone does not
    # trigger a reflow. setprop can fail on locked-down images, so a failure
    # here is reported but left for verification to catch.
    try:
        _run(adb, serial, "shell", "setprop", RTL_SETTING_KEY, value)
    except subprocess.CalledProcessError as exc:
        print(f"  [WARN] setprop {RTL_SETTING_KEY} failed: {exc.stderr.strip()}")


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


def is_geometry_preserving(profile_name: str, baseline_name: str = "baseline") -> bool:
    """
    True when a profile changes no layout vector relative to baseline.

    font_scale, density, and rtl are the vectors that can move or remove an
    element; daltonizer is a display-level colour transform that cannot.
    A geometry-preserving profile's captured text set must therefore equal
    baseline's exactly -- see capture_checks.colour_only_contamination, which
    this drives so the check is never hand-maintained against a hardcoded
    profile name (currently `colorblind_deuteranomaly`, but this must keep
    working if a future colour-only profile is added or renamed).
    """
    profile = ELDER_PROFILES[profile_name]
    baseline = ELDER_PROFILES[baseline_name]
    return all(
        profile[vector] == baseline[vector]
        for vector in ("font_scale", "density", "rtl")
    )


# ---------------------------------------------------------------------------
# Post-condition Verification
#
# Every vector is read back from the device after it is applied. These check
# that the *setting* landed; the orchestrator additionally checks that the
# setting had the intended *visual* effect, because a setting can be accepted
# and still do nothing.
# ---------------------------------------------------------------------------

def _setting_value(adb: str, serial: str, namespace: str, key: str) -> str:
    """Read one Android setting, returning '' when unset."""
    raw = capture_adb(adb, serial, "shell", "settings", "get", namespace, key).strip()
    return "" if raw in ("null", "None") else raw


def verify_font_scale(adb: str, serial: str, expected: str) -> None:
    """Confirm font_scale reads back as requested."""
    actual = _setting_value(adb, serial, "system", "font_scale")
    # Android reports the default 1.0 as unset rather than "1.0".
    if not actual and float(expected) == 1.0:
        return
    if not actual or abs(float(actual) - float(expected)) > 1e-6:
        raise ProfileVerificationError(
            f"font_scale is {actual or 'unset'}, expected {expected}"
        )


def verify_density(adb: str, serial: str, expected: str) -> None:
    """Confirm the density override matches the profile (or is absent when reset)."""
    output = capture_adb(adb, serial, "shell", "wm", "density")
    override = None
    for line in output.splitlines():
        if "Override density:" in line:
            override = line.split(":", 1)[1].strip()

    if expected.lower() == "reset":
        if override is not None:
            raise ProfileVerificationError(
                f"density override is {override}, expected no override"
            )
        return

    if override != expected:
        raise ProfileVerificationError(
            f"density override is {override or 'none'}, expected {expected}"
        )


def verify_rtl_applied(adb: str, serial: str, expected: str) -> None:
    """
    Confirm the force-RTL flag landed in both the setting and the property.

    This checks only that the flag was written. Whether the layout actually
    mirrored is checked empirically by the orchestrator against the captured
    hierarchy, because writing an accepted-but-ignored key is exactly the
    failure mode this benchmark already suffered once.
    """
    setting = _setting_value(adb, serial, "global", RTL_SETTING_KEY)
    prop = capture_adb(adb, serial, "shell", "getprop", RTL_SETTING_KEY).strip()

    normalised_setting = setting or "0"
    normalised_prop = prop or "0"

    if normalised_setting != expected or normalised_prop != expected:
        raise ProfileVerificationError(
            f"force-RTL mismatch: setting={normalised_setting} "
            f"prop={normalised_prop}, expected {expected}"
        )


def verify_daltonizer(adb: str, serial: str, expected: str) -> None:
    """Confirm the on-device colour filter matches the profile."""
    enabled = _setting_value(
        adb, serial, "secure", "accessibility_display_daltonizer_enabled"
    )

    if expected == "off":
        if enabled == "1":
            raise ProfileVerificationError("daltonizer is enabled, expected off")
        return

    mode = _setting_value(adb, serial, "secure", "accessibility_display_daltonizer")
    want = DALTONIZER_MODES[expected]
    if enabled != "1" or mode != want:
        raise ProfileVerificationError(
            f"daltonizer is enabled={enabled or '0'} mode={mode or 'none'}, "
            f"expected enabled=1 mode={want} ({expected})"
        )


def verify_profile(adb: str, serial: str, profile_name: str) -> None:
    """Read every vector of a profile back from the device, raising on mismatch."""
    profile = ELDER_PROFILES[profile_name]
    print(f"\n[VERIFY] Confirming '{profile_name}' applied on device...")

    verify_font_scale(adb, serial, profile["font_scale"])
    verify_density(adb, serial, profile["density"])
    verify_rtl_applied(adb, serial, profile["rtl"])
    verify_daltonizer(adb, serial, profile["daltonizer"])

    print("[VERIFY] All four display vectors confirmed.")


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

def apply_profile(profile_name: str, verify: bool = True) -> None:
    """
    Apply a named accessibility profile to the active emulator.

    Steps:
      1. Validate the profile name against ELDER_PROFILES.
      2. Resolve ADB and detect the active device serial.
      3. Apply all four vectors sequentially.
      4. Block for SETTLE_DELAY seconds so the Android rendering loop
         finishes reflow before any downstream capture tool fires.
      5. Read every vector back from the device and raise if any did not land.

    Args:
        profile_name: Key into ELDER_PROFILES (e.g. "elder_combo_max").
        verify: Read the applied vectors back and raise
            ProfileVerificationError on mismatch. Only disable for offline
            testing -- collecting unverified data is how the RTL arm of an
            earlier run was silently invalidated.
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

    if verify:
        verify_profile(adb, serial, profile_name)

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
