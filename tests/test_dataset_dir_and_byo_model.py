"""Tests for the AGB_DATASET_DIR override, --data-dir CLI wiring, filename
sanitization, and the model smoke test -- the bring-your-own-model changes.
"""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import paths
from collection import cli as collection_cli
from evaluation import cli as evaluation_cli
from evaluation.config import (
    canonical_model_id,
    get_results_csv,
    reject_colliding_models,
    sanitize_model_filename,
)


class OutputScopingTests(unittest.TestCase):
    """Two datasets must never reach the same generated file.

    Sharing one would let an evaluation of dataset B resume against dataset
    A's completed keys, and let an analysis of an archive overwrite the
    current run's tables -- in both cases silently, with no column or path
    recording which dataset a row came from.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # Resolved: the path functions under test resolve their arguments, and
        # on macOS the temp root is reached through a symlink (/var ->
        # /private/var), so an unresolved fixture root makes every expected
        # path disagree with the produced one by spelling alone.
        self.root = Path(self.tmp.name).resolve()
        # Every run lives under collections/; the shipped one is the reserved
        # name `experiment`. Named here so the assertions below read as paths
        # rather than as five chained segments.
        self.shipped = self.root / "collections" / "experiment"
        patch = mock.patch.object(paths, "PROJECT_ROOT", self.root)
        patch.start()
        self.addCleanup(patch.stop)

    def test_each_dataset_gets_its_own_result_file(self):
        default = paths.evaluation_results_path(
            "openai/gpt-4o", dataset_dir=self.shipped / "dataset")
        archive = paths.evaluation_results_path(
            "openai/gpt-4o", dataset_dir=self.shipped / "archive" / "experiment_2")
        collected = paths.evaluation_results_path(
            "openai/gpt-4o", dataset_dir=self.root / "collections" / "rerun" / "dataset")
        bare = paths.evaluation_results_path(
            "openai/gpt-4o", dataset_dir=self.root / "elsewhere" / "some_dump")

        # An output root is derived from where the dataset sits, so no two
        # datasets can collide regardless of what their directories are named.
        # A directory named `dataset` is one half of a run root and writes to
        # its sibling outputs/; anything else owns an outputs/ inside itself,
        # so a superseded run stays one self-contained folder.
        self.assertEqual(4, len({default, archive, collected, bare}))
        self.assertEqual(self.shipped / "outputs" / "evaluations", default.parent)
        self.assertEqual(
            self.shipped / "archive" / "experiment_2" / "outputs" / "evaluations",
            archive.parent)
        self.assertEqual(
            self.root / "collections" / "rerun" / "outputs" / "evaluations", collected.parent)
        self.assertEqual(
            self.root / "elsewhere" / "some_dump" / "outputs" / "evaluations", bare.parent)

    def test_a_collection_is_named_after_its_run_not_its_dataset_dir(self):
        """Otherwise every collection reports the shipped default's name."""
        self.assertEqual("dataset", paths.dataset_name(self.shipped / "dataset"))
        self.assertEqual(
            "my-app", paths.dataset_name(self.root / "collections" / "my-app" / "dataset"))
        self.assertEqual(
            "experiment_2",
            paths.dataset_name(self.shipped / "archive" / "experiment_2"))

    def test_vision_and_tree_are_separate_files_for_one_model(self):
        vision = paths.evaluation_results_path("openai/gpt-4o", False)
        tree = paths.evaluation_results_path("openai/gpt-4o", True)
        self.assertNotEqual(vision, tree)
        self.assertEqual("openai_gpt-4o_vision.csv", vision.name)
        self.assertEqual("openai_gpt-4o_tree.csv", tree.name)

    def test_analysis_output_is_scoped_by_dataset_mode_and_sample(self):
        current = paths.analysis_output_path("vision", "all", self.shipped / "dataset")
        archive = paths.analysis_output_path(
            "vision", "all", self.shipped / "archive" / "experiment_2")
        self.assertNotEqual(current, archive)
        self.assertNotEqual(
            current, paths.analysis_output_path("tree", "all", self.shipped / "dataset"))
        self.assertNotEqual(
            current, paths.analysis_output_path("vision", "primary", self.shipped / "dataset"))

    def test_model_name_survives_a_round_trip_through_the_filename(self):
        from analysis.data.results import model_name_from_path

        for model in ("openai/gpt-4o", "ollama/llama3.2-vision:11b", "9router/cx/gpt-5.6-sol"):
            for tree in (False, True):
                path = paths.evaluation_results_path(model, tree)
                self.assertEqual(sanitize_model_filename(model), model_name_from_path(path))

    def test_env_override_moves_the_result_file_with_the_dataset(self):
        collection = self.root / "collections" / "rerun" / "dataset"
        with mock.patch.object(paths, "DATASET_DIR", collection):
            self.assertEqual(
                self.root / "collections" / "rerun" / "outputs" / "evaluations"
                / "openai_gpt-4o_vision.csv",
                paths.evaluation_results_path("openai/gpt-4o"),
            )


