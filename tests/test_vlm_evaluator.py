import unittest
from unittest import mock

import vlm_evaluator


class VlmEvaluatorConfigTests(unittest.TestCase):
    @mock.patch.dict("vlm_evaluator.os.environ", {"VLM_MODEL": "openai/gpt-4o-mini"})
    def test_resolve_model_prefers_cli_model(self):
        self.assertEqual(
            "gemini/gemini-2.5-pro",
            vlm_evaluator.resolve_model("gemini/gemini-2.5-pro"),
        )

    @mock.patch.dict("vlm_evaluator.os.environ", {"VLM_MODEL": "openai/gpt-4o-mini"})
    def test_resolve_model_uses_env_model(self):
        self.assertEqual(
            "openai/gpt-4o-mini",
            vlm_evaluator.resolve_model(None),
        )

    @mock.patch.dict("vlm_evaluator.os.environ", {}, clear=True)
    def test_resolve_model_exits_without_cli_or_env_model(self):
        with self.assertRaises(SystemExit) as exc:
            vlm_evaluator.resolve_model(None)

        self.assertEqual(1, exc.exception.code)

    @mock.patch.dict("vlm_evaluator.os.environ", {"VLM_PACE_SECONDS": "0.5"})
    def test_resolve_pace_seconds_prefers_cli_value(self):
        self.assertEqual(1.25, vlm_evaluator.resolve_pace_seconds("1.25"))

    @mock.patch.dict("vlm_evaluator.os.environ", {"VLM_PACE_SECONDS": "0.5"})
    def test_resolve_pace_seconds_uses_env_value(self):
        self.assertEqual(0.5, vlm_evaluator.resolve_pace_seconds(None))

    @mock.patch.dict("vlm_evaluator.os.environ", {}, clear=True)
    def test_resolve_pace_seconds_defaults_to_zero(self):
        self.assertEqual(0.0, vlm_evaluator.resolve_pace_seconds(None))

    @mock.patch.dict("vlm_evaluator.os.environ", {"VLM_PACE_SECONDS": "-1"})
    def test_resolve_pace_seconds_exits_for_negative_env_value(self):
        with self.assertRaises(SystemExit) as exc:
            vlm_evaluator.resolve_pace_seconds(None)

        self.assertEqual(1, exc.exception.code)

    @mock.patch.dict("vlm_evaluator.os.environ", {"VLM_PACE_SECONDS": "fast"})
    def test_resolve_pace_seconds_exits_for_non_number_env_value(self):
        with self.assertRaises(SystemExit) as exc:
            vlm_evaluator.resolve_pace_seconds(None)

        self.assertEqual(1, exc.exception.code)


if __name__ == "__main__":
    unittest.main()
