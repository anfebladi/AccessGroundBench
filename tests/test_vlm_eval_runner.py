import csv
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from evaluation.results import (
    STATUS_API_ERROR,
    STATUS_CO_PRESENT,
    STATUS_LABEL_CHANGED,
    STATUS_OFF_FRAME,
    STATUS_OFF_SCREEN,
    init_csv,
)
from evaluation.runner import (
    build_tree_text,
    collect_tree_rows,
    evaluate_screen,
    summarize_run,
)


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
        return self.read_results()[0]

    def read_results(self) -> list[dict]:
        with self.results_csv.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    @mock.patch("evaluation.runner.call_vlm", return_value="[215, 286]")
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

    @mock.patch("evaluation.runner.call_vlm", return_value="[215, 286]")
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

    @mock.patch("evaluation.runner.call_vlm", return_value="no coordinate here")
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

    @mock.patch("evaluation.runner.call_vlm", return_value="[2000, 286]")
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

    @mock.patch("evaluation.runner.call_vlm", return_value="[215, 286]")
    def test_absent_target_is_recorded_off_screen_without_querying_model(self, call_vlm_mock):
        # A target missing from the modified layout is a property of the layout,
        # not a grounding failure. It must not be scored 0, and the model must
        # not be asked -- scoring it as a miss is what inflated the original
        # results and penalised the most accurate models hardest.
        write_png_header(self.images_dir / "clock_elder_combo_max.png", 1080, 2274)
        (self.labels_dir / "clock_elder_combo_max.json").write_text(
            json.dumps([{"text": "Something else", "box": [0, 0, 50, 50]}]),
            encoding="utf-8",
        )

        evaluate_screen(
            "test-model",
            "clock",
            0,
            self.results_csv,
            images_dir=self.images_dir,
            labels_dir=self.labels_dir,
            profiles=["elder_combo_max"],
        )

        row = self.read_result()
        self.assertEqual(STATUS_OFF_SCREEN, row["status"])
        self.assertEqual("", row["score"])
        call_vlm_mock.assert_not_called()

    @mock.patch("evaluation.runner.call_vlm", return_value="[215, 286]")
    def test_relabeled_target_is_recorded_label_changed_without_querying_model(
        self, call_vlm_mock
    ):
        # The element is still on screen, but reflow changed its rendered
        # text enough that the exact lookup misses it. This must not be
        # folded into off_screen (the element didn't leave the layout) or
        # co_present (the model was never asked), and must not be scored.
        write_png_header(self.images_dir / "clock_elder_text_heavy.png", 1080, 2274)
        (self.labels_dir / "clock_elder_text_heavy.json").write_text(
            json.dumps([{"text": "8:30 AM​͏͏", "box": [90, 240, 430, 420]}]),
            encoding="utf-8",
        )

        evaluate_screen(
            "test-model",
            "clock",
            0,
            self.results_csv,
            images_dir=self.images_dir,
            labels_dir=self.labels_dir,
            profiles=["elder_text_heavy"],
        )

        row = self.read_result()
        self.assertEqual(STATUS_LABEL_CHANGED, row["status"])
        self.assertEqual("", row["score"])
        self.assertEqual("90", row["x_min"])
        self.assertIn("LABEL-CHANGED", row["raw_response"])
        call_vlm_mock.assert_not_called()

    @mock.patch("evaluation.runner.call_vlm", return_value="[215, 286]")
    def test_off_frame_box_is_recorded_without_querying_model(self, call_vlm_mock):
        # A box whose center falls outside the screenshot cannot be scored --
        # hit_test would compare against a point that isn't on the image.
        # The element is genuinely present (unlike off_screen), so it must
        # not be silently treated as a miss, and the model must not be asked
        # a question with no answerable point.
        write_png_header(self.images_dir / "clock_elder_combo_max.png", 1080, 2274)
        (self.labels_dir / "clock_elder_combo_max.json").write_text(
            json.dumps([{"text": "8:30 AM", "box": [90, 2200, 430, 2400]}]),
            encoding="utf-8",
        )

        evaluate_screen(
            "test-model",
            "clock",
            0,
            self.results_csv,
            images_dir=self.images_dir,
            labels_dir=self.labels_dir,
            profiles=["elder_combo_max"],
        )

        row = self.read_result()
        self.assertEqual(STATUS_OFF_FRAME, row["status"])
        self.assertEqual("", row["score"])
        self.assertEqual("2200", row["y_min"])
        call_vlm_mock.assert_not_called()

    @mock.patch("evaluation.runner.call_vlm", return_value="[215, 286]")
    def test_box_center_on_image_boundary_is_not_off_frame(self, call_vlm_mock):
        # A box whose center sits exactly at the image's bottom-right corner
        # is still a valid, answerable point -- the boundary check must be
        # inclusive (<=), not exclusive, or a legitimately edge-flush element
        # would be wrongly excluded.
        (self.labels_dir / "clock_baseline.json").write_text(
            json.dumps([{"text": "8:30 AM", "box": [1080, 2274, 1080, 2274]}]),
            encoding="utf-8",
        )

        evaluate_screen(
            "test-model", "clock", 0, self.results_csv,
            images_dir=self.images_dir, labels_dir=self.labels_dir,
            profiles=["baseline"],
        )

        row = self.read_result()
        self.assertNotEqual(STATUS_OFF_FRAME, row["status"])
        call_vlm_mock.assert_called_once()

    @mock.patch("evaluation.runner.call_vlm", return_value="[215, 286]")
    def test_present_target_is_marked_co_present(self, call_vlm_mock):
        evaluate_screen(
            "test-model", "clock", 0, self.results_csv,
            images_dir=self.images_dir, labels_dir=self.labels_dir,
            profiles=["baseline"],
        )

        self.assertEqual(STATUS_CO_PRESENT, self.read_result()["status"])

    @mock.patch("evaluation.runner.call_vlm", side_effect=RuntimeError("boom"))
    def test_api_error_is_recorded_without_a_score(self, call_vlm_mock):
        evaluate_screen(
            "test-model", "clock", 0, self.results_csv,
            images_dir=self.images_dir, labels_dir=self.labels_dir,
            profiles=["baseline"],
        )

        row = self.read_result()
        self.assertEqual(STATUS_API_ERROR, row["status"])
        self.assertEqual("", row["score"])

    @mock.patch(
        "evaluation.runner.call_vlm",
        side_effect=["[215, 286]", "[9000, 9000]", "[215, 286]"],
    )
    def test_majority_vote_across_trials(self, call_vlm_mock):
        evaluate_screen(
            "test-model", "clock", 0, self.results_csv,
            images_dir=self.images_dir, labels_dir=self.labels_dir,
            profiles=["baseline"], trials=3,
        )

        row = self.read_result()
        self.assertEqual(3, call_vlm_mock.call_count)
        self.assertEqual("1", row["score"], "2 of 3 hits should score a hit")
        self.assertEqual("101", row["trial_scores"])
        # The logged coordinates must come from a trial that agrees with the
        # majority, so the row is internally consistent.
        self.assertEqual("215", row["x_pred"])

    @mock.patch(
        "evaluation.runner.call_vlm",
        side_effect=["[215, 286]", "[9000, 9000]"],
    )
    def test_tied_trials_resolve_to_a_miss(self, call_vlm_mock):
        evaluate_screen(
            "test-model", "clock", 0, self.results_csv,
            images_dir=self.images_dir, labels_dir=self.labels_dir,
            profiles=["baseline"], trials=2,
        )

        self.assertEqual("0", self.read_result()["score"])

    @mock.patch("evaluation.runner.call_vlm", return_value="[215, 286]")
    def test_completed_keys_are_skipped(self, call_vlm_mock):
        evaluate_screen(
            "test-model", "clock", 0, self.results_csv,
            images_dir=self.images_dir, labels_dir=self.labels_dir,
            profiles=["baseline"],
            completed={("clock", "8:30 AM", "baseline")},
        )

        call_vlm_mock.assert_not_called()
        self.assertEqual([], self.read_results())

    @mock.patch(
        "evaluation.runner.call_vlm",
        side_effect=["[215, 286]", "[9000, 9000]", "[215, 286]"],
    )
    def test_summarize_run_reports_flip_rate(self, call_vlm_mock):
        evaluate_screen(
            "test-model", "clock", 0, self.results_csv,
            images_dir=self.images_dir, labels_dir=self.labels_dir,
            profiles=["baseline"], trials=3,
        )

        summary = summarize_run(self.results_csv)
        self.assertEqual({STATUS_CO_PRESENT: 1}, summary["statuses"])
        self.assertEqual(1.0, summary["flip_rate"])


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

    def test_excludes_target_reached_only_via_content_desc_fallback(self):
        # A node with empty text but content_desc == target still renders the
        # target's name once the label falls back -- excluding on `text` alone
        # let this through and leaked the target's bounds. Measured on the
        # archived dataset this affected 22 of 168 targets (13.1%), typically
        # a parent tab container whose bounds enclose the ground-truth box.
        labels = [
            {"text": "", "content_desc": "World Clock", "box": [216, 2051, 432, 2219]},
            {"text": "8:30 AM", "box": [84, 231, 429, 414]},
        ]

        tree = build_tree_text(labels, exclude_text="World Clock")

        self.assertNotIn("World Clock", tree)
        self.assertNotIn("[216,2051][432,2219]", tree)
        self.assertIn('"8:30 AM" [84,231][429,414]', tree)

    def test_excludes_target_reached_only_via_resource_id_fallback(self):
        labels = [
            {"text": "", "content_desc": "", "resource_id": "Settings", "box": [0, 0, 50, 50]},
        ]

        tree = build_tree_text(labels, exclude_text="Settings")

        self.assertEqual("", tree)

    def test_exclusion_does_not_match_on_partial_label(self):
        # A record whose rendered label merely contains the target text must
        # not be withheld -- only an exact match leaks the answer.
        labels = [{"text": "Wi-Fi settings", "box": [0, 0, 100, 50]}]

        tree = build_tree_text(labels, exclude_text="Wi-Fi")

        self.assertIn('"Wi-Fi settings" [0,0][100,50]', tree)

    @mock.patch("evaluation.runner.call_vlm", return_value="[50, 85]")
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

    def test_row_whose_centre_would_hit_is_withheld(self):
        # A parent container never renders the target's name, so the label
        # exclusion cannot catch it -- but its centre sits inside the
        # target's scoring box, so a model could score by reading the tree
        # instead of looking at the image. Measured at 67.4% of pairs before
        # this exclusion existed.
        target_box = [100, 100, 200, 140]
        labels = [
            {"text": "", "resource_id": "container", "box": [90, 90, 210, 150]},
            {"text": "Far Away", "box": [0, 900, 100, 950]},
        ]

        rows = collect_tree_rows(
            labels, exclude_text="Target",
            target_box=target_box, baseline_box=target_box,
        )

        labels_kept = [label for label, _box in rows]
        self.assertNotIn("container", labels_kept)
        self.assertIn("Far Away", labels_kept)

    def test_non_hitting_rows_are_kept_as_context(self):
        # The exclusion must be surgical: only rows that would actually score
        # are withheld, so the model keeps its spatial context (~3% cost).
        target_box = [100, 100, 200, 140]
        labels = [
            {"text": "Above", "box": [100, 0, 200, 40]},
            {"text": "Below", "box": [100, 900, 200, 940]},
        ]

        rows = collect_tree_rows(
            labels, exclude_text="Target",
            target_box=target_box, baseline_box=target_box,
        )

        self.assertEqual(["Above", "Below"], [label for label, _box in rows])

    def test_label_exclusion_still_fires_without_a_hitting_centre(self):
        # A row can render the target's name while sitting far away -- still
        # a leak (it confirms the label exists), so the label rule must not
        # be subsumed by the bounds rule.
        target_box = [100, 100, 200, 140]
        labels = [{"text": "Bluetooth", "box": [0, 900, 100, 950]}]

        rows = collect_tree_rows(
            labels, exclude_text="Bluetooth",
            target_box=target_box, baseline_box=target_box,
        )

        self.assertEqual([], rows)

    def test_bounds_exclusion_is_skipped_when_boxes_are_absent(self):
        # Backwards compatibility: non-tree callers pass no boxes and must
        # keep getting label-only exclusion behaviour.
        labels = [
            {"text": "", "resource_id": "container", "box": [90, 90, 210, 150]},
        ]

        rows = collect_tree_rows(labels, exclude_text="Target")

        self.assertEqual(["container"], [label for label, _box in rows])

    @mock.patch("evaluation.runner.call_vlm", return_value="[50, 85]")
    def test_evaluate_screen_withholds_hitting_rows_from_the_prompt(self, call_vlm_mock):
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
            {"text": "Bluetooth", "box": [100, 100, 200, 140]},
            # Encloses Bluetooth -- centre lands inside its scoring box.
            {"text": "", "resource_id": "row_container", "box": [90, 90, 210, 150]},
            {"text": "Wi-Fi", "box": [100, 900, 200, 940]},
        ]
        (labels_dir / "net_baseline.json").write_text(
            json.dumps(labels), encoding="utf-8"
        )

        evaluate_screen(
            "test-model", "net", 0, results_csv,
            images_dir=images_dir, labels_dir=labels_dir,
            profiles=["baseline"], use_a11y_tree=True,
        )

        prompts = [c.args[2] for c in call_vlm_mock.call_args_list]
        bluetooth_prompt = next(p for p in prompts if "'Bluetooth'" in p)
        self.assertNotIn("row_container", bluetooth_prompt)
        self.assertNotIn("[90,90][210,150]", bluetooth_prompt)
        self.assertIn("Wi-Fi", bluetooth_prompt)

    def test_collect_tree_rows_matches_build_tree_text_exclusion(self):
        # collect_tree_rows is build_tree_text's single source of truth for
        # the fallback/exclusion logic; every per-model rendering (e.g.
        # Ferret's) is built on its output, so the two must never diverge.
        labels = [
            {"text": "Wi-Fi", "box": [0, 0, 100, 50]},
            {"text": "Bluetooth", "box": [0, 60, 100, 110]},
            {"text": "", "content_desc": "Back", "box": [0, 120, 40, 160]},
        ]

        rows = collect_tree_rows(labels, exclude_text="Bluetooth")

        self.assertEqual(
            [("Wi-Fi", [0, 0, 100, 50]), ("Back", [0, 120, 40, 160])],
            rows,
        )

    @mock.patch("evaluation.runner.call_vlm", return_value="[50, 85]")
    def test_call_vlm_receives_structured_tree_rows_and_target_text(
        self, call_vlm_mock
    ):
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

        call_kwargs = call_vlm_mock.call_args.kwargs
        self.assertEqual("Bluetooth", call_kwargs["target_text"])
        self.assertEqual([("Wi-Fi", [0, 0, 100, 50])], call_kwargs["tree_rows"])
        self.assertEqual(1080, call_kwargs["img_width"])
        self.assertEqual(2274, call_kwargs["img_height"])

    @mock.patch("evaluation.runner.call_vlm", return_value="[50, 85]")
    def test_call_vlm_gets_none_tree_rows_in_vision_mode(self, call_vlm_mock):
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
        labels = [{"text": "Bluetooth", "box": [0, 60, 100, 110]}]
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
            use_a11y_tree=False,
        )

        call_kwargs = call_vlm_mock.call_args.kwargs
        self.assertEqual("Bluetooth", call_kwargs["target_text"])
        self.assertIsNone(call_kwargs["tree_rows"])


if __name__ == "__main__":
    unittest.main()