class DatasetDirOverrideTests(unittest.TestCase):
    def test_no_override_defaults_to_project_root_dataset(self):
        root = Path("C:/somewhere/accessgroundbench")
        self.assertEqual(
            root / "collections" / "experiment" / "dataset",
            paths._resolve_dataset_dir(root))

    def test_override_env_var_wins_and_is_resolved(self):
        with mock.patch.dict(os.environ, {paths.DATASET_DIR_ENV_VAR: "some/relative/dir"}):
            resolved = paths._resolve_dataset_dir(Path("C:/somewhere/accessgroundbench"))
        self.assertTrue(resolved.is_absolute())
        self.assertEqual(Path("some/relative/dir").resolve(), resolved)

    def test_blank_override_falls_back_to_default(self):
        with mock.patch.dict(os.environ, {paths.DATASET_DIR_ENV_VAR: "   "}):
            root = Path("C:/somewhere/accessgroundbench")
            self.assertEqual(
            root / "collections" / "experiment" / "dataset",
            paths._resolve_dataset_dir(root))


class EvaluateMainDataDirTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop(paths.DATASET_DIR_ENV_VAR, None)
        self.addCleanup(os.environ.pop, paths.DATASET_DIR_ENV_VAR, None)

    def test_data_dir_flag_sets_env_var_before_workflow_runs(self):
        seen = {}

        def fake_evaluate(**kwargs):
            seen["env"] = os.environ.get(paths.DATASET_DIR_ENV_VAR)

        with mock.patch("evaluation.workflow.evaluate", side_effect=fake_evaluate):
            evaluation_cli.evaluate_main(["--data-dir", "my_datasets/app_x"])

        self.assertEqual(
            str(Path("my_datasets/app_x").resolve()), seen["env"]
        )

    def test_no_data_dir_flag_leaves_env_var_unset(self):
        with mock.patch("evaluation.workflow.evaluate") as fake:
            evaluation_cli.evaluate_main(["--fresh"])

        fake.assert_called_once_with(fresh=True, force_unlock=False)
        self.assertNotIn(paths.DATASET_DIR_ENV_VAR, os.environ)


class CollectMainDataDirTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop(paths.DATASET_DIR_ENV_VAR, None)
        self.addCleanup(os.environ.pop, paths.DATASET_DIR_ENV_VAR, None)

    def test_data_dir_flag_sets_env_var_before_workflow_runs(self):
        seen = {}

        def fake_run_collection(screens, **kwargs):
            seen["env"] = os.environ.get(paths.DATASET_DIR_ENV_VAR)

        with mock.patch("collection.workflow.run_collection", side_effect=fake_run_collection):
            collection_cli.collect_main(
                ["--dry-run", "--data-dir", "my_datasets/app_x"]
            )

        self.assertEqual(
            str(Path("my_datasets/app_x").resolve()), seen["env"]
        )


class DataDirEnvVarConstantSyncTests(unittest.TestCase):
    """evaluation.cli/collection.cli hardcode the env var name rather than
    importing paths.DATASET_DIR_ENV_VAR (see the comment at the top of each
    module: importing `paths` at all runs its DATASET_DIR computation
    immediately, which is exactly the bug the subprocess tests below catch).
    This guards the two copies against drifting from the source of truth.
    """

    def test_evaluation_cli_constant_matches_paths(self):
        self.assertEqual(paths.DATASET_DIR_ENV_VAR, evaluation_cli._DATASET_DIR_ENV_VAR)

    def test_collection_cli_constant_matches_paths(self):
        self.assertEqual(paths.DATASET_DIR_ENV_VAR, collection_cli._DATASET_DIR_ENV_VAR)


