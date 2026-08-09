import unittest
from unittest import mock

from collection.runtime import profiles as lm


class FontScaleVerificationTests(unittest.TestCase):
    def verify(self, reported: str, expected: str) -> None:
        with mock.patch.object(lm, "capture_adb", return_value=reported):
            lm.verify_font_scale("adb", "emulator-5554", expected)

    def test_matching_scale_passes(self):
        self.verify("1.4", "1.4")

    def test_unset_scale_counts_as_the_default(self):
        # Android reports the default 1.0 as "null" rather than "1.0".
        self.verify("null", "1.0")

    def test_mismatch_raises(self):
        with self.assertRaises(lm.ProfileVerificationError):
            self.verify("1.0", "1.6")

    def test_unset_scale_is_not_accepted_for_a_scaled_profile(self):
        with self.assertRaises(lm.ProfileVerificationError):
            self.verify("null", "1.4")


class DensityVerificationTests(unittest.TestCase):
    OVERRIDDEN = "Physical density: 420\nOverride density: 480\n"
    PHYSICAL_ONLY = "Physical density: 420\n"

    def verify(self, reported: str, expected: str) -> None:
        with mock.patch.object(lm, "capture_adb", return_value=reported):
            lm.verify_density("adb", "emulator-5554", expected)

    def test_matching_override_passes(self):
        self.verify(self.OVERRIDDEN, "480")

    def test_reset_requires_no_override(self):
        self.verify(self.PHYSICAL_ONLY, "reset")

    def test_reset_fails_when_an_override_lingers(self):
        with self.assertRaises(lm.ProfileVerificationError):
            self.verify(self.OVERRIDDEN, "reset")

    def test_wrong_override_raises(self):
        with self.assertRaises(lm.ProfileVerificationError):
            self.verify(self.OVERRIDDEN, "520")

    def test_missing_override_raises_when_one_is_expected(self):
        with self.assertRaises(lm.ProfileVerificationError):
            self.verify(self.PHYSICAL_ONLY, "480")


class RtlVerificationTests(unittest.TestCase):
    def verify(self, setting: str, prop: str, expected: str) -> None:
        # capture_adb serves the setting read first, then the getprop read.
        with mock.patch.object(lm, "capture_adb", side_effect=[setting, prop]):
            lm.verify_rtl_applied("adb", "emulator-5554", expected)

    def test_both_flags_set_passes(self):
        self.verify("1", "1", "1")

    def test_both_flags_unset_passes_when_rtl_is_off(self):
        self.verify("null", "", "0")

    def test_setting_written_but_property_missing_raises(self):
        # The exact failure that invalidated the archived RTL arm: the write is
        # accepted, but the framework never reflows.
        with self.assertRaises(lm.ProfileVerificationError):
            self.verify("1", "", "1")

    def test_flag_not_set_at_all_raises(self):
        with self.assertRaises(lm.ProfileVerificationError):
            self.verify("null", "", "1")

    def test_uses_the_key_android_actually_reads(self):
        self.assertEqual("debug.force_rtl", lm.RTL_SETTING_KEY)


class DaltonizerVerificationTests(unittest.TestCase):
    def verify(self, reads: list[str], expected: str) -> None:
        with mock.patch.object(lm, "capture_adb", side_effect=reads):
            lm.verify_daltonizer("adb", "emulator-5554", expected)

    def test_off_passes_when_disabled(self):
        self.verify(["0"], "off")

    def test_off_raises_when_still_enabled(self):
        with self.assertRaises(lm.ProfileVerificationError):
            self.verify(["1"], "off")

    def test_enabled_mode_passes(self):
        self.verify(["1", lm.DALTONIZER_MODES["deuteranomaly"]], "deuteranomaly")

    def test_wrong_mode_raises(self):
        with self.assertRaises(lm.ProfileVerificationError):
            self.verify(["1", lm.DALTONIZER_MODES["protanomaly"]], "deuteranomaly")

    def test_correct_mode_but_disabled_raises(self):
        with self.assertRaises(lm.ProfileVerificationError):
            self.verify(["0", lm.DALTONIZER_MODES["deuteranomaly"]], "deuteranomaly")


class ApplyDaltonizerTests(unittest.TestCase):
    def test_off_writes_enabled_zero(self):
        with mock.patch.object(lm, "run_adb") as run_adb_mock:
            lm.apply_daltonizer("adb", "emulator-5554", "off")

        run_adb_mock.assert_called_once_with(
            "adb", "emulator-5554", "shell", "settings", "put", "secure",
            "accessibility_display_daltonizer_enabled", "0",
        )

    def test_enabled_mode_writes_both_enabled_and_mode(self):
        with mock.patch.object(lm, "run_adb") as run_adb_mock:
            lm.apply_daltonizer("adb", "emulator-5554", "deuteranomaly")

        calls = [c.args for c in run_adb_mock.call_args_list]
        self.assertIn(
            ("adb", "emulator-5554", "shell", "settings", "put", "secure",
             "accessibility_display_daltonizer_enabled", "1"),
            calls,
        )
        self.assertIn(
            ("adb", "emulator-5554", "shell", "settings", "put", "secure",
             "accessibility_display_daltonizer", lm.DALTONIZER_MODES["deuteranomaly"]),
            calls,
        )


