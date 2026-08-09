import unittest

from collection.artifacts.diagnostics import (
    colour_only_contamination,
    drift_rate,
    loss_shape,
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


class ColourOnlyContaminationTests(unittest.TestCase):
    def test_identical_text_sets_pass(self):
        # A pure box shift (e.g. app content settling) with no text change
        # must not be flagged -- only a changed text SET is contamination.
        baseline = [label("Color", 0, 100), label("Colors", 0, 100, 60, 110)]
        shifted = [label("Color", 0, 100, 20, 70), label("Colors", 0, 100, 80, 130)]

        vanished, appeared = colour_only_contamination(baseline, shifted)

        self.assertEqual((set(), set()), (vanished, appeared))

    def test_vanished_label_is_flagged(self):
        # The settings_display case: 'Color'/'Colors' disappear under the
        # colour filter even though nothing about the profile should be able
        # to remove a layout element.
        baseline = [label("Brightness", 0, 100), label("Color", 0, 100, 60, 110),
                    label("Colors", 0, 100, 120, 170)]
        colorblind = [label("Brightness", 0, 100, 20, 70)]

        vanished, appeared = colour_only_contamination(baseline, colorblind)

        self.assertEqual({"Color", "Colors"}, vanished)
        self.assertEqual(set(), appeared)

    def test_empty_result_when_nothing_changed(self):
        labels = [label("Wi-Fi", 0, 100)]
        self.assertEqual((set(), set()), colour_only_contamination(labels, labels))


class LossShapeTests(unittest.TestCase):
    def test_no_loss_returns_none(self):
        labels = [label("A", 0, 10), label("B", 0, 10, 20, 30)]
        self.assertIsNone(loss_shape(labels, labels))

    def test_contiguous_tail_loss_is_detected(self):
        baseline = [label(t, 0, 10, i * 20, i * 20 + 10) for i, t in enumerate("ABCDE")]
        profile = baseline[:3]  # C, D, E scrolled off the bottom

        shape = loss_shape(baseline, profile)

        self.assertIsNotNone(shape)
        self.assertTrue(shape["is_tail"])
        self.assertEqual(2, shape["lost_count"])
        self.assertEqual([3, 4], shape["indices"])

    def test_scattered_loss_is_not_a_tail(self):
        baseline = [label(t, 0, 10, i * 20, i * 20 + 10) for i, t in enumerate("ABCDE")]
        profile = [baseline[0], baseline[2], baseline[4]]  # B and D vanished, not a tail

        shape = loss_shape(baseline, profile)

        self.assertIsNotNone(shape)
        self.assertFalse(shape["is_tail"])
        self.assertEqual([1, 3], shape["indices"])

    def test_losing_everything_is_still_a_tail(self):
        baseline = [label(t, 0, 10, i * 20, i * 20 + 10) for i, t in enumerate("AB")]
        shape = loss_shape(baseline, [])
        self.assertTrue(shape["is_tail"])


if __name__ == "__main__":
    unittest.main()
