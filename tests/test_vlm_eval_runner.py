import csv
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vlm_eval.results import init_csv
from vlm_eval.runner import build_tree_text, evaluate_screen


def write_png_header(path: Path, width: int, height: int) -> None:
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
    )


class VlmEvalRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.images_dir = self.root / "images"
        self.labels_dir = self.root / "labels"
        self.images_dir.mkdir()
        self.labels_dir.mkdir()
        self.results_csv = self.root / "results.csv"
        init_csv(self.results_csv)

        write_png_header(self.images_dir / "clock_baseline.png", 1080, 2274)
        labels = [{"text": "8:30 AM", "box": [84, 231, 429, 414]}]
        (self.labels_dir / "clock_baseline.json").write_text(
            json.dumps(labels),
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

    def read_result(self) -> dict:
        with self.results_csv.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))[0]

    @mock.patch("vlm_eval.runner.call_vlm", return_value="[215, 286]")
    def test_prompt_requests_pixel_coordinates_with_image_dimensions(self, call_vlm_mock):
        evaluate_screen(
            "test-model",
            "clock",
            0,
            self.results_csv,
            images_dir=self.images_dir,
            labels_dir=self.labels_dir,
            profiles=["baseline"],
        )

        prompt = call_vlm_mock.call_args.args[2]
        self.assertIn("This image is 1080 x 2274 pixels", prompt)
        self.assertIn("central pixel (x, y) coordinates", prompt)
        self.assertNotIn("Return your response", prompt)
        self.assertNotIn("0-1000", prompt)
        self.assertNotIn("Normalize", prompt)

    @mock.patch("vlm_eval.runner.call_vlm", return_value="[215, 286]")
    def test_pixel_response_is_scored_without_rescaling(self, call_vlm_mock):
        evaluate_screen(
            "test-model",
            "clock",
            0,
            self.results_csv,
            images_dir=self.images_dir,
            labels_dir=self.labels_dir,
            profiles=["baseline"],
        )

        row = self.read_result()
        self.assertEqual("215", row["x_pred"])
        self.assertEqual("286", row["y_pred"])
        self.assertEqual("1", row["score"])

    @mock.patch("vlm_eval.runner.call_vlm", return_value="no coordinate here")
    def test_unparsable_response_scores_miss(self, call_vlm_mock):
        evaluate_screen(
            "test-model",
            "clock",
            0,
            self.results_csv,
            images_dir=self.images_dir,
            labels_dir=self.labels_dir,
            profiles=["baseline"],
        )

        row = self.read_result()
        self.assertEqual("-1", row["x_pred"])
        self.assertEqual("-1", row["y_pred"])
        self.assertEqual("0", row["score"])
        self.assertEqual("no coordinate here", row["raw_response"])

    @mock.patch("vlm_eval.runner.call_vlm", return_value="[2000, 286]")
    def test_out_of_bounds_response_scores_miss(self, call_vlm_mock):
        evaluate_screen(
            "test-model",
            "clock",
            0,
            self.results_csv,
            images_dir=self.images_dir,
            labels_dir=self.labels_dir,
            profiles=["baseline"],
        )

        row = self.read_result()
        self.assertEqual("-1", row["x_pred"])
        self.assertEqual("-1", row["y_pred"])
        self.assertEqual("0", row["score"])


class BuildTreeTextTests(unittest.TestCase):
    LABELS = [
        {"text": "Wi-Fi", "box": [0, 0, 100, 50]},
        {"text": "Bluetooth", "box": [0, 60, 100, 110]},
        {"text": "", "content_desc": "Back", "box": [0, 120, 40, 160]},
    ]

    def test_includes_all_rows_without_exclusion(self):
        tree = build_tree_text(self.LABELS)
        self.assertIn('"Wi-Fi" [0,0][100,50]', tree)
        self.assertIn('"Bluetooth" [0,60][100,110]', tree)
        self.assertIn('"Back" [0,120][40,160]', tree)

    def test_excludes_target_row_to_avoid_leaking_bounds(self):
        tree = build_tree_text(self.LABELS, exclude_text="Bluetooth")
        # Target row (and its exact bounds) is withheld...
        self.assertNotIn("Bluetooth", tree)
        self.assertNotIn("[0,60][100,110]", tree)
        # ...but surrounding elements remain as spatial context.
        self.assertIn('"Wi-Fi" [0,0][100,50]', tree)
        self.assertIn('"Back" [0,120][40,160]', tree)

    @mock.patch("vlm_eval.runner.call_vlm", return_value="[50, 85]")
    def test_a11y_tree_prompt_withholds_target(self, call_vlm_mock):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        images_dir = root / "images"
        labels_dir = root / "labels"
        images_dir.mkdir()
        labels_dir.mkdir()
        results_csv = root / "results.csv"
        init_csv(results_csv)

        write_png_header(images_dir / "net_baseline.png", 1080, 2274)
        labels = [
            {"text": "Wi-Fi", "box": [0, 0, 100, 50]},
            {"text": "Bluetooth", "box": [0, 60, 100, 110]},
        ]
        (labels_dir / "net_baseline.json").write_text(
            json.dumps(labels), encoding="utf-8"
        )

        evaluate_screen(
            "test-model",
            "net",
            0,
            results_csv,
            images_dir=images_dir,
            labels_dir=labels_dir,
            profiles=["baseline"],
            use_a11y_tree=True,
        )

        prompt = call_vlm_mock.call_args.args[2]
        # The target's own bounds must not be handed to the model...
        self.assertNotIn("[0,60][100,110]", prompt)
        # ...while a neighbor stays as context, and the ask still names the target.
        self.assertIn('"Wi-Fi" [0,0][100,50]', prompt)
        self.assertIn("'Bluetooth'", prompt)


if __name__ == "__main__":
    unittest.main()
