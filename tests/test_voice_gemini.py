import os
import unittest
from unittest.mock import patch

import voice_gemini


class GeminiVoiceAdapterTests(unittest.TestCase):
    def test_free_tier_session_cost_is_zero(self):
        with patch.dict(os.environ, {"GEMINI_BILLING_TIER": "free"}, clear=False):
            self.assertEqual(voice_gemini.gemini_session_cost(100, now=700), 0.0)

    def test_paid_tier_cost_uses_conservative_audio_rate_and_ten_minute_cap(self):
        with patch.dict(os.environ, {"GEMINI_BILLING_TIER": "paid"}, clear=False):
            self.assertAlmostEqual(voice_gemini.gemini_session_cost(100, now=700), 0.23)
            self.assertAlmostEqual(voice_gemini.gemini_session_cost(100, now=900), 0.23)

    def test_usage_metadata_is_normalized(self):
        self.assertEqual(
            voice_gemini._usage_counts({"usageMetadata": {
                "promptTokenCount": 123, "candidatesTokenCount": 45,
            }}),
            (123, 45),
        )
        self.assertIsNone(voice_gemini._usage_counts({"serverContent": {}}))

    def test_gemini_api_key_is_required_and_not_returned_by_provider_catalog(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            with self.assertRaises(ValueError):
                voice_gemini._gemini_url()
        with patch.dict(os.environ, {"GEMINI_API_KEY": "secret-key"}, clear=False):
            url = voice_gemini._gemini_url()
        self.assertIn("secret-key", url)
        self.assertTrue(url.startswith("wss://"))

    def test_model_defaults_to_free_tier_live_model(self):
        with patch.dict(os.environ, {"GEMINI_LIVE_MODEL": ""}, clear=False):
            self.assertEqual(voice_gemini.gemini_model(), "gemini-3.8-live")


if __name__ == "__main__":
    unittest.main()
