import os
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import voice


class VoiceProviderTests(unittest.TestCase):
    def test_no_provider_is_exposed_without_credentials(self):
        with patch.dict(os.environ, {
            "GEMINI_API_KEY": "",
            "OPENAI_API_KEY": "",
        }, clear=False):
            self.assertEqual(voice.available_voice_providers(), [])

    def test_gemini_is_marked_free_tier_eligible(self):
        with patch.dict(os.environ, {
            "GEMINI_API_KEY": "test-gemini-key",
            "OPENAI_API_KEY": "",
        }, clear=False):
            providers = voice.available_voice_providers()
        self.assertEqual(providers[0]["id"], "gemini")
        self.assertEqual(providers[0]["tier"], "free-tier-eligible")
        self.assertNotIn("test-gemini-key", str(providers))

    def test_openai_realtime_is_separate_paid_adapter(self):
        with patch.dict(os.environ, {
            "GEMINI_API_KEY": "",
            "OPENAI_API_KEY": "test-openai-key",
        }, clear=False):
            providers = voice.available_voice_providers()
            url, headers = voice._upstream_config("openai")
        self.assertEqual(providers[0]["id"], "openai")
        self.assertEqual(providers[0]["tier"], "paid")
        self.assertIn("gpt-realtime", url)
        self.assertEqual(headers["Authorization"], "Bearer test-openai-key")

    def test_gemini_adapter_keeps_key_server_side(self):
        with patch.dict(os.environ, {
            "GEMINI_API_KEY": "secret-key",
            "GEMINI_LIVE_MODEL": "gemini-3.1-flash-live-preview",
        }, clear=False):
            url, headers = voice._upstream_config("gemini")
        self.assertEqual(parse_qs(urlparse(url).query)["key"], ["secret-key"])
        self.assertEqual(headers, {})

    def test_unknown_or_unconfigured_provider_is_rejected(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            with self.assertRaises(ValueError):
                voice._upstream_config("gemini")
            with self.assertRaises(ValueError):
                voice._upstream_config("unknown")

    def test_session_cap_is_ten_minutes(self):
        self.assertEqual(voice.VOICE_SESSION_SECONDS, 600)


if __name__ == "__main__":
    unittest.main()
