import base64
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from evaluation.providers import hosted as vlm_provider
from evaluation.providers import retry as vlm_retry


class FakeRateLimitError(Exception):
    pass


class SamplingEnvIsolation:
    """Unset the sampling knobs so a local .env cannot decide a default.

    Every one of these is read straight from os.environ, which importing
    evaluation.workflow populates from the developer's own .env via load_dotenv.
    A local VLM_THINKING=disabled would otherwise decide what the "by default"
    tests see -- and only once some other test module had pulled workflow in
    first, so the suite passed or failed depending on discovery order. Unset
    rather than blanked: an empty VLM_TEMPERATURE means "omit the parameter",
    which is not the same as the default. setUp runs before the method-level
    patch.dict decorators, so a test that does want a value still gets one.
    """

    SAMPLING_ENV_VARS = (
        vlm_retry.TEMPERATURE_ENV_VAR,
        vlm_retry.MAX_TOKENS_ENV_VAR,
        vlm_retry.THINKING_ENV_VAR,
        vlm_retry.STRUCTURED_COORDS_ENV_VAR,
    )

    def setUp(self):
        super().setUp()
        saved = {
            name: os.environ.pop(name)
            for name in self.SAMPLING_ENV_VARS
            if name in os.environ
        }
        self.addCleanup(os.environ.update, saved)


