import io
import unittest
from unittest import mock

import vlm_evaluator
from vlm_eval import config


class VlmEvaluatorConfigTests(unittest.TestCase):
    @mock.patch.dict("vlm_eval.config.os.environ", {"VLM_MODEL": "openai/gpt-4o-mini"})
    def test_resolve_models_prefers_cli_model(self):
        self.assertEqual(
            ["gemini/gemini-2.5-pro"],
            config.resolve_models("gemini/gemini-2.5-pro"),
        )

    @mock.patch.dict("vlm_eval.config.os.environ", {"VLM_MODEL": "openai/gpt-4o-mini, local/ferret-ui-llama8b"})
    def test_resolve_models_uses_env_model_and_splits(self):
        self.assertEqual(
            ["openai/gpt-4o-mini", "local/ferret-ui-llama8b"],
            config.resolve_models(None),
        )

    @mock.patch.dict("vlm_eval.config.os.environ", {}, clear=True)
    def test_resolve_models_exits_without_cli_or_env_model(self):
        with self.assertRaises(SystemExit) as exc:
            config.resolve_models(None)

        self.assertEqual(1, exc.exception.code)

    @mock.patch.dict("vlm_eval.config.os.environ", {"VLM_PACE_SECONDS": "0.5"})
    def test_resolve_pace_seconds_prefers_cli_value(self):
        self.assertEqual(1.25, config.resolve_pace_seconds("1.25"))

    @mock.patch.dict("vlm_eval.config.os.environ", {"VLM_PACE_SECONDS": "0.5"})
    def test_resolve_pace_seconds_uses_env_value(self):
        self.assertEqual(0.5, config.resolve_pace_seconds(None))

    @mock.patch.dict("vlm_eval.config.os.environ", {}, clear=True)
    def test_resolve_pace_seconds_defaults_to_zero(self):
        self.assertEqual(0.0, config.resolve_pace_seconds(None))

    @mock.patch.dict("vlm_eval.config.os.environ", {"VLM_PACE_SECONDS": "-1"})
    def test_resolve_pace_seconds_exits_for_negative_env_value(self):
        with self.assertRaises(SystemExit) as exc:
            config.resolve_pace_seconds(None)

        self.assertEqual(1, exc.exception.code)

    @mock.patch.dict("vlm_eval.config.os.environ", {"VLM_PACE_SECONDS": "fast"})
    def test_resolve_pace_seconds_exits_for_non_number_env_value(self):
        with self.assertRaises(SystemExit) as exc:
            config.resolve_pace_seconds(None)

        self.assertEqual(1, exc.exception.code)

    @mock.patch.dict("vlm_eval.config.os.environ", {}, clear=True)
    def test_resolve_use_a11y_tree_defaults_to_false_when_unset(self):
        self.assertFalse(config.resolve_use_a11y_tree())

    def test_resolve_use_a11y_tree_accepts_truthy_values(self):
        for value in ("true", "TRUE", "True", "1", "yes", "YES"):
            with self.subTest(value=value):
                with mock.patch.dict(
                    "vlm_eval.config.os.environ", {"USE_A11Y_TREE": value}, clear=True
                ):
                    self.assertTrue(config.resolve_use_a11y_tree())

    def test_resolve_use_a11y_tree_accepts_falsy_values(self):
        for value in ("false", "FALSE", "0", "no", ""):
            with self.subTest(value=value):
                with mock.patch.dict(
                    "vlm_eval.config.os.environ", {"USE_A11Y_TREE": value}, clear=True
                ):
                    self.assertFalse(config.resolve_use_a11y_tree())

    @mock.patch.dict("vlm_eval.config.os.environ", {"USE_A11Y_TREE": "on"}, clear=True)
    def test_resolve_use_a11y_tree_exits_for_unrecognised_value(self):
        # A typo like "on" must not silently fall back to vision-only: that
        # would run a full, expensive evaluation under the wrong mode with
        # nothing in the output filename to reveal the mismatch.
        with self.assertRaises(SystemExit) as exc:
            config.resolve_use_a11y_tree()

        self.assertEqual(1, exc.exception.code)