class DaltonizerTeardownTests(unittest.TestCase):
    """
    Regression coverage from investigating settings_display's baseline_close
    drift (the missing 'Color'/'Colors' rows). That drift was suspected to be
    a daltonizer-teardown leak in this module -- it is not: comparing raw
    (uncropped) XML bounds shows every element shifts by an identical 323px
    between baseline and colorblind_deuteranomaly, with image dimensions
    unchanged, which rules out a crop-offset artifact and points to a
    persistent Settings-app UI side effect of toggling an accessibility
    setting out-of-band via ADB (the same category as the already-documented
    RTL reflow issue) -- not a value that failed to reset. These tests lock
    in that the setting-level teardown is, and remains, correct.
    """

    def test_apply_profile_baseline_turns_daltonizer_off(self):
        with mock.patch.object(lm, "resolve_adb", return_value="adb"), \
             mock.patch.object(lm, "get_device_serial", return_value="emulator-5554"), \
             mock.patch.object(lm, "run_adb") as run_adb_mock, \
             mock.patch.object(lm, "capture_adb", return_value=""), \
             mock.patch.object(lm.time, "sleep"):
            lm.apply_profile("baseline")

        calls = [c.args for c in run_adb_mock.call_args_list]
        self.assertIn(
            ("adb", "emulator-5554", "shell", "settings", "put", "secure",
             "accessibility_display_daltonizer_enabled", "0"),
            calls,
        )

    def test_reset_all_turns_daltonizer_off(self):
        with mock.patch.object(lm, "run_adb") as run_adb_mock:
            lm.reset_all("adb", "emulator-5554")

        calls = [c.args for c in run_adb_mock.call_args_list]
        self.assertIn(
            ("adb", "emulator-5554", "shell", "settings", "put", "secure",
             "accessibility_display_daltonizer_enabled", "0"),
            calls,
        )

    def test_applying_baseline_after_colorblind_still_turns_daltonizer_off(self):
        # The exact sequence the orchestrator runs for every screen:
        # colorblind_deuteranomaly immediately followed by the baseline
        # profile for the closing drift probe. The teardown write must not
        # depend on, or be skipped because of, the daltonizer's prior state.
        with mock.patch.object(lm, "resolve_adb", return_value="adb"), \
             mock.patch.object(lm, "get_device_serial", return_value="emulator-5554"), \
             mock.patch.object(lm, "run_adb") as run_adb_mock, \
             mock.patch.object(lm, "capture_adb", return_value=""), \
             mock.patch.object(lm.time, "sleep"):
            # Simulate the daltonizer being left on from the immediately
            # preceding colorblind_deuteranomaly capture.
            lm.apply_daltonizer("adb", "emulator-5554", "deuteranomaly")
            run_adb_mock.reset_mock()

            lm.apply_profile("baseline")

        calls = [c.args for c in run_adb_mock.call_args_list]
        self.assertIn(
            ("adb", "emulator-5554", "shell", "settings", "put", "secure",
             "accessibility_display_daltonizer_enabled", "0"),
            calls,
        )


class ProfileMatrixTests(unittest.TestCase):
    def test_every_profile_declares_all_four_vectors(self):
        for name, profile in lm.ELDER_PROFILES.items():
            for vector in ("font_scale", "density", "rtl", "daltonizer"):
                self.assertIn(vector, profile, f"{name} is missing {vector}")

    def test_colorblind_profile_isolates_the_colour_vector(self):
        # Geometry must match baseline so colour is the only difference.
        baseline = lm.ELDER_PROFILES["baseline"]
        colourblind = lm.ELDER_PROFILES["colorblind_deuteranomaly"]
        for vector in ("font_scale", "density", "rtl"):
            self.assertEqual(baseline[vector], colourblind[vector])
        self.assertNotEqual(baseline["daltonizer"], colourblind["daltonizer"])


class IsGeometryPreservingTests(unittest.TestCase):
    def test_colorblind_is_geometry_preserving(self):
        self.assertTrue(lm.is_geometry_preserving("colorblind_deuteranomaly"))

    def test_baseline_is_trivially_geometry_preserving(self):
        self.assertTrue(lm.is_geometry_preserving("baseline"))

    def test_font_scaling_profiles_are_not_geometry_preserving(self):
        for name in ("elder_text_heavy", "elder_zoom_heavy",
                     "elder_combo_max", "elder_combo_mid"):
            self.assertFalse(
                lm.is_geometry_preserving(name),
                f"{name} changes font_scale or density and must not read as "
                "geometry-preserving",
            )

    def test_driven_by_elder_profiles_not_hardcoded(self):
        # If a future colour-only profile is added under a different name,
        # this must recognise it without the function itself changing --
        # the whole point of B0 is that the check is mechanical, not a
        # hardcoded profile-name comparison.
        original = dict(lm.ELDER_PROFILES)
        try:
            lm.ELDER_PROFILES["colorblind_protanomaly"] = {
                "font_scale": "1.0", "density": "reset", "rtl": "0",
                "daltonizer": "protanomaly",
            }
            self.assertTrue(lm.is_geometry_preserving("colorblind_protanomaly"))
        finally:
            lm.ELDER_PROFILES.clear()
            lm.ELDER_PROFILES.update(original)


if __name__ == "__main__":
    unittest.main()
