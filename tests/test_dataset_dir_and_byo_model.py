"""Tests for the AGB_DATASET_DIR override, --data-dir CLI wiring, filename
sanitization, and the model smoke test -- the bring-your-own-model changes.
"""

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
from evaluation.config import get_results_csv, sanitize_model_filename


class DatasetDirOverrideTests(unittest.TestCase):
    def test_no_override_defaults_to_project_root_dataset(self):
        root = Path("C:/somewhere/accessgroundbench")
        self.assertEqual(root / "dataset", paths._resolve_dataset_dir(root))

    def test_override_env_var_wins_and_is_resolved(self):
        with mock.patch.dict(os.environ, {paths.DATASET_DIR_ENV_VAR: "some/relative/dir"}):
            resolved = paths._resolve_dataset_dir(Path("C:/somewhere/accessgroundbench"))
        self.assertTrue(resolved.is_absolute())
        self.assertEqual(Path("some/relative/dir").resolve(), resolved)

    def test_blank_override_falls_back_to_default(self):
        with mock.patch.dict(os.environ, {paths.DATASET_DIR_ENV_VAR: "   "}):
            root = Path("C:/somewhere/accessgroundbench")
            self.assertEqual(root / "dataset", paths._resolve_dataset_dir(root))


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
        default_images = str(paths.PROJECT_ROOT / "dataset" / "images")
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
    def test_slash_replacement_is_unchanged_from_original_behavior(self):
        path = get_results_csv("9router/cx/gpt-5.5")
        self.assertEqual("results.csv", path.name)
        self.assertEqual(("9router_cx_gpt-5.5", "vision"),
                         (path.parent.parent.name, path.parent.name))
        self.assertEqual("evaluations", path.parent.parent.parent.name)

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
        self.assertEqual("results.csv", path.name)
        self.assertEqual("tree", path.parent.name)
        self.assertEqual("ollama_llama3.2-vision_11b", path.parent.parent.name)
        self.assertNotIn(":", str(path))


if __name__ == "__main__":
    unittest.main()
