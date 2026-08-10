import unittest

from webui import keys


class SessionKeyStoreTests(unittest.TestCase):
    def tearDown(self):
        for provider in keys.PROVIDER_ENV_VARS:
            keys.clear_key(provider)

    def test_set_and_check_key(self):
        keys.set_key("openai", "sk-test-123")
        self.assertTrue(keys.has_session_key("openai"))
        self.assertEqual({"OPENAI_API_KEY": "sk-test-123"}, keys.session_env_overrides())

    def test_clear_key_removes_override(self):
        keys.set_key("openai", "sk-test-123")
        keys.clear_key("openai")
        self.assertFalse(keys.has_session_key("openai"))
        self.assertEqual({}, keys.session_env_overrides())

    def test_setting_empty_value_clears_it(self):
        keys.set_key("gemini", "abc")
        keys.set_key("gemini", "")
        self.assertFalse(keys.has_session_key("gemini"))

    def test_unknown_provider_raises(self):
        with self.assertRaises(ValueError):
            keys.set_key("not-a-real-provider", "x")

    def test_multiple_providers_do_not_interfere(self):
        keys.set_key("openai", "sk-openai")
        keys.set_key("anthropic", "sk-anthropic")
        overrides = keys.session_env_overrides()
        self.assertEqual("sk-openai", overrides["OPENAI_API_KEY"])
        self.assertEqual("sk-anthropic", overrides["ANTHROPIC_API_KEY"])

    def test_9router_and_openai_compatible_map_to_api_key_var_only(self):
        # The base-URL half of these providers is configured via .env only --
        # the session store just overrides the credential half.
        keys.set_key("9router", "route-key")
        keys.set_key("openai_compatible", "compat-key")
        overrides = keys.session_env_overrides()
        self.assertEqual("route-key", overrides["NINEROUTER_API_KEY"])
        self.assertEqual("compat-key", overrides["OPENAI_COMPATIBLE_API_KEY"])


if __name__ == "__main__":
    unittest.main()
