import io
import unittest
from unittest import mock

import vlm_evaluator
from vlm_eval import config


class VlmEvaluatorConfigTests(unittest.TestCase):
    @mock.patch.dict("vlm_eval.config.os.environ", {"VLM_MODEL": "openai/gpt-4o-mini"})
    def test_resolve_model_prefers_cli_model(self):
        self.assertEqual(
            "gemini/gemini-2.5-pro",
            config.resolve_model("gemini/gemini-2.5-pro"),
        )

    @mock.patch.dict("vlm_eval.config.os.environ", {"VLM_MODEL": "openai/gpt-4o-mini"})
    def test_resolve_model_uses_env_model(self):
        self.assertEqual(
            "openai/gpt-4o-mini",
            config.resolve_model(None),
        )

    @mock.patch.dict("vlm_eval.config.os.environ", {}, clear=True)
    def test_resolve_model_exits_without_cli_or_env_model(self):
        with self.assertRaises(SystemExit) as exc:
            config.resolve_model(None)

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


class VlmEvaluatorMainTests(unittest.TestCase):
    @mock.patch("vlm_evaluator.evaluate_screen", return_value=1)
    @mock.patch("vlm_evaluator.init_csv")
    @mock.patch("vlm_evaluator.api_key_exists", return_value=True)
    @mock.patch("vlm_evaluator.discover_screens", return_value=["clock", "settings_main"])
    @mock.patch.dict(
        "vlm_eval.config.os.environ",
        {"VLM_MODEL": "openai/gpt-5.4-nano", "VLM_PACE_SECONDS": "1.5"},
    )
    def test_main_uses_env_model_env_pace_and_discovered_screens(
        self,
        discover_screens_mock,
        api_key_exists_mock,
        init_csv_mock,
        evaluate_screen_mock,
    ):
        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            vlm_evaluator.main()

        self.assertEqual(2, evaluate_screen_mock.call_count)
        output = stdout.getvalue()
        self.assertIn("Mode    : OFFLINE evaluation from dataset/images + dataset/labels", output)
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


if __name__ == "__main__":
    unittest.main()
