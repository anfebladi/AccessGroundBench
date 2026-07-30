import unittest

from capture_checks import (
    drift_rate,
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


if __name__ == "__main__":
    unittest.main()
