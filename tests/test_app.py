import os
import unittest
from unittest.mock import patch

import app


class ModelConfigurationTests(unittest.TestCase):
    def test_load_models_resolves_environment_key(self):
        raw = '[{"id":"demo","name":"Demo","base_url":"https://example.com/v1","api_key":"${DEMO_KEY}","models":["model-a"]}]'
        with patch.dict(os.environ, {"AI_PROVIDERS_JSON": raw, "DEMO_KEY": "secret"}, clear=False):
            models = app.load_models()
        self.assertIn("demo:model-a", models)
        self.assertEqual(models["demo:model-a"].api_key, "secret")
        self.assertEqual(models["demo:model-a"].base_url, "https://example.com/v1")

    def test_openrouter_secret_auto_configures_default_model(self):
        with patch.dict(os.environ, {
            "AI_PROVIDERS_JSON": "[]",
            "OPENROUTER_API_KEY": "test-openrouter-key",
        }, clear=False):
            models = app.load_models()
        self.assertIn("openrouter:openai/gpt-4.1-mini", models)
        self.assertEqual(models["openrouter:openai/gpt-4.1-mini"].api_key, "test-openrouter-key")
        self.assertEqual(models["openrouter:openai/gpt-4.1-mini"].base_url, "https://openrouter.ai/api/v1")

    def test_invalid_json_is_rejected(self):
        with patch.dict(os.environ, {"AI_PROVIDERS_JSON": "not-json"}, clear=False):
            with self.assertRaises(RuntimeError):
                app.load_models()

    def test_non_array_configuration_is_rejected(self):
        with patch.dict(os.environ, {"AI_PROVIDERS_JSON": "{}"}, clear=False):
            with self.assertRaises(RuntimeError):
                app.load_models()

    def test_incomplete_provider_is_skipped(self):
        with patch.dict(os.environ, {"AI_PROVIDERS_JSON": '[{"id":"missing","models":["x"]}]'}, clear=False):
            self.assertEqual(app.load_models(), {})


class AccessControlTests(unittest.TestCase):
    def test_empty_allow_list_denies_access_by_default(self):
        with patch.object(app, "PUBLIC_ACCESS", False), patch.object(app, "ALLOWED_USER_IDS", set()):
            self.assertFalse(app.is_allowed(12345))

    def test_allow_list_permits_only_selected_user(self):
        with patch.object(app, "PUBLIC_ACCESS", False), patch.object(app, "ALLOWED_USER_IDS", {12345}):
            self.assertTrue(app.is_allowed(12345))
            self.assertFalse(app.is_allowed(67890))

    def test_public_access_requires_explicit_flag(self):
        with patch.object(app, "PUBLIC_ACCESS", True), patch.object(app, "ALLOWED_USER_IDS", set()):
            self.assertTrue(app.is_allowed(67890))


if __name__ == "__main__":
    unittest.main()
