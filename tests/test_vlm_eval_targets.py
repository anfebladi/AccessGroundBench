import json
import tempfile
import unittest
from pathlib import Path

from vlm_eval.targets import (
    MATCH_EXACT,
    MATCH_RELAXED,
    find_element_in_profile,
    harvest_targets,
    locate_element,
    normalize_label,
)


class VlmEvalTargetsTests(unittest.TestCase):
    def test_harvest_targets_reads_non_empty_baseline_text(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            labels_dir = Path(tmp_dir)
            label_path = labels_dir / "settings_main_baseline.json"
            label_path.write_text(
                json.dumps([
                    {"text": " Settings ", "box": [1, 2, 3, 4]},
                    {"text": "", "box": [5, 6, 7, 8]},
                    {"text": "   ", "box": [9, 10, 11, 12]},
                    {"text": "Network", "box": [13, 14, 15, 16]},
                ]),
                encoding="utf-8",
            )

            targets = harvest_targets("settings_main", labels_dir)

        self.assertEqual(
            [
                {"text": "Settings", "baseline_box": [1, 2, 3, 4]},
                {"text": "Network", "baseline_box": [13, 14, 15, 16]},
            ],
            targets,
        )

    def test_harvest_targets_returns_empty_for_missing_baseline(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            targets = harvest_targets("missing", Path(tmp_dir))

        self.assertEqual([], targets)

    def test_find_element_in_profile_matches_stripped_text(self):
        labels = [
            {"text": " Settings ", "box": [1, 2, 3, 4]},
            {"text": "Network", "box": [5, 6, 7, 8]},
        ]

        self.assertEqual([1, 2, 3, 4], find_element_in_profile(labels, "Settings"))
        self.assertIsNone(find_element_in_profile(labels, "Battery"))


class NormalizeLabelTests(unittest.TestCase):
    def test_collapses_internal_whitespace_runs(self):
        self.assertEqual("8:30 AM", normalize_label("8:30    AM"))

    def test_strips_non_breaking_and_narrow_no_break_space(self):
        # \xa0 (nbsp) and   (narrow no-break space, the one Android uses
        # in real clock/time labels) must compare equal to a plain space.
        self.assertEqual("8:30 AM", normalize_label("8:30 AM"))
        self.assertEqual("8:30 AM", normalize_label("8:30 AM"))

    def test_strips_zero_width_and_combining_joiner_padding(self):
        self.assertEqual(
            "Ship your first commit",
            normalize_label("Ship your first commit​͏͏"),
        )

    def test_does_not_casefold_or_strip_punctuation(self):
        # A genuine wording change must NOT be hidden by normalization --
        # only whitespace/invisible-character differences are collapsed.
        self.assertNotEqual(normalize_label("Color"), normalize_label("color"))
        self.assertNotEqual(normalize_label("Colors"), normalize_label("Color!"))

    def test_empty_and_none_input(self):
        self.assertEqual("", normalize_label(""))
        self.assertEqual("", normalize_label(None))


class LocateElementTests(unittest.TestCase):
    def test_exact_match_takes_priority_and_is_reported_as_exact(self):
        labels = [
            {"text": "Color", "box": [1, 2, 3, 4]},
            {"text": "Colors", "box": [5, 6, 7, 8]},
        ]

        result = locate_element(labels, "Color")

        self.assertEqual(([1, 2, 3, 4], "Color", MATCH_EXACT), result)

    def test_relaxed_match_on_whitespace_reflow(self):
        target = "Ship your first commit in 5 minutes."
        labels = [
            {"text": target + "͏͏͏͏͏", "box": [0, 0, 10, 10]},
        ]

        box, matched_text, kind = locate_element(labels, target)

        self.assertEqual([0, 0, 10, 10], box)
        self.assertEqual(MATCH_RELAXED, kind)
        self.assertTrue(matched_text.startswith(target))

    def test_relaxed_match_on_long_truncated_prefix(self):
        target = "Font size, display size, bold text, outline text, and more"
        truncated = target[:44]  # a real prefix, as reflow truncation produces
        self.assertGreater(len(truncated), 20)
        labels = [{"text": truncated, "box": [1, 1, 2, 2]}]

        result = locate_element(labels, target)

        self.assertIsNotNone(result)
        self.assertEqual(MATCH_RELAXED, result[2])

    def test_short_labels_do_not_spuriously_prefix_match(self):
        # "Color" is a genuine prefix of "Colors", but both are real,
        # independent targets (e.g. settings_display). Below
        # MIN_RELAXED_MATCH_CHARS, prefix matching must not fire, or a
        # target that is genuinely absent would resolve to an unrelated
        # short label that merely happens to share a prefix.
        labels = [{"text": "Colors", "box": [1, 2, 3, 4]}]

        self.assertIsNone(locate_element(labels, "Color"))

    def test_no_match_returns_none(self):
        labels = [{"text": "Network", "box": [1, 2, 3, 4]}]

        self.assertIsNone(locate_element(labels, "Battery"))

    def test_genuinely_absent_long_target_returns_none(self):
        # A long target with nothing even loosely resembling it in the
        # profile must not be coerced into matching something unrelated.
        labels = [{"text": "Compose", "box": [1, 2, 3, 4]}]
        target = "Unread, , , Claude Team, , Welcome to Claude Code, , Ship"

        self.assertIsNone(locate_element(labels, target))


if __name__ == "__main__":
    unittest.main()
