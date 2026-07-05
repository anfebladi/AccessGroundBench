import base64
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import vlm_provider


class FakeRateLimitError(Exception):
    pass


class VlmProviderTests(unittest.TestCase):
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
