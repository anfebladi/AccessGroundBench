import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from evaluation.smoke import smoke_test_model


def write_png_header(path: Path, width: int, height: int) -> None:
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
    )


class SmokeTestModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.images_dir = self.root / "images"
        self.labels_dir = self.root / "labels"
        self.images_dir.mkdir()
        self.labels_dir.mkdir()

        # 1080x2274 (real screenshot dimensions) with a box whose y exceeds
        # 1000 -- deliberately outside the 0-1000 normalized range, so a
        # pixel reply near the box is unambiguously pixel-space rather than
        # coincidentally also passing as normalized (see the classifier's
        # documented ambiguity for values that happen to land in 0-1000).
        write_png_header(self.images_dir / "clock_baseline.png", 1080, 2274)
        labels = [{"text": "8:30 AM", "box": [600, 1400, 800, 1600]}]
        (self.labels_dir / "clock_baseline.json").write_text(
            json.dumps(labels), encoding="utf-8",
        )
        self.addCleanup(self.tmp_dir.cleanup)

    @mock.patch("evaluation.smoke.call_vlm", return_value="[700, 1500]")
    def test_pixel_reply_hits_and_reports_no_mismatch(self, call_vlm_mock):
        result = smoke_test_model(
            "openai/gpt-4o-mini", "clock",
            images_dir=self.images_dir, labels_dir=self.labels_dir,
            coord_space="pixel",
        )

        self.assertTrue(result.ok)
        self.assertEqual(1, result.hit)
        self.assertEqual((700.0, 1500.0), (result.x_pred, result.y_pred))
        self.assertFalse(result.coord_space_mismatch)
        call_vlm_mock.assert_called_once()

    @mock.patch("evaluation.smoke.call_vlm", return_value="[500, 500]")
    def test_normalized_reply_flagged_as_mismatch_when_expected_pixel(self, call_vlm_mock):
        # An unrecognised normalized model (not in the gemini/qwen/glm
        # family match) answering on a 0-1000 grid with coord_space=pixel
        # would otherwise silently score near the top-left corner -- this is
        # exactly the failure mode the smoke test exists to catch before a
        # full paid run.
        result = smoke_test_model(
            "openai/my-custom-vlm", "clock",
            images_dir=self.images_dir, labels_dir=self.labels_dir,
            coord_space="pixel",
        )

        self.assertTrue(result.ok)
        self.assertEqual("normalized", result.coord_space_detected)
        self.assertTrue(result.coord_space_mismatch)

    @mock.patch("evaluation.smoke.call_vlm", side_effect=RuntimeError("missing API key"))
    def test_call_failure_is_reported_not_raised(self, call_vlm_mock):
        result = smoke_test_model(
            "openai/gpt-4o-mini", "clock",
            images_dir=self.images_dir, labels_dir=self.labels_dir,
        )

        self.assertFalse(result.ok)
        self.assertIn("missing API key", result.error)

    def test_missing_image_reports_a_clear_error_without_calling_the_model(self):
        result = smoke_test_model(
            "openai/gpt-4o-mini", "nonexistent_screen",
            images_dir=self.images_dir, labels_dir=self.labels_dir,
        )

        self.assertFalse(result.ok)
        self.assertIn("Missing image", result.error)

    @mock.patch("evaluation.smoke.call_vlm", return_value="[9999, 9999]")
    def test_out_of_frame_prediction_has_no_hit_verdict(self, call_vlm_mock):
        result = smoke_test_model(
            "openai/gpt-4o-mini", "clock",
            images_dir=self.images_dir, labels_dir=self.labels_dir,
            coord_space="pixel",
        )

        self.assertTrue(result.ok)
        self.assertIsNone(result.hit)


if __name__ == "__main__":
    unittest.main()