class RealSubprocessDataDirTests(unittest.TestCase):
    """Exercises --data-dir through an actual spawned interpreter rather than
    an in-process mock.

    This class exists because of a real bug: an earlier version of
    evaluation.cli/collection.cli imported `from paths import
    DATASET_DIR_ENV_VAR` at module level. That import alone runs paths.py's
    DATASET_DIR computation before argparse had even parsed --data-dir,
    permanently freezing DATASET_DIR to the default for the rest of the
    process -- the override was silently ignored. Every in-process test above
    passed anyway, because mock.patch("evaluation.workflow.evaluate", ...)
    (or collection.workflow.run_collection) itself imports evaluation.config
    (which imports paths) before evaluate_main/collect_main ever runs, which
    coincidentally pre-populates the same DATASET_DIR the bug would have
    frozen it to -- masking the bug entirely. Only a real subprocess, with a
    clean, unimported `paths` module, reproduces it.
    """

    def run_cli(self, args: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
        full_env = dict(os.environ)
        full_env.pop(paths.DATASET_DIR_ENV_VAR, None)
        if env:
            full_env.update(env)
        code = "import sys, cli; sys.exit(cli.main(sys.argv[1:]) or 0)"
        return subprocess.run(
            [sys.executable, "-c", code, *args],
            cwd=str(paths.PROJECT_ROOT),
            env=full_env,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_collect_dry_run_data_dir_is_honored_by_a_real_subprocess(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "my_collect_dataset"
            result = self.run_cli([
                "collect", "--dry-run", "--screens", "clock",
                "--data-dir", str(target),
            ])

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn(str(target), result.stdout)
        # The bug this guards against prints the default dataset/ path
        # instead -- assert the default is NOT what appears.
        default_images = str(paths.PROJECT_ROOT / "collections" / "experiment" / "dataset" / "images")
        self.assertNotIn(default_images, result.stdout)

    def test_evaluate_data_dir_is_honored_by_a_real_subprocess(self):
        # An empty --data-dir with no baseline labels is a safe, unambiguous
        # probe: if the override is honored, evaluate() finds zero screens
        # and exits 1 immediately, before any model or network is touched.
        # If the bug regresses and it silently falls back to the real
        # dataset/ (which has real screens), this assertion fails instead of
        # quietly passing -- and even in that failure mode nothing unsafe
        # happens, because VLM_MODEL is prefixed openai/ and no
        # OPENAI_API_KEY is set in full_env, so evaluate() would only ever
        # print [SKIP] rather than place a real API call.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "my_eval_dataset"
            (target / "labels").mkdir(parents=True)
            (target / "images").mkdir(parents=True)

            env = {"VLM_MODEL": "openai/does-not-matter", "OPENAI_API_KEY": ""}
            result = self.run_cli(["evaluate", "--data-dir", str(target)], env=env)

        self.assertEqual(1, result.returncode)
        self.assertIn("No screens found", result.stdout)


class FilenameSanitizationTests(unittest.TestCase):
    def test_result_file_is_named_after_the_model_not_the_route(self):
        """A 9router gateway is a local deployment detail, not part of the result."""
        path = get_results_csv("9router/cx/gpt-5.5")
        self.assertEqual("gpt-5.5_vision.csv", path.name)
        self.assertEqual("evaluations", path.parent.name)

        self.assertEqual("openai_gpt-4o_tree.csv", get_results_csv("openai/gpt-4o", True).name)

    def test_provider_prefixes_are_kept(self):
        """anthropic/ and local/ name who served the model -- a real property."""
        self.assertEqual(
            "anthropic_claude-opus-5_vision.csv",
            get_results_csv("anthropic/claude-opus-5").name,
        )
        self.assertEqual(
            "local_ferret-ui-llama8b_vision.csv",
            get_results_csv("local/ferret-ui-llama8b").name,
        )

    def test_a_routing_prefix_with_no_model_is_left_intact(self):
        # Collapsing every malformed id to the same empty name would make two
        # broken configs share one CSV; model_configuration_error reports them.
        self.assertEqual("9router/", canonical_model_id("9router/"))

    def test_two_routes_to_the_same_model_are_refused_in_one_run(self):
        """Both would claim one resumable CSV and silently blend their rows."""
        with contextlib.redirect_stdout(io.StringIO()) as out:
            with self.assertRaises(SystemExit):
                reject_colliding_models(
                    ["9router/cx/gpt-5.5", "9router/vendor/gpt-5.5"]
                )
        self.assertIn("same result filename", out.getvalue())

    def test_distinct_models_do_not_collide(self):
        reject_colliding_models(
            ["9router/cx/gpt-5.5", "anthropic/claude-opus-5", "openai/gpt-4o"]
        )

    def test_colon_is_sanitized(self):
        # Ollama-style ids embed a tag after a colon, which is illegal in a
        # Windows filename and previously crashed at file-open time.
        cleaned = sanitize_model_filename("ollama/llama3.2-vision:11b")
        self.assertNotIn(":", cleaned)
        self.assertEqual("ollama_llama3.2-vision_11b", cleaned)

    def test_windows_reserved_characters_are_sanitized(self):
        cleaned = sanitize_model_filename('a<b>c:d"e\\f|g?h*i')
        self.assertTrue(all(ch not in cleaned for ch in '<>:"\\|?*'))

    def test_trailing_dot_and_space_are_stripped(self):
        cleaned = sanitize_model_filename("openai/gpt-4o-mini. ")
        self.assertFalse(cleaned.endswith(".") or cleaned.endswith(" "))

    def test_long_model_id_is_capped(self):
        cleaned = sanitize_model_filename("openai/" + "x" * 500)
        self.assertLessEqual(len(cleaned), 150)

    def test_tree_suffix_still_appends_after_sanitization(self):
        path = get_results_csv("ollama/llama3.2-vision:11b", use_a11y_tree=True)
        self.assertEqual("ollama_llama3.2-vision_11b_tree.csv", path.name)
        # The filename itself must stay Windows-legal; a drive letter in the
        # surrounding absolute path is not the model's doing.
        self.assertNotIn(":", path.name)


if __name__ == "__main__":
    unittest.main()
