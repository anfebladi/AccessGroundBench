import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import paths
from collection import cli as collection_cli
from collection.runtime import profiles as layout_modifier
from collection.artifacts import manifest as collection_manifest
from collection import workflow


def sequence_profiles() -> list[str]:
    experimental = [p for p in layout_modifier.ELDER_PROFILES if p != "baseline"]
    return ["baseline", *experimental, collection_manifest.DRIFT_PROBE]


def make_entry(screen: str, profile: str, ok: bool = True, label_count: int = 1) -> dict:
    stem = f"{screen}_{profile}"
    entry = {"screen": screen, "profile": profile, "stem": stem, "ok": ok}
    if ok:
        entry.update({
            "png": f"{stem}.png", "xml": f"{stem}.xml", "labels": f"{stem}.json",
            "label_count": label_count,
        })
    else:
        entry["error"] = "navigation failed"
    return entry


def full_entries(screen: str) -> list[dict]:
    return [make_entry(screen, p) for p in sequence_profiles()]


class OrchestratorPathsTestCase(unittest.TestCase):
    """Patches orchestrator's module-level path constants to a temp dir."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.images_dir = root / "images"
        self.raw_xml_dir = root / "raw_xml"
        self.labels_dir = root / "labels"
        self.manifest_path = root / "collection_manifest.json"
        for d in (self.images_dir, self.raw_xml_dir, self.labels_dir):
            d.mkdir(parents=True)

        patches = [
            mock.patch.object(paths, "images_dir", return_value=self.images_dir),
            mock.patch.object(paths, "raw_xml_dir", return_value=self.raw_xml_dir),
            mock.patch.object(paths, "labels_dir", return_value=self.labels_dir),
            mock.patch.object(paths, "manifest_path", return_value=self.manifest_path),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def read_manifest(self) -> dict:
        with open(self.manifest_path, encoding="utf-8") as f:
            return json.load(f)


class WriteManifestMergeTests(OrchestratorPathsTestCase):
    def test_first_write_creates_a_fresh_manifest(self):
        problems = collection_manifest.write_manifest(
            ["clock"], full_entries("clock"), []
        )

        self.assertEqual([], problems)
        manifest = self.read_manifest()
        self.assertEqual(["clock"], list(manifest["screens"]))

    def test_second_run_preserves_screens_it_did_not_touch(self):
        collection_manifest.write_manifest(["clock"], full_entries("clock"), [])

        collection_manifest.write_manifest(["dialer"], full_entries("dialer"), [])

        manifest = self.read_manifest()
        self.assertEqual({"clock", "dialer"}, set(manifest["screens"]))
        # clock's record must be untouched by the dialer-only run.
        self.assertEqual(
            [f"clock_{p}" for p in sequence_profiles()],
            [e["stem"] for e in manifest["screens"]["clock"]["captures"]],
        )

    def test_subset_run_warns_about_screens_it_did_not_touch(self):
        collection_manifest.write_manifest(["clock", "dialer"], full_entries("clock") + full_entries("dialer"), [])

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            collection_manifest.write_manifest(["clock"], full_entries("clock"), [])

        output = buf.getvalue()
        self.assertIn("WARN", output)
        self.assertIn("dialer", output)

    def test_no_warning_when_this_run_covers_everything_on_disk(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            collection_manifest.write_manifest(["clock"], full_entries("clock"), [])

        self.assertNotIn("WARN", buf.getvalue())

    def test_recapturing_a_screen_replaces_its_own_record(self):
        collection_manifest.write_manifest(["clock"], full_entries("clock"), [])

        stale_entries = full_entries("clock")
        stale_entries[0]["ok"] = False
        stale_entries[0].pop("label_count", None)
        stale_entries[0]["error"] = "navigation failed"
        collection_manifest.write_manifest(["clock"], stale_entries, [])

        manifest = self.read_manifest()
        self.assertFalse(manifest["screens"]["clock"]["captures"][0]["ok"])

    def test_old_flat_schema_manifest_is_treated_as_empty(self):
        self.manifest_path.write_text(
            json.dumps({
                "collected_at": "2026-01-01T00:00:00+00:00",
                "screens": ["clock"],
                "captures": [],
                "drift": [],
                "problems": [],
            }),
            encoding="utf-8",
        )

        collection_manifest.write_manifest(["dialer"], full_entries("dialer"), [])

        manifest = self.read_manifest()
        # Only dialer is present -- the old-schema "clock" entry had nothing
        # per-screen to carry forward, so it is not resurrected.
        self.assertEqual(["dialer"], list(manifest["screens"]))

    def test_expected_and_successful_totals_are_across_the_full_manifest(self):
        collection_manifest.write_manifest(["clock"], full_entries("clock"), [])
        collection_manifest.write_manifest(["dialer"], full_entries("dialer"), [])

        manifest = self.read_manifest()
        self.assertEqual(2 * collection_manifest.PER_SCREEN_EXPECTED, manifest["expected_captures"])
        self.assertEqual(2 * collection_manifest.PER_SCREEN_EXPECTED, manifest["successful_captures"])

    def test_reconstructed_flag_is_recorded_per_screen(self):
        collection_manifest.write_manifest(["clock"], full_entries("clock"), [], reconstructed=True)

        manifest = self.read_manifest()
        self.assertTrue(manifest["screens"]["clock"]["reconstructed"])


class ContaminationAndDiagnosticsTestCase(OrchestratorPathsTestCase):
    """Base for tests needing real label JSON on disk (not just entry dicts)."""

    def write_labels(self, screen: str, profile: str, texts: list[str]) -> dict:
        stem = f"{screen}_{profile}"
        path = self.labels_dir / f"{stem}.json"
        path.write_text(
            json.dumps([
                {"text": t, "box": [0, i * 60, 100, i * 60 + 50]}
                for i, t in enumerate(texts)
            ]),
            encoding="utf-8",
        )
        return {"screen": screen, "profile": profile, "stem": stem, "ok": True,
                "labels": str(path), "label_count": len(texts)}


class ContaminationProblemsTests(ContaminationAndDiagnosticsTestCase):
    def test_clean_colour_profile_has_no_problems(self):
        captures = [
            self.write_labels("settings_display", "baseline", ["Brightness", "Color"]),
            self.write_labels("settings_display", "colorblind_deuteranomaly",
                               ["Brightness", "Color"]),
        ]

        problems = collection_manifest.contamination_problems("settings_display", captures)

        self.assertEqual([], problems)

    def test_vanished_text_under_colour_profile_is_flagged(self):
        captures = [
            self.write_labels("settings_display", "baseline",
                               ["Brightness", "Color", "Colors"]),
            self.write_labels("settings_display", "colorblind_deuteranomaly",
                               ["Brightness"]),
        ]

        problems = collection_manifest.contamination_problems("settings_display", captures)

        self.assertEqual(1, len(problems))
        self.assertIn("colour-only contamination", problems[0])
        self.assertIn("settings_display/colorblind_deuteranomaly", problems[0])

    def test_geometry_changing_profile_is_not_checked(self):
        # elder_text_heavy changes font_scale, so losing a tail of texts is
        # ordinary scroll-off, not contamination -- this check must skip it
        # entirely (drift/scroll-off has its own, separate handling).
        captures = [
            self.write_labels("clock", "baseline", ["Alarm", "8:30 AM", "Timer"]),
            self.write_labels("clock", "elder_text_heavy", ["Alarm", "8:30 AM"]),
        ]

        problems = collection_manifest.contamination_problems("clock", captures)

        self.assertEqual([], problems)

    def test_missing_baseline_capture_produces_no_problems_here(self):
        # That gap is reported by the missing-capture check; this function
        # has nothing to compare against and must not crash.
        captures = [
            self.write_labels("clock", "colorblind_deuteranomaly", ["Alarm"]),
        ]

        problems = collection_manifest.contamination_problems("clock", captures)

        self.assertEqual([], problems)

    def test_stem_not_profile_disambiguates_the_drift_probe(self):
        # capture_one stamps the drift probe's entry with profile="baseline"
        # (it applies the baseline profile) even though its stem is
        # "..._baseline_close". A profile-keyed lookup would collide the two
        # baseline entries; contamination_problems must not do that.
        baseline = self.write_labels("clock", "baseline", ["Alarm", "8:30 AM"])
        probe = self.write_labels("clock", "baseline_close", ["Alarm", "8:30 AM"])
        probe["profile"] = "baseline"  # as the real pipeline stamps it
        colourblind = self.write_labels("clock", "colorblind_deuteranomaly",
                                         ["Alarm", "8:30 AM"])

        problems = collection_manifest.contamination_problems(
            "clock", [baseline, probe, colourblind]
        )

        self.assertEqual([], problems)


class ShapeDiagnosticsTests(ContaminationAndDiagnosticsTestCase):
    def test_tail_loss_produces_no_diagnostic(self):
        captures = [
            self.write_labels("clock", "baseline", ["A", "B", "C", "D"]),
            self.write_labels("clock", "elder_text_heavy", ["A", "B"]),
        ]

        notes = collection_manifest.shape_diagnostics("clock", captures)

        self.assertEqual([], notes)

    def test_scattered_loss_produces_a_diagnostic(self):
        captures = [
            self.write_labels("gmail", "baseline", ["A", "B", "C", "D"]),
            self.write_labels("gmail", "elder_text_heavy", ["A", "C"]),
        ]

        notes = collection_manifest.shape_diagnostics("gmail", captures)

        self.assertEqual(1, len(notes))
        self.assertIn("gmail/elder_text_heavy", notes[0])
        self.assertIn("scattered", notes[0])

    def test_colour_only_profile_is_not_checked(self):
        # That is contamination_problems' job (a hard failure), not this
        # diagnostic's -- checking it here too would double-report the same
        # settings_display finding under two different mechanisms.
        captures = [
            self.write_labels("settings_display", "baseline", ["Color", "Colors"]),
            self.write_labels("settings_display", "colorblind_deuteranomaly", []),
        ]

        notes = collection_manifest.shape_diagnostics("settings_display", captures)

        self.assertEqual([], notes)


class ScreenProblemsContaminationIntegrationTests(ContaminationAndDiagnosticsTestCase):
    def test_contamination_is_folded_into_screen_problems(self):
        captures = [
            self.write_labels("settings_display", "baseline",
                               ["Brightness", "Color", "Colors"]),
            self.write_labels("settings_display", "colorblind_deuteranomaly",
                               ["Brightness"]),
        ]
        # Fill in the rest of the sequence as successful, empty-content
        # captures so screen_problems doesn't also report missing captures.
        for profile in sequence_profiles():
            if profile in ("baseline", "colorblind_deuteranomaly"):
                continue
            captures.append(self.write_labels("settings_display", profile, ["Brightness"]))

        problems = collection_manifest.screen_problems("settings_display", captures, None)

        self.assertTrue(any("colour-only contamination" in p for p in problems))


class WriteManifestDiagnosticsTests(ContaminationAndDiagnosticsTestCase):
    def test_diagnostics_are_recorded_but_do_not_become_problems(self):
        captures = [
            self.write_labels("gmail", "baseline", ["A", "B", "C", "D"]),
        ]
        for profile in sequence_profiles():
            if profile == "baseline":
                continue
            if profile == "elder_text_heavy":
                texts = ["A", "C"]  # scattered loss -> triggers the diagnostic
            elif profile == "colorblind_deuteranomaly":
                texts = ["A", "B", "C", "D"]  # unchanged -> no contamination
            else:
                texts = ["A", "B"]  # ordinary tail loss -> no diagnostic
            captures.append(self.write_labels("gmail", profile, texts))

        problems = collection_manifest.write_manifest(["gmail"], captures, [])

        manifest = self.read_manifest()
        record = manifest["screens"]["gmail"]
        self.assertTrue(any("scattered" in d for d in record["diagnostics"]))
        self.assertFalse(any("scattered" in p for p in problems))


class ScreenProblemsTests(unittest.TestCase):
    def test_clean_screen_has_no_problems(self):
        problems = collection_manifest.screen_problems("clock", full_entries("clock"), None)
        self.assertEqual([], problems)

    def test_missing_capture_is_reported(self):
        entries = full_entries("clock")
        entries[0]["ok"] = False
        entries[0].pop("label_count", None)

        problems = collection_manifest.screen_problems("clock", entries, None)

        self.assertTrue(any("missing capture" in p for p in problems))

    def test_empty_extraction_is_reported(self):
        entries = full_entries("clock")
        entries[0]["label_count"] = 0

        problems = collection_manifest.screen_problems("clock", entries, None)

        self.assertTrue(any("empty extraction" in p for p in problems))

    def test_flagged_drift_is_reported(self):
        drift = {"screen": "clock", "drift_rate": 0.2, "flagged": True,
                  "vanished": ["x"], "appeared": []}

        problems = collection_manifest.screen_problems("clock", full_entries("clock"), drift)

        self.assertTrue(any("high content drift" in p for p in problems))

    def test_unflagged_drift_is_not_reported(self):
        drift = {"screen": "clock", "drift_rate": 0.0, "flagged": False,
                  "vanished": [], "appeared": []}

        problems = collection_manifest.screen_problems("clock", full_entries("clock"), drift)

        self.assertEqual([], problems)


class RebuildCaptureEntryTests(OrchestratorPathsTestCase):
    def test_missing_files_produce_not_ok_entry(self):
        entry = collection_manifest.rebuild_capture_entry("clock", "baseline", "clock_baseline")

        self.assertFalse(entry["ok"])
        self.assertIn("missing", entry["error"])

    def test_present_files_produce_ok_entry_with_label_count(self):
        stem = "clock_baseline"
        (self.images_dir / f"{stem}.png").write_bytes(b"\x89PNG")
        (self.raw_xml_dir / f"{stem}.xml").write_text("<hierarchy/>", encoding="utf-8")
        (self.labels_dir / f"{stem}.json").write_text(
            json.dumps([{"text": "A", "box": [0, 0, 1, 1]},
                        {"text": "B", "box": [0, 0, 1, 1]}]),
            encoding="utf-8",
        )

        entry = collection_manifest.rebuild_capture_entry("clock", "baseline", stem)

        self.assertTrue(entry["ok"])
        self.assertEqual(2, entry["label_count"])

    def test_partial_files_produce_not_ok_entry(self):
        stem = "clock_baseline"
        (self.images_dir / f"{stem}.png").write_bytes(b"\x89PNG")
        # xml and labels missing

        entry = collection_manifest.rebuild_capture_entry("clock", "baseline", stem)

        self.assertFalse(entry["ok"])


class RebuildScreenTests(OrchestratorPathsTestCase):
    def write_capture(self, stem: str, texts: list[str]) -> None:
        (self.images_dir / f"{stem}.png").write_bytes(b"\x89PNG")
        (self.raw_xml_dir / f"{stem}.xml").write_text("<hierarchy/>", encoding="utf-8")
        (self.labels_dir / f"{stem}.json").write_text(
            json.dumps([{"text": t, "box": [0, 0, 1, 1]} for t in texts]),
            encoding="utf-8",
        )

    def test_full_set_on_disk_reconstructs_all_entries_and_zero_drift(self):
        for profile in sequence_profiles():
            self.write_capture(f"clock_{profile}", ["Alarm", "8:30 AM"])

        entries, drift = collection_manifest.rebuild_screen("clock")

        self.assertEqual(len(sequence_profiles()), len(entries))
        self.assertTrue(all(e["ok"] for e in entries))
        self.assertIsNotNone(drift)
        self.assertEqual(0.0, drift["drift_rate"])
        self.assertFalse(drift["flagged"])

    def test_missing_profile_leaves_that_entry_not_ok_but_others_intact(self):
        for profile in sequence_profiles():
            if profile == "elder_zoom_heavy":
                continue
            self.write_capture(f"clock_{profile}", ["Alarm"])

        entries, _drift = collection_manifest.rebuild_screen("clock")

        by_profile = {e["profile"]: e for e in entries}
        self.assertFalse(by_profile["elder_zoom_heavy"]["ok"])
        self.assertTrue(by_profile["baseline"]["ok"])

    def test_drift_between_open_and_close_baseline_is_detected(self):
        for profile in sequence_profiles():
            if profile == collection_manifest.DRIFT_PROBE:
                self.write_capture(f"clock_{profile}", ["Alarm", "Different Text"])
            else:
                self.write_capture(f"clock_{profile}", ["Alarm", "8:30 AM"])

        _entries, drift = collection_manifest.rebuild_screen("clock")

        self.assertIsNotNone(drift)
        self.assertGreater(drift["drift_rate"], 0.0)


class WorkflowDelegationTests(unittest.TestCase):
    def test_collect_cli_delegates_rebuild_work_through_workflow_to_manifest(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(workflow, "ensure_dirs"), \
             mock.patch.object(
                 workflow.manifest, "rebuild_screen", return_value=([], None)
             ) as rebuild, \
             mock.patch.object(
                 workflow.manifest, "write_manifest", return_value=[]
             ) as write, \
             contextlib.redirect_stdout(io.StringIO()):
            collection_cli.collect_main(
                ["--rebuild-manifest", "--screens", "clock", "--data-dir", tmp]
            )

        rebuild.assert_called_once_with("clock")
        write.assert_called_once_with(["clock"], [], [], reconstructed=True)


if __name__ == "__main__":
    unittest.main()
