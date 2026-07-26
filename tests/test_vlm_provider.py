import base64
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from vlm_eval import provider as vlm_provider


class FakeRateLimitError(Exception):
    pass


class VlmProviderTests(unittest.TestCase):
    @mock.patch.dict(
        "vlm_eval.provider.os.environ",
        {
            "NINEROUTER_BASE_URL": "http://localhost:20128/v1",
            "NINEROUTER_API_KEY": "router-key",
        },
        clear=True,
    )
    def test_register_ninerouter_model_is_idempotent(self):
        try:
            import litellm
        except ImportError:
            self.skipTest("LiteLLM is unavailable in this test environment")

        route = "cx/test-registration-route"
        litellm.open_ai_chat_completion_models.discard(route)
        vlm_provider._register_ninerouter_model(f"9router/{route}")
        vlm_provider._register_ninerouter_model(f"9router/{route}")
        self.assertIn(route, litellm.open_ai_chat_completion_models)

    def test_register_native_model_does_nothing(self):
        try:
            import litellm
        except ImportError:
            self.skipTest("LiteLLM is unavailable in this test environment")

        before = set(litellm.open_ai_chat_completion_models)
        vlm_provider._register_ninerouter_model("openai/gpt-4o-mini")
        self.assertEqual(before, set(litellm.open_ai_chat_completion_models))

    @mock.patch.dict("vlm_eval.provider.os.environ", {}, clear=True)
    def test_request_timeout_defaults_to_120_seconds(self):
        self.assertEqual(120.0, vlm_provider._resolve_request_timeout())

    @mock.patch.dict(
        "vlm_eval.provider.os.environ", {"VLM_REQUEST_TIMEOUT_SECONDS": "30"}, clear=True
    )
    def test_request_timeout_uses_environment(self):
        self.assertEqual(30.0, vlm_provider._resolve_request_timeout())

    def test_request_timeout_rejects_non_positive_values(self):
        with self.assertRaises(ValueError):
            vlm_provider._resolve_request_timeout(0)

    def test_connection_errors_are_retryable(self):
        self.assertTrue(vlm_provider._is_retryable_error(Exception("Connection error.")))

    @mock.patch.dict(
        "vlm_eval.provider.os.environ",
        {
            "NINEROUTER_BASE_URL": "http://localhost:20128",
            "NINEROUTER_API_KEY": "router-key",
        },
        clear=True,
    )
    def test_resolve_9router_config_normalizes_base_url(self):
        self.assertEqual(
            {
                "model": "cx/gpt-5.3-codex",
                "custom_llm_provider": "openai",
                "api_base": "http://localhost:20128/v1",
                "api_key": "router-key",
            },
            vlm_provider.resolve_completion_config("9router/cx/gpt-5.3-codex"),
        )

    @mock.patch.dict("vlm_eval.provider.os.environ", {"NINEROUTER_API_KEY": "key"}, clear=True)
    def test_resolve_9router_requires_base_url(self):
        with self.assertRaisesRegex(ValueError, "NINEROUTER_BASE_URL"):
            vlm_provider.resolve_completion_config("9router/cx/gpt-5.3-codex")

    def test_compatible_model_requires_route_name(self):
        with self.assertRaisesRegex(ValueError, "model route"):
            vlm_provider.resolve_completion_config("9router/")

    def test_normalize_ninerouter_base_url_accepts_host_and_v1_forms(self):
        for value in (
            "http://localhost:20128",
            "http://localhost:20128/",
            "http://localhost:20128/v1",
            "http://localhost:20128/v1/",
        ):
            with self.subTest(value=value):
                self.assertEqual(
                    "http://localhost:20128/v1",
                    vlm_provider._normalize_ninerouter_base_url(value),
                )

    @mock.patch.dict("vlm_eval.provider.os.environ", {}, clear=True)
    def test_compatible_model_reports_missing_configuration(self):
        error = vlm_provider.model_configuration_error("9router/cx/gpt-5.3-codex")
        self.assertIn("NINEROUTER_BASE_URL", error)
        self.assertIn("NINEROUTER_API_KEY", error)

    @mock.patch.dict("vlm_eval.provider.os.environ", {}, clear=True)
    def test_native_model_configuration_is_unchanged(self):
        for model in (
            "openai/gpt-4o-mini",
            "gemini/gemini-2.5-pro",
            "anthropic/claude-sonnet",
        ):
            with self.subTest(model=model):
                self.assertIsNone(vlm_provider.model_configuration_error(model))

        self.assertEqual(
            {"model": "anthropic/claude-sonnet"},
            vlm_provider.resolve_completion_config("anthropic/claude-sonnet"),
        )

    def test_image_to_data_url_encodes_png_bytes(self):
        png_bytes = b"\x89PNG\r\n\x1a\nfake"

        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "screen.png"
            image_path.write_bytes(png_bytes)

            data_url = vlm_provider.image_to_data_url(image_path)

        expected = base64.b64encode(png_bytes).decode("ascii")
        self.assertEqual(f"data:image/png;base64,{expected}", data_url)

    @mock.patch("vlm_eval.provider._completion")
    def test_call_vlm_sends_litellm_vision_message(self, completion_mock):
        completion_mock.return_value = {
            "choices": [{"message": {"content": "[123, 456]"}}],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "screen.png"
            image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")

            response_text = vlm_provider.call_vlm(
                "openai/gpt-4o-mini",
                image_path,
                "Find Settings",
            )

        self.assertEqual("[123, 456]", response_text)
        completion_mock.assert_called_once()
        call_kwargs = completion_mock.call_args.kwargs
        self.assertEqual("openai/gpt-4o-mini", call_kwargs["model"])
        content = call_kwargs["messages"][0]["content"]
        self.assertEqual({"type": "text", "text": "Find Settings"}, content[0])
        self.assertEqual("image_url", content[1]["type"])
        self.assertTrue(
            content[1]["image_url"]["url"].startswith("data:image/png;base64,")
        )

    @mock.patch.dict(
        "vlm_eval.provider.os.environ",
        {
            "NINEROUTER_BASE_URL": "http://localhost:20128/v1/",
            "NINEROUTER_API_KEY": "router-key",
        },
        clear=True,
    )
    @mock.patch("vlm_eval.provider._register_ninerouter_model")
    @mock.patch("vlm_eval.provider._completion")
    def test_call_vlm_passes_9router_compatibility_arguments(
        self, completion_mock, register_model_mock
    ):
        completion_mock.return_value = {"choices": [{"message": {"content": "[1, 2]"}}]}

        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "screen.png"
            image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
            vlm_provider.call_vlm("9router/cx/gpt-5.3-codex", image_path, "Find it")

        call_kwargs = completion_mock.call_args.kwargs
        self.assertEqual("cx/gpt-5.3-codex", call_kwargs["model"])
        self.assertEqual("openai", call_kwargs["custom_llm_provider"])
        self.assertEqual("http://localhost:20128/v1", call_kwargs["api_base"])
        self.assertEqual("router-key", call_kwargs["api_key"])
        self.assertEqual(120.0, call_kwargs["timeout"])

    @mock.patch.dict(
        "vlm_eval.provider.os.environ",
        {
            "NINEROUTER_BASE_URL": "http://localhost:20128/v1",
            "NINEROUTER_API_KEY": "router-key",
        },
        clear=True,
    )
    def test_real_litellm_mock_completion_has_no_provider_warning(self):
        try:
            import litellm
        except ImportError:
            self.skipTest("LiteLLM is unavailable in this test environment")

        route = "cx/no-warning-route"
        litellm.open_ai_chat_completion_models.discard(route)

        output = StringIO()
        with redirect_stdout(output):
            vlm_provider._register_ninerouter_model(f"9router/{route}")
            response = litellm.completion(
                model=route,
                custom_llm_provider="openai",
                api_base="http://localhost:20128/v1",
                api_key="router-key",
                messages=[{"role": "user", "content": "hi"}],
                mock_response="ok",
            )

        self.assertNotIn("Provider List", output.getvalue())
        self.assertEqual("ok", response.choices[0].message.content)

    @mock.patch("vlm_eval.provider.time.sleep")
    @mock.patch("vlm_eval.provider._completion")
    def test_call_vlm_retries_timeout_then_succeeds(self, completion_mock, sleep_mock):
        class FakeReadTimeout(Exception):
            pass

        completion_mock.side_effect = [
            FakeReadTimeout("read timed out"),
            {"choices": [{"message": {"content": "[3, 4]"}}]},
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "screen.png"
            image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
            response_text = vlm_provider.call_vlm(
                "openai/gpt-4o-mini", image_path, "Find it", max_retries=1
            )

        self.assertEqual("[3, 4]", response_text)
        self.assertEqual(2, completion_mock.call_count)
        sleep_mock.assert_called_once_with(0.5)

    def test_extract_response_text_supports_object_response(self):
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="[10, 20]"),
                )
            ]
        )

        self.assertEqual("[10, 20]", vlm_provider._extract_response_text(response))

    def test_extract_response_text_supports_text_part_list(self):
        response = {
            "choices": [
                {
                    "message": {
                        "content": [
                            {"type": "text", "text": "[7, "},
                            {"type": "text", "text": "8]"},
                        ],
                    }
                }
            ]
        }

        self.assertEqual("[7, 8]", vlm_provider._extract_response_text(response))

    @mock.patch("vlm_eval.provider.time.sleep")
    @mock.patch("vlm_eval.provider._completion")
    def test_call_vlm_retries_rate_limit_then_succeeds(self, completion_mock, sleep_mock):
        completion_mock.side_effect = [
            FakeRateLimitError("Please try again in 249ms."),
            {"choices": [{"message": {"content": "[321, 654]"}}]},
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "screen.png"
            image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")

            response_text = vlm_provider.call_vlm(
                "openai/gpt-4o-mini",
                image_path,
                "Find Timer",
                max_retries=3,
            )

        self.assertEqual("[321, 654]", response_text)
        self.assertEqual(2, completion_mock.call_count)
        sleep_mock.assert_called_once_with(0.249)

    @mock.patch("vlm_eval.provider.time.sleep")
    @mock.patch("vlm_eval.provider._completion")
    def test_call_vlm_raises_after_repeated_rate_limits(self, completion_mock, sleep_mock):
        completion_mock.side_effect = FakeRateLimitError("Rate limit reached")

        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "screen.png"
            image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")

            with self.assertRaises(FakeRateLimitError):
                vlm_provider.call_vlm(
                    "openai/gpt-4o-mini",
                    image_path,
                    "Find Timer",
                    max_retries=2,
                )

        self.assertEqual(3, completion_mock.call_count)
        self.assertEqual(2, sleep_mock.call_count)


if __name__ == "__main__":
    unittest.main()
