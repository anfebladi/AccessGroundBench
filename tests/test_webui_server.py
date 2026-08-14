import contextlib
import io
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import paths
from evaluation.storage.results import CSV_COLUMNS, append_result, init_csv
from webui.backend.services import keys as keys_mod
from webui.backend.server import create_app


def write_png_header(path: Path, width: int, height: int) -> None:
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
    )


class WebuiServerTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.addCleanup(self.tmp_dir.cleanup)

        self.dataset_dir = self.root / "collections" / "experiment" / "dataset"
        (self.dataset_dir / "images").mkdir(parents=True)
        (self.dataset_dir / "labels").mkdir(parents=True)

        write_png_header(self.dataset_dir / "images" / "clock_baseline.png", 1080, 2274)
        write_png_header(self.dataset_dir / "images" / "clock_elder_text_heavy.png", 1080, 2274)
        labels = [{"text": "8:30 AM", "box": [84, 231, 429, 414]}]
        (self.dataset_dir / "labels" / "clock_baseline.json").write_text(
            json.dumps(labels), encoding="utf-8",
        )
        (self.dataset_dir / "labels" / "clock_elder_text_heavy.json").write_text(
            json.dumps(labels), encoding="utf-8",
        )

        # A second, ordinary run. Every run under collections/ is equal, so this
        # is what a "some other dataset" fixture looks like now.
        self.other_dir = self.root / "collections" / "other_run" / "dataset"
        (self.other_dir / "images").mkdir(parents=True)
        (self.other_dir / "labels").mkdir(parents=True)
        (self.other_dir / "labels" / "clock_baseline.json").write_text("[]", encoding="utf-8")

        # Every output root is derived from PROJECT_ROOT at call time, so this
        # one patch isolates the whole test from the real checkout's outputs.
        # If a second patch ever becomes necessary here, some module has gone
        # back to freezing a root at import time.
        self._root_patch = mock.patch.object(paths, "PROJECT_ROOT", self.root)
        self._root_patch.start()
        self.addCleanup(self._root_patch.stop)

        for provider in keys_mod.PROVIDER_ENV_VARS:
            keys_mod.clear_key(provider)
        self.addCleanup(lambda: [keys_mod.clear_key(p) for p in keys_mod.PROVIDER_ENV_VARS])

        self.client = TestClient(create_app())

    def write_results_csv(self, model: str, rows: list[dict], *,
                          use_a11y_tree: bool = False,
                          dataset_dir: Path | None = None) -> Path:
        """Write a fixture result file into a dataset's own output root."""
        path = paths.evaluation_results_path(
            model, use_a11y_tree, dataset_dir or self.dataset_dir,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        init_csv(path)
        for row in rows:
            full_row = {col: row.get(col, "") for col in CSV_COLUMNS}
            append_result(path, full_row)
        return path

    def test_list_datasets_names_each_run_after_its_folder(self):
        resp = self.client.get("/api/datasets")
        self.assertEqual(200, resp.status_code)
        by_name = {d["name"]: d for d in resp.json()}
        # No run is privileged and none is called "dataset" -- that was the
        # registry name the shipped run used to be given by a special case.
        self.assertEqual({"experiment", "other_run"}, set(by_name))
        self.assertNotIn("is_default", by_name["experiment"])
        self.assertNotIn("is_archived", by_name["experiment"])

    def test_unknown_dataset_is_404(self):
        resp = self.client.get("/api/datasets/nonexistent/screens")
        self.assertEqual(404, resp.status_code)

    def test_dataset_screens_lists_baseline_derived_names(self):
        resp = self.client.get("/api/datasets/experiment/screens")
        self.assertEqual(200, resp.status_code)
        self.assertEqual(["clock"], resp.json()["screens"])

    def test_dataset_targets_returns_harvested_targets(self):
        terminal = io.StringIO()
        with contextlib.redirect_stdout(terminal):
            resp = self.client.get("/api/datasets/experiment/targets/clock")
        self.assertEqual(200, resp.status_code)
        targets = resp.json()["targets"]
        self.assertEqual(1, len(targets))
        self.assertEqual("8:30 AM", targets[0]["text"])
        self.assertNotIn("[HARVEST]", terminal.getvalue())

    def test_smoke_test_suppresses_backend_output(self):
        from evaluation.smoke import SmokeTestResult

        def noisy_smoke(*args, **kwargs):
            print("SMOKE BACKEND OUTPUT")
            return SmokeTestResult(
                ok=True,
                model=args[0],
                screen=args[1],
                target_text="8:30 AM",
                raw_response="[200, 300]",
                x_pred=200,
                y_pred=300,
                box=[84, 231, 429, 414],
                hit=1,
                coord_space_detected="pixel",
                coord_space_used="pixel",
            )

        terminal = io.StringIO()
        with mock.patch("evaluation.smoke.smoke_test_model", side_effect=noisy_smoke):
            with contextlib.redirect_stdout(terminal):
                resp = self.client.post("/api/smoke-test", json={
                    "dataset": "experiment",
                    "model": "test-model",
                    "screen": "clock",
                })

        self.assertEqual(200, resp.status_code)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertEqual("test-model", body["model"])
        self.assertEqual("clock", body["screen"])
        self.assertEqual("8:30 AM", body["target_text"])
        self.assertNotIn("SMOKE BACKEND OUTPUT", terminal.getvalue())

    def test_dataset_image_serves_png(self):
        resp = self.client.get("/api/datasets/experiment/image/clock/baseline")
        self.assertEqual(200, resp.status_code)
        self.assertEqual("image/png", resp.headers["content-type"])

    def test_dataset_image_missing_is_404(self):
        resp = self.client.get("/api/datasets/experiment/image/clock/elder_combo_max")
        self.assertEqual(404, resp.status_code)

    def test_dataset_labels_returns_json(self):
        resp = self.client.get("/api/datasets/experiment/labels/clock/baseline")
        self.assertEqual(200, resp.status_code)
        self.assertEqual("8:30 AM", resp.json()[0]["text"])

    def test_dataset_manifest_reports_unavailable_when_absent(self):
        resp = self.client.get("/api/datasets/experiment/manifest")
        self.assertEqual(200, resp.status_code)
        self.assertFalse(resp.json()["available"])

    def test_get_doc_returns_content(self):
        docs_dir = self.root / "docs"
        docs_dir.mkdir(parents=True)
        (docs_dir / "collection.md").write_text("# Collection guide\n", encoding="utf-8")

        resp = self.client.get("/api/docs/collection.md")

        self.assertEqual(200, resp.status_code)
        body = resp.json()
        self.assertEqual("collection.md", body["name"])
        self.assertEqual("# Collection guide\n", body["content"])

    def test_get_doc_rejects_unknown_name(self):
        resp = self.client.get("/api/docs/nope.md")
        self.assertEqual(404, resp.status_code)

    def test_get_doc_404s_when_allowed_but_missing_on_disk(self):
        resp = self.client.get("/api/docs/collection.md")
        self.assertEqual(404, resp.status_code)

    def test_provider_status_defaults_to_unconfigured(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            resp = self.client.get("/api/providers")
        self.assertEqual(200, resp.status_code)
        providers = {p["provider"]: p for p in resp.json()}
        self.assertFalse(providers["openai"]["configured"])

    def test_setting_a_session_key_is_reflected_in_provider_status(self):
        set_resp = self.client.post("/api/keys", json={"provider": "openai", "value": "sk-test"})
        self.assertEqual(200, set_resp.status_code)

        with mock.patch.dict("os.environ", {}, clear=True):
            status_resp = self.client.get("/api/providers")
        providers = {p["provider"]: p for p in status_resp.json()}
        self.assertTrue(providers["openai"]["session_configured"])
        self.assertTrue(providers["openai"]["configured"])
        self.assertFalse(providers["openai"]["env_configured"])

        clear_resp = self.client.delete("/api/keys/openai")
        self.assertEqual(200, clear_resp.status_code)
        with mock.patch.dict("os.environ", {}, clear=True):
            status_resp2 = self.client.get("/api/providers")
        self.assertFalse({p["provider"]: p for p in status_resp2.json()}["openai"]["configured"])

    def test_set_key_rejects_unknown_provider(self):
        resp = self.client.post("/api/keys", json={"provider": "not-real", "value": "x"})
        self.assertEqual(400, resp.status_code)

    def test_dataset_results_computes_accuracy_from_co_present_rows(self):
        self.write_results_csv("test-model", [
            {"screen": "clock", "target_text": "8:30 AM", "profile": "baseline",
             "status": "co_present", "score": "1", "prompt_mode": "vision"},
            {"screen": "clock", "target_text": "8:30 AM", "profile": "elder_text_heavy",
             "status": "co_present", "score": "0", "prompt_mode": "vision"},
        ])
        resp = self.client.get("/api/datasets/experiment/results")
        self.assertEqual(200, resp.status_code)
        rows = resp.json()
        self.assertEqual(1, len(rows))
        self.assertEqual("test-model", rows[0]["model"])
        self.assertEqual(2, rows[0]["co_present_count"])
        self.assertEqual(1, rows[0]["hits"])
        self.assertAlmostEqual(0.5, rows[0]["accuracy"])
        self.assertEqual("test-model_vision.csv", rows[0]["filename"])

    def test_analysis_endpoint_reports_unavailable_when_nothing_has_been_run(self):
        resp = self.client.get("/api/datasets/experiment/analysis?mode=vision&sample=all")
        self.assertEqual(200, resp.status_code)
        body = resp.json()
        self.assertFalse(body["available"])
        self.assertIsNone(body["output_dir"])
        self.assertEqual([], body["reachability"])

    def test_analysis_endpoint_reads_existing_tables_without_recomputing(self):
        # This is the direct regression test for "I see no graphs": tables
        # already on disk from a prior `agb analyze` (or a previous browser
        # run) must be readable without POSTing a fresh, multi-minute run.
        output_dir = paths.analysis_output_path("vision", "all", self.dataset_dir)
        output_dir.mkdir(parents=True)
        (output_dir / "reachability_results.csv").write_text(
            "Sample,Profile,Targets_Present,Targets_Total,Reachability,CI_Low,CI_High\n"
            "all,elder_text_heavy,9,10,0.9000,0.6000,0.9800\n",
            encoding="utf-8",
        )

        resp = self.client.get("/api/datasets/experiment/analysis?mode=vision&sample=all")
        self.assertEqual(200, resp.status_code)
        body = resp.json()
        self.assertTrue(body["available"])
        self.assertEqual("collections/experiment/outputs/analysis/vision_all", body["output_dir"])
        self.assertEqual(1, len(body["reachability"]))
        self.assertEqual("elder_text_heavy", body["reachability"][0]["Profile"])
        # The other three tables have no file on disk yet -- empty, not an error.
        self.assertEqual([], body["pooled_permutation"])
        self.assertEqual([], body["mcnemar_per_model"])
        self.assertEqual([], body["direction_consistency"])

    def test_analysis_endpoint_rejects_unknown_mode_or_sample(self):
        self.assertEqual(400, self.client.get(
            "/api/datasets/experiment/analysis?mode=bogus"
        ).status_code)
        self.assertEqual(400, self.client.get(
            "/api/datasets/experiment/analysis?sample=bogus"
        ).status_code)

    def test_result_rows_endpoint_returns_scoreable_fields(self):
        self.write_results_csv("test-model", [
            {"screen": "clock", "target_text": "8:30 AM", "profile": "baseline",
             "status": "co_present", "score": "1", "x_pred": "200", "y_pred": "300",
             "x_min": "84", "y_min": "231", "x_max": "429", "y_max": "414",
             "raw_response": "[200, 300]", "prompt_mode": "vision"},
            {"screen": "clock", "target_text": "8:30 AM", "profile": "elder_text_heavy",
             "status": "co_present", "score": "0", "x_pred": "10", "y_pred": "10",
             "x_min": "84", "y_min": "231", "x_max": "429", "y_max": "414",
             "raw_response": "[10, 10]", "prompt_mode": "vision"},
        ])
        resp = self.client.get("/api/datasets/experiment/results/test-model_vision.csv/rows")
        self.assertEqual(200, resp.status_code)
        rows = resp.json()
        self.assertEqual(2, len(rows))
        misses = [r for r in rows if r["status"] == "co_present" and r["score"] == "0"]
        self.assertEqual(1, len(misses))
        self.assertEqual("elder_text_heavy", misses[0]["profile"])
        self.assertEqual("[10, 10]", misses[0]["raw_response"])

    def test_result_rows_rejects_path_traversal_filename(self):
        resp = self.client.get("/api/datasets/experiment/results/../../../etc/passwd/rows")
        self.assertIn(resp.status_code, (404, 400))

    def test_result_rows_missing_file_is_404(self):
        resp = self.client.get("/api/datasets/experiment/results/nope_vision.csv/rows")
        self.assertEqual(404, resp.status_code)

    def test_preflight_reports_expected_and_completed_counts(self):
        # Only one screen (clock, one target) exists in the fixture, so
        # expected_total = 1 target x 6 profiles = 6, regardless of model.
        resp = self.client.get(
            "/api/datasets/experiment/preflight",
            params={"model": "openai/gpt-4o-mini", "use_a11y_tree": "false"},
        )
        self.assertEqual(200, resp.status_code)
        body = resp.json()
        self.assertEqual(6, body["expected_total"])
        self.assertEqual(0, body["already_done"])
        self.assertFalse(body["lock_present"])
        self.assertEqual("openai_gpt-4o-mini_vision.csv", body["results_csv"])

    def test_preflight_counts_already_completed_rows(self):
        self.write_results_csv("openai/gpt-4o-mini", [
            {"screen": "clock", "target_text": "8:30 AM", "profile": "baseline",
             "status": "co_present", "score": "1", "prompt_mode": "vision"},
        ])
        resp = self.client.get(
            "/api/datasets/experiment/preflight",
            params={"model": "openai/gpt-4o-mini"},
        )
        self.assertEqual(1, resp.json()["already_done"])

    def test_preflight_detects_a_stale_lock(self):
        from evaluation.storage.locking import acquire_lock, lock_path

        results_csv = paths.evaluation_results_path("openai/gpt-4o-mini", dataset_dir=self.dataset_dir)
        acquire_lock(results_csv)
        self.addCleanup(lambda: lock_path(results_csv).unlink(missing_ok=True))

        resp = self.client.get(
            "/api/datasets/experiment/preflight",
            params={"model": "openai/gpt-4o-mini"},
        )
        self.assertTrue(resp.json()["lock_present"])
        self.assertIsNotNone(resp.json()["lock_holder"])

    def test_preflight_without_model_is_400(self):
        resp = self.client.get("/api/datasets/experiment/preflight", params={"model": ""})
        self.assertEqual(400, resp.status_code)

    def test_start_run_against_an_unknown_dataset_is_a_404(self):
        resp = self.client.post(
            "/api/runs", json={"dataset": "no_such_run", "model": "openai/gpt-4o-mini"})
        self.assertEqual(404, resp.status_code)

    def test_start_run_without_model_is_a_400(self):
        resp = self.client.post("/api/runs", json={"dataset": "experiment"})
        self.assertEqual(400, resp.status_code)

    def test_start_run_returns_run_id_and_equivalent_command(self):
        resp = self.client.post("/api/runs", json={
            "dataset": "experiment", "model": "openai/gpt-4o-mini", "use_a11y_tree": False,
        })
        self.assertEqual(200, resp.status_code)
        body = resp.json()
        self.assertIn("run_id", body)
        self.assertIn("agb evaluate", body["equivalent_command"])
        self.assertIn("VLM_MODEL=openai/gpt-4o-mini", body["equivalent_command"])

        # Poll until the subprocess (which will skip instantly on the
        # missing API key) finishes, confirming the run endpoints work
        # end-to-end without touching real credentials or dataset files.
        import time
        deadline = time.monotonic() + 20
        status = "running"
        while status == "running" and time.monotonic() < deadline:
            time.sleep(0.2)
            poll = self.client.get(f"/api/runs/{body['run_id']}?since=0")
            self.assertEqual(200, poll.status_code)
            status = poll.json()["status"]
        self.assertIn(status, ("completed", "failed"))

    def test_get_unknown_run_is_404(self):
        resp = self.client.get("/api/runs/does-not-exist")
        self.assertEqual(404, resp.status_code)

    def test_cancel_unknown_run_is_400(self):
        resp = self.client.post("/api/runs/does-not-exist/cancel")
        self.assertEqual(400, resp.status_code)

    def test_collect_screens_lists_default_order(self):
        resp = self.client.get("/api/collect/screens")
        self.assertEqual(200, resp.status_code)
        body = resp.json()
        self.assertIn("clock", body["default_order"])
        self.assertIn("clock", body["all_screens"])

    def test_collect_preflight_reports_adb_unavailable(self):
        with mock.patch(
            "collection.runtime.device.resolve_adb",
            return_value=str(self.root / "no-such-adb.exe"),
        ):
            resp = self.client.get("/api/collect/preflight")
        self.assertEqual(200, resp.status_code)
        body = resp.json()
        self.assertFalse(body["adb_available"])
        self.assertIsNotNone(body["error"])

    def test_start_collect_run_rejects_only_unsafe_names(self):
        # Path safety only. No name is reserved: every run under collections/ is
        # ordinary data, so there is nothing for this endpoint to treat as
        # special. See the companion test below for what that permits.
        bad_names = ("", "a/b", "a\\b", "..")
        for bad_name in bad_names:
            with self.subTest(bad_name=bad_name):
                resp = self.client.post(
                    "/api/collect/runs", json={"name": bad_name, "dry_run": True})
                self.assertEqual(400, resp.status_code)

    def test_start_collect_run_accepts_an_existing_run_name(self):
        """Collecting into a run that already exists is a supported workflow.

        `--screens <subset>` adds screens to a run already on disk and
        `--rebuild-manifest` does nothing else, so refusing existing names would
        break both. The consequence, accepted deliberately: a collection named
        after a committed run adds to it.
        """
        resp = self.client.post(
            "/api/collect/runs", json={"name": "experiment", "dry_run": True})
        self.assertEqual(200, resp.status_code, resp.text)
        self.assertIn(
            str(self.root / "collections" / "experiment" / "dataset"),
            resp.json()["equivalent_command"],
        )

    def test_start_collect_run_targets_the_collections_subdirectory(self):
        resp = self.client.post("/api/collect/runs", json={
            "name": "my_new_app", "dry_run": True, "screens": ["clock"],
        })
        self.assertEqual(200, resp.status_code)
        body = resp.json()
        self.assertIn("run_id", body)
        expected_path = str(self.root / "collections" / "my_new_app" / "dataset")
        self.assertIn(expected_path, body["equivalent_command"])
        self.assertIn("--dry-run", body["equivalent_command"])

        import time
        deadline = time.monotonic() + 20
        status = "running"
        while status == "running" and time.monotonic() < deadline:
            time.sleep(0.2)
            poll = self.client.get(f"/api/runs/{body['run_id']}?since=0")
            status = poll.json()["status"]
        # --dry-run touches no ADB and captures no assets, but it does call
        # ensure_dirs() -- so the (empty) directory skeleton is expected,
        # while no actual capture output (images/xml/labels files) is.
        self.assertEqual("completed", status)
        new_dataset_dir = self.root / "collections" / "my_new_app" / "dataset"
        self.assertTrue(new_dataset_dir.is_dir())
        self.assertEqual([], list((new_dataset_dir / "images").iterdir()))
        # The old flat layout must not come back alongside it.
        self.assertFalse((self.root / "datasets").exists())

    def test_start_collect_run_uses_the_real_project_root_not_a_mocked_one(self):
        # The subprocess resolves paths.PROJECT_ROOT for itself -- mocking
        # paths.PROJECT_ROOT in this test process (as setUp does) has no
        # effect on the spawned child, so this only works because --data-dir
        # is passed as an ABSOLUTE path. Regression coverage for that.
        resp = self.client.post("/api/collect/runs", json={
            "name": "my_new_app2", "dry_run": True, "screens": ["clock"],
        })
        run_id = resp.json()["run_id"]

        import time
        deadline = time.monotonic() + 20
        status = "running"
        while status == "running" and time.monotonic() < deadline:
            time.sleep(0.2)
            poll = self.client.get(f"/api/runs/{run_id}?since=0")
            status = poll.json()["status"]

        self.assertEqual("completed", status)
        self.assertTrue((self.root / "collections" / "my_new_app2" / "dataset").is_dir())

    def test_analyze_with_no_result_csvs_is_a_400(self):
        resp = self.client.post("/api/analyze", json={"dataset": "experiment", "mode": "vision"})
        self.assertEqual(400, resp.status_code)

    def write_analyzable_results(self, model: str = "m1", *, use_a11y_tree: bool = False,
                                 dataset_dir: Path | None = None) -> None:
        """One model, one target, present at baseline and under one profile."""
        box = {"x_min": "84", "y_min": "231", "x_max": "429", "y_max": "414"}
        mode = "tree" if use_a11y_tree else "vision"
        rows = [
            {"screen": "clock", "target_text": "8:30 AM", "profile": "baseline",
             "status": "co_present", "score": "1", "prompt_mode": mode,
             "x_pred": "200", "y_pred": "300", **box},
            {"screen": "clock", "target_text": "8:30 AM", "profile": "elder_text_heavy",
             "status": "co_present", "score": "0", "prompt_mode": mode,
             "x_pred": "900", "y_pred": "1800", **box},
        ]
        self.write_results_csv(model, rows, use_a11y_tree=use_a11y_tree,
                               dataset_dir=dataset_dir)

    def run_analysis_request(self, **overrides):
        payload = {"dataset": "experiment", "mode": "vision", "sample": "primary",
                   "permutations": 10, "seed": 0}
        payload.update(overrides)
        return self.client.post("/api/analyze", json=payload)

    def test_analyze_never_overwrites_the_datasets_own_result_tables(self):
        """A click in the browser must not clobber a committed experiment.

        `agb analyze` names its outputs after the analysis rather than the run,
        so writing into the dataset would silently narrow the committed tables
        to whichever sample happened to be selected in the form.
        """
        self.write_analyzable_results()
        committed = self.dataset_dir / "reachability_results.csv"
        committed.write_text("Sample,Profile\ncommitted,do-not-touch\n", encoding="utf-8")

        resp = self.run_analysis_request()
        self.assertEqual(200, resp.status_code, resp.text)

        self.assertEqual(
            "Sample,Profile\ncommitted,do-not-touch\n",
            committed.read_text(encoding="utf-8"),
        )
        for name in ("pooled_permutation_results.csv", "mcnemar_results_per_model.csv",
                     "direction_consistency.csv"):
            self.assertFalse((self.dataset_dir / name).exists(), name)

    def test_analyze_writes_under_the_runs_output_root_and_reports_the_path(self):
        self.write_analyzable_results()

        resp = self.run_analysis_request()
        self.assertEqual(200, resp.status_code, resp.text)
        self.assertEqual("collections/experiment/outputs/analysis/vision_primary",
                         resp.json()["output_dir"])

        out = self.root / "collections" / "experiment" / "outputs" / "analysis" / "vision_primary"
        self.assertTrue((out / "reachability_results.csv").is_file())
        self.assertTrue(resp.json()["reachability"])

    def test_analyze_keeps_vision_and_tree_output_apart(self):
        """The two arms answer different questions and must never be conflated."""
        self.write_analyzable_results()
        self.write_analyzable_results(use_a11y_tree=True)

        self.assertEqual(200, self.run_analysis_request(mode="vision").status_code)
        self.assertEqual(200, self.run_analysis_request(mode="tree").status_code)

        root = self.root / "collections" / "experiment" / "outputs" / "analysis"
        self.assertTrue((root / "vision_primary" / "reachability_results.csv").is_file())
        self.assertTrue((root / "tree_primary" / "reachability_results.csv").is_file())

    def test_analyzing_one_run_writes_nothing_into_another(self):
        """Output roots are per-run, so two runs can never reach the same table."""
        other = self.other_dir
        write_png_header(other / "images" / "clock_baseline.png", 1080, 2274)
        write_png_header(other / "images" / "clock_elder_text_heavy.png", 1080, 2274)
        labels = [{"text": "8:30 AM", "box": [84, 231, 429, 414]}]
        for profile in ("baseline", "elder_text_heavy"):
            (other / "labels" / f"clock_{profile}.json").write_text(
                json.dumps(labels), encoding="utf-8")

        self.write_analyzable_results(dataset_dir=other)
        self.write_analyzable_results()
        self.assertEqual(200, self.run_analysis_request().status_code)
        current_table = (self.root / "collections" / "experiment" / "outputs" / "analysis"
                         / "vision_primary" / "reachability_results.csv")
        current_before = current_table.read_text(encoding="utf-8")

        # The other run's captures must not change: analysis reads
        # images/labels/raw_xml and writes none of them.
        captures_before = {
            name: sorted(p.name for p in (other / name).iterdir())
            for name in ("images", "labels")
        }
        resp = self.run_analysis_request(dataset="other_run")
        self.assertEqual(200, resp.status_code, resp.text)

        self.assertEqual(captures_before, {
            name: sorted(p.name for p in (other / name).iterdir())
            for name in ("images", "labels")
        })
        # collections/other_run/dataset is half of a run root, so its tables land
        # in the sibling outputs/, not inside its own captures.
        self.assertTrue(
            (self.root / "collections" / "other_run" / "outputs" / "analysis"
             / "vision_primary" / "reachability_results.csv").is_file()
        )
        self.assertEqual(current_before, current_table.read_text(encoding="utf-8"))

    def test_analyze_rejects_an_unknown_sample_or_mode(self):
        self.write_analyzable_results()
        self.assertEqual(400, self.run_analysis_request(sample="../escape").status_code)
        self.assertEqual(400, self.run_analysis_request(mode="../escape").status_code)
        self.assertFalse((self.root / "collections" / "experiment" / "outputs"
                          / "analysis").exists())


if __name__ == "__main__":
    unittest.main()
