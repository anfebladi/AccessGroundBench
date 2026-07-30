import unittest

from capture_checks import (
    CENTRE_EXCLUSION_PX,
    drift_rate,
    mirror_ratio,
    rtl_applied,
    text_boxes,
    text_drift,
)

SCREEN_WIDTH = 1000


def label(text: str, x1: int, x2: int, y1: int = 0, y2: int = 50) -> dict:
    return {"text": text, "box": [x1, y1, x2, y2]}


class TextBoxesTests(unittest.TestCase):
    def test_skips_empty_and_whitespace_text(self):
        labels = [label("Wi-Fi", 0, 100), label("", 0, 10), label("   ", 0, 10)]
        self.assertEqual({"Wi-Fi"}, set(text_boxes(labels)))

    def test_keeps_first_occurrence_of_duplicated_text(self):
        labels = [label("Save", 0, 100), label("Save", 500, 600)]
        self.assertEqual([0, 0, 100, 50], text_boxes(labels)["Save"])


class MirrorRatioTests(unittest.TestCase):
    def test_detects_a_fully_mirrored_layout(self):
        # An element centred at 100 should land at 900 once mirrored.
        reference = [label("Wi-Fi", 50, 150), label("Bluetooth", 50, 150, 60, 110)]
        mirrored = [label("Wi-Fi", 850, 950), label("Bluetooth", 850, 950, 60, 110)]

        self.assertEqual((2, 2), mirror_ratio(reference, mirrored, SCREEN_WIDTH))

    def test_detects_an_unmirrored_layout(self):
        # This is the archived RTL failure: identical positions, nothing moved.
        reference = [label("Wi-Fi", 50, 150)]
        unchanged = [label("Wi-Fi", 50, 150)]

        self.assertEqual((0, 1), mirror_ratio(reference, unchanged, SCREEN_WIDTH))

    def test_centred_elements_are_excluded_as_uninformative(self):
        # Mirroring maps a centred element onto itself, so it cannot tell a
        # mirrored layout apart from an unmirrored one.
        centred = SCREEN_WIDTH // 2
        reference = [label("Title", centred - 20, centred + 20)]
        unchanged = [label("Title", centred - 20, centred + 20)]

        self.assertEqual((0, 0), mirror_ratio(reference, unchanged, SCREEN_WIDTH))

    def test_element_just_outside_the_exclusion_band_is_counted(self):
        offset = CENTRE_EXCLUSION_PX + 30
        centre = SCREEN_WIDTH // 2 + offset
        reference = [label("Item", centre - 10, centre + 10)]
        mirrored_centre = SCREEN_WIDTH - centre
        mirrored = [label("Item", mirrored_centre - 10, mirrored_centre + 10)]

        self.assertEqual((1, 1), mirror_ratio(reference, mirrored, SCREEN_WIDTH))

    def test_only_shared_text_is_compared(self):
        reference = [label("Wi-Fi", 50, 150)]
        other = [label("Bluetooth", 850, 950)]

        self.assertEqual((0, 0), mirror_ratio(reference, other, SCREEN_WIDTH))


class RtlAppliedTests(unittest.TestCase):
    def test_passes_when_the_layout_mirrors(self):
        reference = [label("Wi-Fi", 50, 150), label("Data", 50, 150, 60, 110)]
        mirrored = [label("Wi-Fi", 850, 950), label("Data", 850, 950, 60, 110)]

        passed, detail = rtl_applied(reference, mirrored, SCREEN_WIDTH)
        self.assertTrue(passed)
        self.assertIn("2/2", detail)

    def test_fails_when_nothing_moved(self):
        reference = [label("Wi-Fi", 50, 150)]
        unchanged = [label("Wi-Fi", 50, 150)]

        passed, detail = rtl_applied(reference, unchanged, SCREEN_WIDTH)
        self.assertFalse(passed)
        self.assertIn("0/1", detail)

    def test_reports_inconclusive_rather_than_passing_with_no_evidence(self):
        passed, detail = rtl_applied([], [], SCREEN_WIDTH)
        self.assertFalse(passed)
        self.assertIn("no shared off-centre elements", detail)


class DriftTests(unittest.TestCase):
    def test_identical_captures_have_no_drift(self):
        labels = [label("Wi-Fi", 0, 100), label("Bluetooth", 0, 100, 60, 110)]
        self.assertEqual((set(), set()), text_drift(labels, labels))
        self.assertEqual(0.0, drift_rate(labels, labels))

    def test_reports_vanished_and_appeared_text(self):
        before = [label("Welcome Back", 0, 100), label("Install", 0, 100, 60, 110)]
        after = [label("Install", 0, 100, 60, 110), label("Ask Maps", 0, 100, 120, 170)]

        vanished, appeared = text_drift(before, after)
        self.assertEqual({"Welcome Back"}, vanished)
        self.assertEqual({"Ask Maps"}, appeared)

    def test_drift_rate_is_relative_to_the_first_capture(self):
        before = [label("A", 0, 10), label("B", 0, 10, 20, 30)]
        after = [label("A", 0, 10), label("C", 0, 10, 40, 50)]

        # One vanished (B) plus one appeared (C), over 2 baseline texts.
        self.assertEqual(1.0, drift_rate(before, after))

    def test_empty_baseline_has_no_drift(self):
        self.assertEqual(0.0, drift_rate([], [label("A", 0, 10)]))


if __name__ == "__main__":
    unittest.main()
