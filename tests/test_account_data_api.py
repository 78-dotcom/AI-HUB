import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import accounts
import web_app


class AccountDataApiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "DATABASE_URL": "sqlite://",
            "HUB_SIGNUP_CODE": "test-invite-code",
            "RENDER": "",
        }, clear=False)
        self.env.start()
        accounts._engines.clear()
        self.client = TestClient(web_app.app)
        response = self.client.post("/api/auth/register", json={
            "email": "data@example.com",
            "password": "a-very-long-test-password",
            "invite_code": "test-invite-code",
        })
        self.assertEqual(response.status_code, 200)

    def tearDown(self):
        self.client.close()
        for engine in accounts._engines.values():
            engine.dispose()
        accounts._engines.clear()
        self.env.stop()

    def test_preferences_are_saved_and_returned(self):
        saved = self.client.put("/api/preferences", json={
            "language": "ru",
            "preferred_model": "openrouter:example/model",
            "preferences": {"compact_mode": True},
        })
        self.assertEqual(saved.status_code, 200)
        loaded = self.client.get("/api/preferences")
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(loaded.json()["language"], "ru")
        self.assertEqual(loaded.json()["preferred_model"], "openrouter:example/model")
        self.assertTrue(loaded.json()["preferences"]["compact_mode"])

    def test_usage_endpoint_starts_at_zero_and_does_not_guess_cost(self):
        response = self.client.get("/api/usage")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["requests"], 0)
        self.assertEqual(data["input_tokens"], 0)
        self.assertEqual(data["output_tokens"], 0)
        self.assertIsNone(data["estimated_cost_usd"])
        self.assertIn("not yet configured", data["cost_note"])

    def test_preferences_reject_unsupported_language(self):
        response = self.client.put("/api/preferences", json={
            "language": "xx",
            "preferred_model": None,
            "preferences": {},
        })
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
