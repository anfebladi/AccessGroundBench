import base64
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import vlm_provider


class FakeRateLimitError(Exception):
    pass


class VlmProviderTests(unittest.TestCase):
    @mock.patch.dict(
        "vlm_provider.os.environ",
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

    @mock.patch.dict("vlm_provider.os.environ", {}, clear=True)
    def test_request_timeout_defaults_to_120_seconds(self):
        self.assertEqual(120.0, vlm_provider._resolve_request_timeout())

    @mock.patch.dict(
        "vlm_provider.os.environ", {"VLM_REQUEST_TIMEOUT_SECONDS": "30"}, clear=True
    )
    def test_request_timeout_uses_environment(self):
        self.assertEqual(30.0, vlm_provider._resolve_request_timeout())

    def test_request_timeout_rejects_non_positive_values(self):
        with self.assertRaises(ValueError):
            vlm_provider._resolve_request_timeout(0)

    def test_connection_errors_are_retryable(self):
        self.assertTrue(vlm_provider._is_retryable_error(Exception("Connection error.")))

    @mock.patch.dict(
        "vlm_provider.os.environ",
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

    @mock.patch.dict("vlm_provider.os.environ", {"NINEROUTER_API_KEY": "key"}, clear=True)
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
        "vlm_provider.os.environ",
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

    @mock.patch.dict("vlm_provider.os.environ", {}, clear=True)
    def test_compatible_model_reports_missing_configuration(self):
        error = vlm_provider.model_configuration_error("9router/cx/gpt-5.3-codex")
        self.assertIn("NINEROUTER_BASE_URL", error)
        self.assertIn("NINEROUTER_API_KEY", error)

    @mock.patch.dict(
        "vlm_provider.os.environ",
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

    @mock.patch.dict("vlm_provider.os.environ", {}, clear=True)
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

    @mock.patch("vlm_provider._completion")
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
        "vlm_provider.os.environ",
        {
            "NINEROUTER_BASE_URL": "http://localhost:20128/v1/",
            "NINEROUTER_API_KEY": "router-key",
        },
        clear=True,
    )
    @mock.patch("vlm_provider._register_compatible_model")
    @mock.patch("vlm_provider._completion")
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
        "vlm_provider.os.environ",
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

    @mock.patch("vlm_provider.time.sleep")
    @mock.patch("vlm_provider._completion")
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

    @mock.patch("vlm_provider.time.sleep")
    @mock.patch("vlm_provider._completion")
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

    @mock.patch("vlm_provider.urllib.request.urlopen")
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

    @mock.patch("vlm_provider.urllib.request.urlopen")
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

    @mock.patch("vlm_provider.urllib.request.urlopen")
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

    @mock.patch("vlm_provider.urllib.request.urlopen")
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

    @mock.patch("vlm_provider._completion")
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

    @mock.patch("vlm_provider.time.sleep")
    @mock.patch("vlm_provider._completion")
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

    @mock.patch("vlm_provider._completion")
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

    @mock.patch("vlm_provider._completion")
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

    @mock.patch("vlm_provider.time.sleep")
    @mock.patch("vlm_provider._completion")
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