class VlmProviderTests(unittest.TestCase):
    @mock.patch.dict(
        "evaluation.providers.hosted.os.environ",
        {
            "NINEROUTER_BASE_URL": "http://localhost:20128/v1",
            "NINEROUTER_API_KEY": "router-key",
        },
        clear=True,
    )
    def test_register_compatible_model_is_idempotent(self):
        try:
            import litellm
        except ImportError:
            self.skipTest("LiteLLM is unavailable in this test environment")

        route = "cx/test-registration-route"
        litellm.open_ai_chat_completion_models.discard(route)
        vlm_provider._register_compatible_model(f"9router/{route}")
        vlm_provider._register_compatible_model(f"9router/{route}")
        self.assertIn(route, litellm.open_ai_chat_completion_models)

    def test_register_native_model_does_nothing(self):
        try:
            import litellm
        except ImportError:
            self.skipTest("LiteLLM is unavailable in this test environment")

        before = set(litellm.open_ai_chat_completion_models)
        vlm_provider._register_compatible_model("openai/gpt-4o-mini")
        self.assertEqual(before, set(litellm.open_ai_chat_completion_models))

    @mock.patch.dict("evaluation.providers.hosted.os.environ", {}, clear=True)
    def test_request_timeout_defaults_to_120_seconds(self):
        self.assertEqual(120.0, vlm_provider._resolve_request_timeout())

    @mock.patch.dict(
        "evaluation.providers.hosted.os.environ", {"VLM_REQUEST_TIMEOUT_SECONDS": "30"}, clear=True
    )
    def test_request_timeout_uses_environment(self):
        self.assertEqual(30.0, vlm_provider._resolve_request_timeout())

    def test_request_timeout_rejects_non_positive_values(self):
        with self.assertRaises(ValueError):
            vlm_provider._resolve_request_timeout(0)

    def test_connection_errors_are_retryable(self):
        self.assertTrue(vlm_provider._is_retryable_error(Exception("Connection error.")))

    @mock.patch.dict(
        "evaluation.providers.hosted.os.environ",
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

    @mock.patch.dict("evaluation.providers.hosted.os.environ", {"NINEROUTER_API_KEY": "key"}, clear=True)
    def test_resolve_9router_requires_base_url(self):
        with self.assertRaisesRegex(ValueError, "NINEROUTER_BASE_URL"):
            vlm_provider.resolve_completion_config("9router/cx/gpt-5.3-codex")

    def test_compatible_model_requires_route_name(self):
        with self.assertRaisesRegex(ValueError, "model route"):
            vlm_provider.resolve_completion_config("9router/")

    def test_normalize_compatible_base_url_accepts_host_and_v1_forms(self):
        for value in (
            "http://localhost:20128",
            "http://localhost:20128/",
            "http://localhost:20128/v1",
            "http://localhost:20128/v1/",
        ):
            with self.subTest(value=value):
                self.assertEqual(
                    "http://localhost:20128/v1",
                    vlm_provider._normalize_compatible_base_url(value),
                )

    @mock.patch.dict(
        "evaluation.providers.hosted.os.environ",
        {
            "OPENAI_COMPATIBLE_BASE_URL": "https://provider.example.com/v1/",
            "OPENAI_COMPATIBLE_API_KEY": "provider-key",
        },
        clear=True,
    )
    def test_resolve_generic_compatible_model_preserves_nested_model_id(self):
        self.assertEqual(
            {
                "model": "vendor/model-with-slashes",
                "custom_llm_provider": "openai",
                "api_base": "https://provider.example.com/v1",
                "api_key": "provider-key",
            },
            vlm_provider.resolve_completion_config(
                "openai_compatible/vendor/model-with-slashes"
            ),
        )

    @mock.patch.dict("evaluation.providers.hosted.os.environ", {}, clear=True)
    def test_compatible_model_reports_missing_configuration(self):
        error = vlm_provider.model_configuration_error("9router/cx/gpt-5.3-codex")
        self.assertIn("NINEROUTER_BASE_URL", error)
        self.assertIn("NINEROUTER_API_KEY", error)

    @mock.patch.dict(
        "evaluation.providers.hosted.os.environ",
        {
            "OPENAI_COMPATIBLE_BASE_URL": "https://provider.example.com/v1",
            "OPENAI_COMPATIBLE_API_KEY": "your-compatible-provider-key-here",
        },
        clear=True,
    )
    def test_generic_compatible_placeholder_key_is_missing(self):
        error = vlm_provider.model_configuration_error(
            "openai_compatible/my-provider-model"
        )
        self.assertIn("OPENAI_COMPATIBLE_API_KEY", error)

    @mock.patch.dict("evaluation.providers.hosted.os.environ", {}, clear=True)
    def test_native_model_configuration_is_unchanged(self):
        self.assertIsNone(vlm_provider.model_configuration_error("openai/gpt-4o-mini"))
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

    @mock.patch("evaluation.providers.hosted._completion")
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
        "evaluation.providers.hosted.os.environ",
        {
            "NINEROUTER_BASE_URL": "http://localhost:20128/v1/",
            "NINEROUTER_API_KEY": "router-key",
        },
        clear=True,
    )
    @mock.patch("evaluation.providers.hosted._register_compatible_model")
    @mock.patch("evaluation.providers.hosted._completion")
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
        "evaluation.providers.hosted.os.environ",
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
            vlm_provider._register_compatible_model(f"9router/{route}")
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

    @mock.patch("evaluation.providers.hosted.time.sleep")
    @mock.patch("evaluation.providers.hosted._completion")
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

    @mock.patch("evaluation.providers.hosted.time.sleep")
    @mock.patch("evaluation.providers.hosted._completion")
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

    def test_build_ferret_prompt_vision_mode_matches_original_string(self):
        # Regression lock: this exact string is what Ferret-UI was fine-tuned
        # on, and must be byte-identical whether or not tree mode exists.
        self.assertEqual(
            "Provide the bounding box of the text 'Bluetooth'.",
            vlm_provider.build_ferret_prompt("Bluetooth", None, 1080, 2219),
        )
        self.assertEqual(
            "Provide the bounding box of the text 'Bluetooth'.",
            vlm_provider.build_ferret_prompt("Bluetooth", [], 1080, 2219),
        )

    def test_build_ferret_prompt_tree_mode_ends_with_vision_line(self):
        rows = [("Wi-Fi", [0, 0, 100, 50])]
        prompt = vlm_provider.build_ferret_prompt("Bluetooth", rows, 1080, 2219)

        self.assertTrue(
            prompt.endswith("Provide the bounding box of the text 'Bluetooth'.")
        )
        self.assertTrue(prompt.startswith("Nearby elements:\n"))

    def test_build_ferret_prompt_scales_boxes_to_vocab_1000(self):
        # Matches ferret_ui/model_UI.py:126-140's own scaling: multiply by
        # VOCAB_IMAGE_W/img_w (and H analogously), then int()-truncate --
        # not round.
        rows = [("Wi-Fi", [10, 20, 1070, 2200])]
        prompt = vlm_provider.build_ferret_prompt("Bluetooth", rows, 1080, 2219)

        ratio_w = 1000 / 1080
        ratio_h = 1000 / 2219
        expected = (
            f'"Wi-Fi" [{int(10 * ratio_w)}, {int(20 * ratio_h)}, '
            f'{int(1070 * ratio_w)}, {int(2200 * ratio_h)}]'
        )
        self.assertIn(expected, prompt)
        # Single bracket, comma-space -- Ferret's own input convention, not
        # the hosted-model tree's "[x1,y1][x2,y2]" pixel format.
        self.assertNotIn("][", prompt)

    def test_build_ferret_prompt_excludes_target_row(self):
        # The leak-fix exclusion (collect_tree_rows) must hold through this
        # rendering too, including the content_desc-only fallback case.
        rows = [("World Clock", [216, 2051, 432, 2219]), ("8:30 AM", [84, 231, 429, 414])]
        # Simulate collect_tree_rows(..., exclude_text="World Clock") having
        # already dropped the excluded row before it reaches the prompt builder.
        rows = [r for r in rows if r[0] != "World Clock"]

        prompt = vlm_provider.build_ferret_prompt("World Clock", rows, 1080, 2219)

        self.assertNotIn("[216,", prompt)
        self.assertIn('"8:30 AM"', prompt)

    def test_build_ferret_prompt_preserves_apostrophes_in_target(self):
        prompt = vlm_provider.build_ferret_prompt("Today's Deals", None, 1080, 2219)
        self.assertEqual(
            "Provide the bounding box of the text 'Today's Deals'.",
            prompt,
        )

    def test_build_ferret_prompt_sanitizes_image_token_and_newlines(self):
        rows = [("weird <image>\nlabel", [0, 0, 10, 10])]
        prompt = vlm_provider.build_ferret_prompt("Bluetooth", rows, 1080, 2219)
        self.assertNotIn("<image>", prompt)
        self.assertNotIn("weird \nlabel", prompt)

    def test_parse_ferret_bbox_prefers_double_bracket(self):
        self.assertEqual(
            (100.0, 200.0, 300.0, 400.0),
            vlm_provider._parse_ferret_bbox("The box is [[100, 200, 300, 400]]"),
        )

    def test_parse_ferret_bbox_falls_back_to_single_bracket(self):
        self.assertEqual(
            (10.0, 20.0, 30.5, 40.0),
            vlm_provider._parse_ferret_bbox("sure, [10, 20, 30.5, 40]"),
        )

    def test_parse_ferret_bbox_prefers_last_single_bracket_match(self):
        # Once the prompt itself can contain bracketed boxes (an injected
        # tree), a model that echoes context must not have that echoed box
        # mistaken for its actual answer.
        self.assertEqual(
            (50.0, 60.0, 70.0, 80.0),
            vlm_provider._parse_ferret_bbox(
                "context had [1, 2, 3, 4], my answer is [50, 60, 70, 80]"
            ),
        )

    def test_parse_ferret_bbox_returns_none_when_unparseable(self):
        self.assertIsNone(vlm_provider._parse_ferret_bbox("no bounding box here"))

    @mock.patch("evaluation.providers.hosted.urllib.request.urlopen")
    def test_call_vlm_ferret_vision_mode_sends_unchanged_prompt(self, urlopen_mock):
        import json as _json

        response = mock.MagicMock()
        response.read.return_value = _json.dumps(
            {"text": "[[100, 200, 300, 400]]", "max_new_tokens": 1024}
        ).encode("utf-8")
        response.__enter__.return_value = response
        urlopen_mock.return_value = response

        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "screen.png"
            image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")

            vlm_provider.call_vlm(
                "local/ferret-ui-llama8b",
                image_path,
                "irrelevant when target_text is provided",
                target_text="Bluetooth",
                tree_rows=None,
                img_width=1080,
                img_height=2219,
            )

        sent_request = urlopen_mock.call_args.args[0]
        sent_body = _json.loads(sent_request.data.decode("utf-8"))
        self.assertEqual(
            "Provide the bounding box of the text 'Bluetooth'.",
            sent_body["prompt"],
        )

    @mock.patch("evaluation.providers.hosted.urllib.request.urlopen")
    def test_call_vlm_ferret_tree_mode_includes_tree_text(self, urlopen_mock):
        import json as _json

        response = mock.MagicMock()
        response.read.return_value = _json.dumps(
            {"text": "[[100, 200, 300, 400]]", "max_new_tokens": 1024}
        ).encode("utf-8")
        response.__enter__.return_value = response
        urlopen_mock.return_value = response

        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "screen.png"
            image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")

            vlm_provider.call_vlm(
                "local/ferret-ui-llama8b",
                image_path,
                "irrelevant when target_text is provided",
                target_text="Bluetooth",
                tree_rows=[("Wi-Fi", [0, 0, 100, 50])],
                img_width=1080,
                img_height=2219,
            )

        sent_request = urlopen_mock.call_args.args[0]
        sent_body = _json.loads(sent_request.data.decode("utf-8"))
        self.assertIn("Nearby elements:", sent_body["prompt"])
        self.assertIn('"Wi-Fi"', sent_body["prompt"])
        self.assertTrue(
            sent_body["prompt"].endswith(
                "Provide the bounding box of the text 'Bluetooth'."
            )
        )

    @mock.patch("evaluation.providers.hosted.urllib.request.urlopen")
    def test_call_vlm_ferret_converts_vocab_scale_response_to_pixel_center(
        self, urlopen_mock
    ):
        import json as _json

        response = mock.MagicMock()
        response.read.return_value = _json.dumps(
            {"text": "[[0, 0, 1000, 1000]]", "max_new_tokens": 1024}
        ).encode("utf-8")
        response.__enter__.return_value = response
        urlopen_mock.return_value = response

        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "screen.png"
            image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")

            result = vlm_provider.call_vlm(
                "local/ferret-ui-llama8b",
                image_path,
                "irrelevant when target_text is provided",
                target_text="Bluetooth",
                img_width=1080,
                img_height=2219,
            )

        self.assertEqual("[540.0, 1109.5]", result)

    @mock.patch("evaluation.providers.hosted.urllib.request.urlopen")
    def test_call_vlm_ferret_surfaces_server_budget_error(self, urlopen_mock):
        import urllib.error

        error_body = mock.MagicMock()
        error_body.read.return_value = b'{"error": "context window exceeded"}'
        urlopen_mock.side_effect = urllib.error.HTTPError(
            "http://localhost:8000/", 400, "Bad Request", {}, error_body
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "screen.png"
            image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")

            with self.assertRaisesRegex(RuntimeError, "context window exceeded"):
                vlm_provider.call_vlm(
                    "local/ferret-ui-llama8b",
                    image_path,
                    "irrelevant when target_text is provided",
                    target_text="Bluetooth",
                    tree_rows=[("Wi-Fi", [0, 0, 100, 50])],
                    img_width=1080,
                    img_height=2219,
                )

    def test_uses_normalized_coords_matches_native_and_9router_forms(self):
        self.assertTrue(vlm_provider._uses_normalized_coords("gemini/gemini-2.5-flash"))
        self.assertTrue(vlm_provider._uses_normalized_coords("9router/ag/gemini-3-flash"))
        self.assertTrue(vlm_provider._uses_normalized_coords("9router/ag/gemini-pro-agent"))

    def test_uses_normalized_coords_matches_qwen_and_glm_routes(self):
        # The reason the registry is a predicate rather than a Gemini check:
        # these OpenRouter models answer on the same 0-1000 grid and scored
        # ~0% while they were treated as pixel-space.
        self.assertTrue(vlm_provider._uses_normalized_coords(
            "openrouter/qwen/qwen3-vl-235b-a22b-instruct"))
        self.assertTrue(vlm_provider._uses_normalized_coords(
            "openrouter/z-ai/glm-5v-turbo"))

    def test_uses_normalized_coords_rejects_other_families(self):
        self.assertFalse(vlm_provider._uses_normalized_coords("openai/gpt-4o-mini"))
        self.assertFalse(vlm_provider._uses_normalized_coords("9router/cx/gpt-5.5"))
        self.assertFalse(vlm_provider._uses_normalized_coords(
            "anthropic/claude-3-5-sonnet-latest"))

    def test_uses_normalized_coords_excludes_ferret_which_self_converts(self):
        # Ferret-UI also replies on a 1000 scale, but call_vlm's Ferret branch
        # already converts it; matching here would convert a second time.
        self.assertFalse(vlm_provider._uses_normalized_coords("local/ferret-ui-llama8b"))

    def test_validate_coord_space_allows_pixel_for_any_model(self):
        self.assertEqual("pixel", vlm_provider.validate_coord_space(
            "9router/ag/gemini-3-flash", "pixel"))
        self.assertEqual("pixel", vlm_provider.validate_coord_space(
            "openai/gpt-4o-mini", "pixel"))

    def test_validate_coord_space_allows_override_for_unregistered_model(self):
        self.assertEqual("norm1000", vlm_provider.validate_coord_space(
            "openrouter/some/new-vlm", "norm1000"))

    def test_validate_coord_space_rejects_override_on_self_converting_models(self):
        # The double-conversion guard: COORD_SPACE is one global value per run
        # while VLM_MODEL may list several models, so this must fail loudly
        # rather than silently squash predictions into the top-left corner.
        for model in ("9router/ag/gemini-3-flash",
                      "gemini/gemini-2.5-flash",
                      "openrouter/qwen/qwen3-vl-235b-a22b-instruct",
                      "local/ferret-ui-llama8b"):
            with self.subTest(model=model):
                with self.assertRaises(SystemExit):
                    vlm_provider.validate_coord_space(model, "norm1000")

    def test_classify_normalized_reply_reports_in_range_as_normalized(self):
        self.assertEqual(
            vlm_provider.GEMINI_SPACE_NORMALIZED,
            vlm_provider._classify_normalized_reply("[500, 500]"),
        )

    def test_classify_normalized_reply_flags_out_of_range_as_pixel_space(self):
        # y=1109 on a 2219px-tall image cannot be a 0-1000 normalized value
        # AND also be this reply's intended pixel answer at the same time --
        # a value over 1000 is unambiguous pixel-space non-compliance.
        self.assertEqual(
            vlm_provider.GEMINI_SPACE_PIXEL,
            vlm_provider._classify_normalized_reply("[166, 1109]"),
        )

    def test_classify_normalized_reply_flags_unparseable_as_unverified(self):
        self.assertEqual(
            vlm_provider.GEMINI_SPACE_UNVERIFIED,
            vlm_provider._classify_normalized_reply("no coordinates here"),
        )

    def test_build_normalized_prompt_states_normalized_scale_and_example(self):
        prompt = vlm_provider.build_normalized_prompt("Bluetooth", None, 1080, 2219)
        self.assertIn("0-1000", prompt)
        self.assertIn("[500, 500]", prompt)
        self.assertIn("'Bluetooth'", prompt)
        self.assertNotIn("Your previous answer", prompt)

    def test_build_normalized_prompt_strict_adds_correction(self):
        prompt = vlm_provider.build_normalized_prompt(
            "Bluetooth", None, 1080, 2219, strict=True)
        self.assertIn("Your previous answer used raw pixel coordinates", prompt)

    @mock.patch("evaluation.providers.hosted._completion")
    def test_call_vlm_returns_normalized_reply_verbatim(self, completion_mock):
        completion_mock.return_value = {
            "choices": [{"message": {"content": "[500, 500]"}}],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "screen.png"
            image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")

            coord_space_out: dict = {}
            response_text = vlm_provider.call_vlm(
                "gemini/gemini-2.5-flash",
                image_path,
                "irrelevant when target_text is provided",
                target_text="Bluetooth",
                img_width=1080,
                img_height=2219,
                coord_space_out=coord_space_out,
            )

        # Verbatim, NOT converted: the runner converts using coord_space_out,
        # so the model's own answer survives into raw_response and stays
        # re-scorable offline.
        self.assertEqual("[500, 500]", response_text)
        self.assertEqual(vlm_provider.GEMINI_SPACE_NORMALIZED, coord_space_out["value"])
        sent_prompt = completion_mock.call_args.kwargs["messages"][0]["content"][0]["text"]
        self.assertIn("0-1000", sent_prompt)

    @mock.patch("evaluation.providers.hosted.time.sleep")
    @mock.patch("evaluation.providers.hosted._completion")
    def test_call_vlm_retries_normalized_model_pixel_space_reply_then_succeeds(
        self, completion_mock, sleep_mock
    ):
        completion_mock.side_effect = [
            {"choices": [{"message": {"content": "[166, 1109]"}}]},
            {"choices": [{"message": {"content": "[500, 500]"}}]},
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "screen.png"
            image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")

            coord_space_out: dict = {}
            response_text = vlm_provider.call_vlm(
                "9router/ag/gemini-3-flash",
                image_path,
                "irrelevant when target_text is provided",
                target_text="Bluetooth",
                img_width=1080,
                img_height=2219,
                max_retries=1,
                coord_space_out=coord_space_out,
            )

        self.assertEqual("[500, 500]", response_text)
        self.assertEqual(vlm_provider.GEMINI_SPACE_NORMALIZED, coord_space_out["value"])
        self.assertEqual(2, completion_mock.call_count)
        # The retried prompt must be the stricter restatement, not identical.
        second_prompt = completion_mock.call_args_list[1].kwargs["messages"][0]["content"][0]["text"]
        self.assertIn("Your previous answer used raw pixel coordinates", second_prompt)

    @mock.patch("evaluation.providers.hosted._completion")
    def test_call_vlm_flags_reply_still_pixel_space_after_retries(
        self, completion_mock
    ):
        completion_mock.return_value = {
            "choices": [{"message": {"content": "[166, 1109]"}}],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "screen.png"
            image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")

            coord_space_out: dict = {}
            response_text = vlm_provider.call_vlm(
                "gemini/gemini-2.5-flash",
                image_path,
                "irrelevant when target_text is provided",
                target_text="Bluetooth",
                img_width=1080,
                img_height=2219,
                max_retries=0,
                coord_space_out=coord_space_out,
            )

        # Not silently coerced: the pixel-looking reply is returned unconverted.
        self.assertEqual("[166, 1109]", response_text)
        self.assertEqual(vlm_provider.GEMINI_SPACE_PIXEL, coord_space_out["value"])
        self.assertEqual(1, completion_mock.call_count)

    @mock.patch("evaluation.providers.hosted._completion")
    def test_call_vlm_pixel_space_model_unaffected_by_normalized_path(self, completion_mock):
        completion_mock.return_value = {
            "choices": [{"message": {"content": "[123, 456]"}}],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "screen.png"
            image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")

            coord_space_out: dict = {}
            response_text = vlm_provider.call_vlm(
                "9router/cx/gpt-5.5",
                image_path,
                "Find Bluetooth",
                target_text="Bluetooth",
                img_width=1080,
                img_height=2219,
                coord_space_out=coord_space_out,
            )

        # GPT rows must be untouched: no conversion, no coord_space set, and
        # the original prompt is sent verbatim.
        self.assertEqual("[123, 456]", response_text)
        self.assertEqual({}, coord_space_out)
        sent_prompt = completion_mock.call_args.kwargs["messages"][0]["content"][0]["text"]
        self.assertEqual("Find Bluetooth", sent_prompt)

    @mock.patch("evaluation.providers.hosted.time.sleep")
    @mock.patch("evaluation.providers.hosted._completion")
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


class ReplyBudgetAndThinkingTests(SamplingEnvIsolation, unittest.TestCase):
    """max_tokens / thinking plumbing, and the truncation guard.

    A truncated reply used to reach the coordinate parser, fail to parse, and
    score as a grounding miss. On a model that thinks, truncation gets likelier
    the longer the model reasons, so those misses would concentrate on the hard
    targets and overstate the accessibility profiles' effect.
    """

    def _png(self, tmp_dir):
        path = Path(tmp_dir) / "screen.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
        return path

    def _call(self, model="openai/gpt-4o-mini", finish_reason="stop"):
        with mock.patch("evaluation.providers.hosted._completion") as completion, \
             mock.patch("evaluation.providers.hosted._register_compatible_model"), \
             tempfile.TemporaryDirectory() as tmp_dir:
            completion.return_value = {
                "choices": [{"finish_reason": finish_reason,
                             "message": {"content": "[1, 2]"}}],
            }
            text = vlm_provider.call_vlm(model, self._png(tmp_dir), "Find Settings")
            return text, completion.call_args.kwargs

    def test_no_budget_is_sent_by_default(self):
        """The already-collected roster ran with no max_tokens; keep it that way."""
        _, kwargs = self._call()
        self.assertNotIn("max_tokens", kwargs)

    @mock.patch.dict(os.environ, {"VLM_MAX_TOKENS": "8192"}, clear=False)
    def test_budget_is_sent_when_configured(self):
        _, kwargs = self._call()
        self.assertEqual(8192, kwargs["max_tokens"])

    def test_thinking_is_not_sent_by_default(self):
        _, kwargs = self._call("anthropic/claude-opus-5")
        self.assertNotIn("thinking", kwargs)

    @mock.patch.dict(os.environ, {"VLM_THINKING": "disabled"}, clear=False)
    def test_thinking_goes_only_to_anthropic_models(self):
        _, anthropic_kwargs = self._call("anthropic/claude-opus-5")
        self.assertEqual({"type": "disabled"}, anthropic_kwargs["thinking"])

        # Any other provider would reject it as an unrecognised parameter.
        _, other_kwargs = self._call("openai/gpt-4o-mini")
        self.assertNotIn("thinking", other_kwargs)

    @mock.patch.dict(os.environ, {"VLM_THINKING": "sometimes"}, clear=False)
    def test_an_unrecognised_thinking_mode_exits_rather_than_guessing(self):
        with self.assertRaises(SystemExit):
            self._call("anthropic/claude-opus-5")

    def test_truncated_reply_raises_instead_of_being_scored(self):
        with self.assertRaises(vlm_provider.TruncatedReplyError):
            self._call(finish_reason="length")

    def test_truncation_is_not_retried(self):
        """The same budget truncates again; it must surface as an api_error."""
        from evaluation.providers.retry import is_retryable_error

        self.assertFalse(is_retryable_error(vlm_provider.TruncatedReplyError("x")))


class ImageCapTests(unittest.TestCase):
    """Per-model image caps, and the coordinate space they silently create.

    A provider given an oversized image downscales it and the model answers in
    the space it was actually shown -- measured at 17% instead of ~100% for
    Haiku 4.5 and Sonnet 4.6, the same defect class as the gemini-pro-agent
    8.4%-vs-96.8% error. The pipeline does the resize itself so the space is
    known and recorded.
    """

    def test_uncapped_models_are_untouched(self):
        from evaluation.providers.config import image_send_scale

        for model in ("openai/gpt-4o-mini", "9router/cx/gpt-5.5",
                      "anthropic/claude-opus-5", "anthropic/claude-sonnet-5"):
            self.assertEqual(1.0, image_send_scale(model, 1080, 2219), model)

    def test_capped_models_scale_to_their_cap(self):
        from evaluation.providers.config import image_send_scale, max_image_edge

        for model in ("anthropic/claude-haiku-4-5", "anthropic/claude-sonnet-4-6"):
            self.assertEqual(1568, max_image_edge(model))
            self.assertAlmostEqual(1568 / 2219,
                                   image_send_scale(model, 1080, 2219), places=6)

    def test_an_image_already_under_the_cap_is_not_scaled(self):
        from evaluation.providers.config import image_send_scale

        self.assertEqual(1.0, image_send_scale("anthropic/claude-haiku-4-5", 800, 1200))

    def test_scale_one_reencodes_the_original_bytes_untouched(self):
        """The comparability guarantee: an uncapped model's request is unchanged."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "screen.png"
            path.write_bytes(b"\x89PNG\r\n\x1a\nnot-a-real-png")

            # scale >= 1.0 must not even open the file as an image, so a
            # non-decodable payload round-trips byte for byte.
            expected = base64.b64encode(path.read_bytes()).decode("ascii")
            self.assertEqual(f"data:image/png;base64,{expected}",
                             vlm_provider.image_to_data_url(path, 1.0))

    def test_a_scaled_image_is_actually_smaller(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "screen.png"
            Image.new("RGB", (1080, 2219), "white").save(path)

            url = vlm_provider.image_to_data_url(path, 1568 / 2219)
            raw = base64.b64decode(url.split(",", 1)[1])
            with Image.open(io.BytesIO(raw)) as img:
                self.assertEqual((763, 1568), img.size)
                self.assertEqual(1568, max(img.size))


class ScaledPredictionScoringTests(unittest.TestCase):
    """A reply in downscaled space must be rescaled before it is scored."""

    BOX = [95, 221, 266, 283]          # true centre (180, 252)
    SCALE = 1568 / 2219

    def test_downscaled_reply_scores_as_a_hit_once_rescaled(self):
        from evaluation.runner import score_one_trial

        # What Haiku actually returned for this target on clock_baseline.
        x, y, score, _ = score_one_trial(
            "[127, 177]", self.BOX, self.BOX, 1080, 2219, image_scale=self.SCALE,
        )
        self.assertEqual(1, score)
        self.assertAlmostEqual(180, x, delta=3)
        self.assertAlmostEqual(252, y, delta=4)

    def test_the_same_reply_is_a_miss_without_the_rescale(self):
        """Pins the defect this fix exists for -- 17% instead of ~100%."""
        from evaluation.runner import score_one_trial

        _, _, score, _ = score_one_trial(
            "[127, 177]", self.BOX, self.BOX, 1080, 2219,
        )
        self.assertEqual(0, score)

    def test_scale_one_reproduces_the_previous_scoring_exactly(self):
        from evaluation.runner import score_one_trial

        for reply in ("[180, 252]", "[127, 177]", "not a coordinate", "[9999, 9999]"):
            self.assertEqual(
                score_one_trial(reply, self.BOX, self.BOX, 1080, 2219),
                score_one_trial(reply, self.BOX, self.BOX, 1080, 2219, image_scale=1.0),
                reply,
            )


class CappedModelTreeModeTests(unittest.TestCase):
    """A capped model (screenshot downscaled) can now run tree mode: the tree
    bounds are scaled into the same space as the sent image instead of the
    run being refused."""

    def test_tree_mode_runs_a_capped_model_with_scaled_bounds(self):
        import json as _json
        import struct as _struct

        from evaluation.runner import evaluate_screen

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            images, labels = root / "images", root / "labels"
            images.mkdir(); labels.mkdir()
            (images / "clock_baseline.png").write_bytes(
                b"\x89PNG\r\n\x1a\n" + _struct.pack(">I", 13) + b"IHDR"
                + _struct.pack(">II", 1080, 2219)
            )
            # "Alarm" is the harvested target; "Snooze" is a distinct element
            # far enough from Alarm's hit box that collect_tree_rows keeps it,
            # so the captured tree carries at least one row to check scaling on.
            (labels / "clock_baseline.json").write_text(
                _json.dumps([
                    {"text": "Alarm", "box": [10, 10, 100, 60]},
                    {"text": "Snooze", "box": [200, 200, 300, 260]},
                ]),
                encoding="utf-8",
            )

            # Both baseline texts are unique, so harvest_targets queries both
            # in file order: "Alarm" first (with "Snooze" as its tree
            # context), then "Snooze" (with "Alarm" as its tree context).
            calls = []

            def fake_call_vlm(model, image_path, prompt, target_text=None, **kwargs):
                calls.append({
                    "target_text": target_text,
                    "prompt": prompt,
                    "tree_rows": kwargs.get("tree_rows"),
                    "img_width": kwargs.get("img_width"),
                    "img_height": kwargs.get("img_height"),
                })
                return "[100, 100]"

            with mock.patch("evaluation.runner.call_vlm", side_effect=fake_call_vlm):
                # Previously this raised ValueError; it must now run cleanly.
                count = evaluate_screen(
                    "anthropic/claude-haiku-4-5", "clock", 0, root / "r.csv",
                    images_dir=images, labels_dir=labels, use_a11y_tree=True,
                    profiles=["baseline"],
                )

            self.assertEqual(2, count)
            self.assertEqual(2, len(calls))
            alarm_call = next(c for c in calls if c["target_text"] == "Alarm")

            # 1080x2219 capped to a 1568px long edge -> 763x1568.
            self.assertEqual(763, alarm_call["img_width"])
            self.assertEqual(1568, alarm_call["img_height"])
            self.assertIn("763 x 1568", alarm_call["prompt"])

            tree_rows = alarm_call["tree_rows"]
            self.assertTrue(tree_rows)
            labels_seen = {label: box for label, box in tree_rows}
            self.assertIn("Snooze", labels_seen)
            snooze_box = labels_seen["Snooze"]
            # Unscaled box would be [200, 200, 300, 260]; scaled by 1568/2219
            # it must land well inside the 763x1568 sent image and differ from
            # the unscaled values.
            self.assertNotEqual([200, 200, 300, 260], snooze_box)
            x1, y1, x2, y2 = snooze_box
            self.assertTrue(0 <= x1 <= x2 <= 763)
            self.assertTrue(0 <= y1 <= y2 <= 1568)
            self.assertEqual([141, 141, 212, 184], snooze_box)


class ScaleTreeRowsTests(unittest.TestCase):
    """scale_tree_rows keeps a capped model's tree bounds in the same
    coordinate space as the downscaled screenshot it accompanies."""

    def test_identity_at_scale_one(self):
        from evaluation.grounding.task_prompting import scale_tree_rows

        rows = [("Snooze", [200, 200, 300, 260])]
        result = scale_tree_rows(rows, 1.0)
        # Same object, not a rebuilt equal copy -- an uncapped model's prompt
        # must be byte-identical to the pre-cap pipeline.
        self.assertIs(rows, result)

    def test_scales_and_rounds_at_capped_ratio(self):
        from evaluation.grounding.task_prompting import scale_tree_rows

        scale = 1568 / 2219
        rows = [("Snooze", [200, 200, 300, 260])]
        result = scale_tree_rows(rows, scale)
        self.assertEqual([("Snooze", [141, 141, 212, 184])], result)

    def test_degenerate_box_does_not_invert(self):
        from evaluation.grounding.task_prompting import scale_tree_rows

        # A 1px-wide box at a small scale can round both edges to the same
        # value or, without clamping, x2 < x1.
        rows = [("dot", [100, 100, 101, 101])]
        result = scale_tree_rows(rows, 0.01)
        (_, (x1, y1, x2, y2)) = result[0]
        self.assertGreaterEqual(x2, x1)
        self.assertGreaterEqual(y2, y1)


class StructuredCoordinateTests(SamplingEnvIsolation, unittest.TestCase):
    """Constraining the reply to coordinates, for models that ignore the prompt.

    The schema returns an array, so the rendered JSON contains a literal
    "[x, y]" that the existing bracket parser reads unchanged -- turning this
    on cannot alter how any reply is interpreted, only what the model sends.
    """

    def _call(self, model, **env):
        with mock.patch("evaluation.providers.hosted._completion") as completion, \
             mock.patch("evaluation.providers.hosted._register_compatible_model"), \
             mock.patch.dict(os.environ, env, clear=False), \
             tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "screen.png"
            path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
            completion.return_value = {
                "choices": [{"finish_reason": "stop",
                             "message": {"content": '{"coordinates": [126, 176]}'}}],
            }
            vlm_provider.call_vlm(model, path, "Find Settings")
            return completion.call_args.kwargs

    def test_off_by_default(self):
        self.assertNotIn("response_format", self._call("anthropic/claude-haiku-4-5"))

    def test_enabled_sends_a_strict_schema(self):
        kwargs = self._call("anthropic/claude-haiku-4-5", VLM_STRUCTURED_COORDS="true")
        schema = kwargs["response_format"]["json_schema"]
        self.assertTrue(schema["strict"])
        self.assertEqual(["coordinates"], schema["schema"]["required"])
        self.assertFalse(schema["schema"]["additionalProperties"])

    def test_not_sent_to_non_anthropic_models(self):
        self.assertNotIn(
            "response_format",
            self._call("openai/gpt-4o-mini", VLM_STRUCTURED_COORDS="true"),
        )

    def test_the_schema_reply_parses_with_the_unchanged_bracket_rule(self):
        from evaluation.grounding.scoring import parse_coordinates_detailed

        self.assertEqual(
            (126.0, 176.0, "bracket"),
            parse_coordinates_detailed('{"coordinates": [126, 176]}'),
        )