class VlmEvaluatorMainTests(unittest.TestCase):
    @mock.patch("vlm_evaluator.build_expected_keys", return_value=[])
    @mock.patch("vlm_evaluator.finalize_csv", return_value=[])
    @mock.patch("vlm_evaluator.release_lock")
    @mock.patch("vlm_evaluator.acquire_lock")
    @mock.patch("vlm_evaluator.summarize_run", return_value={})
    @mock.patch("vlm_evaluator.evaluate_screen", return_value=1)
    @mock.patch("vlm_evaluator.prepare_csv", return_value=set())
    @mock.patch("vlm_evaluator.api_key_exists", return_value=True)
    @mock.patch("vlm_evaluator.discover_screens", return_value=["clock", "settings_main"])
    @mock.patch.dict(
        "vlm_eval.config.os.environ",
        {
            "VLM_MODEL": "openai/gpt-5.4-nano",
            "VLM_PACE_SECONDS": "1.5",
            # Pinned so the developer's own .env, which load_dotenv reads at
            # import time, cannot change what this test observes.
            "USE_A11Y_TREE": "false",
            "COORD_SPACE": "pixel",
        },
    )
    def test_main_uses_env_model_env_pace_and_discovered_screens(
        self,
        discover_screens_mock,
        api_key_exists_mock,
        prepare_csv_mock,
        evaluate_screen_mock,
        summarize_run_mock,
        acquire_lock_mock,
        release_lock_mock,
        finalize_csv_mock,
        build_expected_keys_mock,
    ):
        fake_stdout = io.StringIO()
        fake_stdout.reconfigure = lambda **kwargs: None
        with mock.patch("sys.stdout", fake_stdout):
            vlm_evaluator.main([])

        self.assertEqual(2, evaluate_screen_mock.call_count)
        output = fake_stdout.getvalue()
        self.assertIn("Mode    : Vision-only", output)
        self.assertIn("Note    : Does not navigate or capture the emulator", output)
        self.assertEqual(
            [
                ("openai/gpt-5.4-nano", "clock", 1.5),
                ("openai/gpt-5.4-nano", "settings_main", 1.5),
            ],
            [
                (call.args[0], call.args[1], call.args[2])
                for call in evaluate_screen_mock.call_args_list
            ],
        )
        # Verify use_a11y_tree defaults to False
        for call in evaluate_screen_mock.call_args_list:
            self.assertFalse(call.kwargs.get("use_a11y_tree", False))

    @mock.patch("vlm_evaluator.build_expected_keys", return_value=[])
    @mock.patch("vlm_evaluator.finalize_csv", return_value=[])
    @mock.patch("vlm_evaluator.release_lock")
    @mock.patch("vlm_evaluator.acquire_lock")
    @mock.patch("vlm_evaluator.summarize_run", return_value={})
    @mock.patch("vlm_evaluator.evaluate_screen", return_value=1)
    @mock.patch("vlm_evaluator.prepare_csv", return_value=set())
    @mock.patch("vlm_evaluator.api_key_exists", return_value=True)
    @mock.patch("vlm_evaluator.discover_screens", return_value=["clock"])
    @mock.patch.dict(
        "vlm_eval.config.os.environ",
        {"VLM_MODEL": "openai/gpt-5.4-nano", "USE_A11Y_TREE": "false"},
    )
    def test_main_resumes_by_default_and_restarts_with_fresh(
        self,
        discover_screens_mock,
        api_key_exists_mock,
        prepare_csv_mock,
        evaluate_screen_mock,
        summarize_run_mock,
        acquire_lock_mock,
        release_lock_mock,
        finalize_csv_mock,
        build_expected_keys_mock,
    ):
        fake_stdout = io.StringIO()
        fake_stdout.reconfigure = lambda **kwargs: None

        with mock.patch("sys.stdout", fake_stdout):
            vlm_evaluator.main([])
        self.assertFalse(prepare_csv_mock.call_args.kwargs["fresh"])

        with mock.patch("sys.stdout", fake_stdout):
            vlm_evaluator.main(["--fresh"])
        self.assertTrue(prepare_csv_mock.call_args.kwargs["fresh"])


if __name__ == "__main__":
    unittest.main()

