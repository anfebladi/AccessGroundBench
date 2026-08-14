import json
import tempfile
import unittest
from pathlib import Path

from evaluation.grounding.targets import (
    MATCH_EXACT,
    MATCH_RELAXED,
    MAX_TARGET_CHARS,
    PRIVACY_WITHHELD_TARGETS,
    box_contains,
    build_expected_keys,
    find_element_in_profile,
    harvest_targets,
    invalid_targets,
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

    def test_harvest_withholds_targets_that_name_a_real_person(self):
        """A withheld target is dropped as a question but kept as a tree row.

        The label node stays in the JSON on purpose: tree mode builds the
        accessibility tree for every *other* target on the screen from these
        same records, so deleting the node would change those prompts and make
        already-collected tree results irreproducible. Withholding therefore
        has to happen at harvest, and this pins that it does.
        """
        screen, withheld = next(iter(PRIVACY_WITHHELD_TARGETS.items()))
        withheld_text = next(iter(withheld))
        with tempfile.TemporaryDirectory() as tmp_dir:
            labels_dir = Path(tmp_dir)
            records = [
                {"text": withheld_text, "box": [1, 2, 3, 4]},
                {"text": "Your info", "box": [5, 6, 7, 8]},
            ]
            (labels_dir / f"{screen}_baseline.json").write_text(
                json.dumps(records), encoding="utf-8"
            )

            targets = harvest_targets(screen, labels_dir)

        self.assertEqual([{"text": "Your info", "baseline_box": [5, 6, 7, 8]}], targets)

    def test_harvest_withholding_is_scoped_to_its_own_screen(self):
        screen, withheld = next(iter(PRIVACY_WITHHELD_TARGETS.items()))
        withheld_text = next(iter(withheld))
        other_screen = "clock" if screen != "clock" else "dialer"
        with tempfile.TemporaryDirectory() as tmp_dir:
            labels_dir = Path(tmp_dir)
            (labels_dir / f"{other_screen}_baseline.json").write_text(
                json.dumps([{"text": withheld_text, "box": [1, 2, 3, 4]}]),
                encoding="utf-8",
            )

            targets = harvest_targets(other_screen, labels_dir)

        self.assertEqual([{"text": withheld_text, "baseline_box": [1, 2, 3, 4]}], targets)

    def test_harvest_targets_returns_empty_for_missing_baseline(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            targets = harvest_targets("missing", Path(tmp_dir))

        self.assertEqual([], targets)

    def test_harvest_targets_excludes_row_containers_and_long_text(self):
        long_text = "x" * (MAX_TARGET_CHARS + 1)
        with tempfile.TemporaryDirectory() as tmp_dir:
            labels_dir = Path(tmp_dir)
            label_path = labels_dir / "gmail_baseline.json"
            label_path.write_text(
                json.dumps([
                    # Row container: encloses "Sender" below, and is itself
                    # short enough to survive the length rule alone.
                    {"text": "container", "box": [0, 0, 100, 100]},
                    {"text": "Sender", "box": [10, 10, 50, 50]},
                    {"text": long_text, "box": [200, 200, 210, 210]},
                    {"text": "Compose", "box": [300, 300, 320, 320]},
                ]),
                encoding="utf-8",
            )

            targets = harvest_targets("gmail", labels_dir)

        self.assertEqual(
            {"Sender", "Compose"},
            {t["text"] for t in targets},
        )

    def test_find_element_in_profile_matches_stripped_text(self):
        labels = [
            {"text": " Settings ", "box": [1, 2, 3, 4]},
            {"text": "Network", "box": [5, 6, 7, 8]},
        ]

        self.assertEqual([1, 2, 3, 4], find_element_in_profile(labels, "Settings"))
        self.assertIsNone(find_element_in_profile(labels, "Battery"))


class BoxContainsTests(unittest.TestCase):
    def test_outer_box_contains_inner_box(self):
        self.assertTrue(box_contains([0, 0, 100, 100], [10, 10, 50, 50]))

    def test_identical_boxes_do_not_contain_each_other(self):
        self.assertFalse(box_contains([0, 0, 100, 100], [0, 0, 100, 100]))

    def test_partially_overlapping_boxes_do_not_contain(self):
        self.assertFalse(box_contains([0, 0, 50, 50], [25, 25, 75, 75]))

    def test_disjoint_boxes_do_not_contain(self):
        self.assertFalse(box_contains([0, 0, 10, 10], [100, 100, 110, 110]))


class InvalidTargetsTests(unittest.TestCase):
    def test_over_cap_text_is_excluded(self):
        long_text = "x" * (MAX_TARGET_CHARS + 1)
        candidates = [{"text": long_text, "baseline_box": [0, 0, 10, 10]}]

        self.assertEqual({long_text}, invalid_targets(candidates))

    def test_text_at_the_cap_is_kept(self):
        exact_text = "x" * MAX_TARGET_CHARS
        candidates = [{"text": exact_text, "baseline_box": [0, 0, 10, 10]}]

        self.assertEqual(set(), invalid_targets(candidates))

    def test_container_enclosing_another_target_is_excluded(self):
        candidates = [
            {"text": "container", "baseline_box": [0, 0, 100, 100]},
            {"text": "child", "baseline_box": [10, 10, 50, 50]},
        ]

        self.assertEqual({"container"}, invalid_targets(candidates))

    def test_short_unique_label_is_kept(self):
        candidates = [
            {"text": "Home", "baseline_box": [0, 0, 20, 20]},
            {"text": "Back", "baseline_box": [30, 30, 50, 50]},
        ]

        self.assertEqual(set(), invalid_targets(candidates))


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


class BuildExpectedKeysTests(unittest.TestCase):
    def test_orders_screen_then_profile_then_target(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            labels_dir = Path(tmp_dir)
            (labels_dir / "clock_baseline.json").write_text(
                json.dumps([
                    {"text": "Timer", "box": [1, 2, 3, 4]},
                    {"text": "Alarm", "box": [5, 6, 7, 8]},
                ]),
                encoding="utf-8",
            )
            (labels_dir / "dialer_baseline.json").write_text(
                json.dumps([{"text": "Call", "box": [1, 2, 3, 4]}]),
                encoding="utf-8",
            )

            keys = build_expected_keys(
                ["clock", "dialer"], labels_dir, ["baseline", "elder_text_heavy"]
            )

        self.assertEqual(
            [
                ("clock", "Timer", "baseline"),
                ("clock", "Alarm", "baseline"),
                ("clock", "Timer", "elder_text_heavy"),
                ("clock", "Alarm", "elder_text_heavy"),
                ("dialer", "Call", "baseline"),
                ("dialer", "Call", "elder_text_heavy"),
            ],
            keys,
        )

    def test_excludes_targets_invalid_targets_would_drop(self):
        # build_expected_keys must reflect the same harvest that runs at
        # collection time, including the invalid_targets filter -- otherwise
        # the "expected" set it hands to prepare_csv/finalize_csv would
        # itself contain the stale targets those are meant to catch.
        with tempfile.TemporaryDirectory() as tmp_dir:
            labels_dir = Path(tmp_dir)
            (labels_dir / "gmail_baseline.json").write_text(
                json.dumps([{"text": "x" * (MAX_TARGET_CHARS + 1), "box": [1, 2, 3, 4]}]),
                encoding="utf-8",
            )

            keys = build_expected_keys(["gmail"], labels_dir, ["baseline"])

        self.assertEqual([], keys)


if __name__ == "__main__":
    unittest.main()
