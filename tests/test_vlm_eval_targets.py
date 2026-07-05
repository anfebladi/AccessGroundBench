import json
import tempfile
import unittest
from pathlib import Path

from vlm_eval.targets import find_element_in_profile, harvest_targets


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
                {"text": "Settings", "box": [1, 2, 3, 4]},
                {"text": "Network", "box": [13, 14, 15, 16]},
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


if __name__ == "__main__":
    unittest.main()
