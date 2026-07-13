import csv
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vlm_eval.results import init_csv
from vlm_eval.runner import evaluate_screen


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


if __name__ == "__main__":
    unittest.main()
