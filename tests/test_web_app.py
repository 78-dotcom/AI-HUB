import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import web_app


class WebAppAccessTests(unittest.TestCase):
    def setUp(self):
        web_app._login_failures.clear()
        self.env = patch.dict(os.environ, {
            "HUB_ACCESS_PASSWORD": "correct-horse-battery",
            "HUB_SESSION_SECRET": "test-session-secret",
            "AI_PROVIDERS_JSON": "[]",
            "OPENROUTER_API_KEY": "test-provider-key",
        }, clear=False)
        self.env.start()
        self.client = TestClient(web_app.app)

    def tearDown(self):
        self.client.close()
        self.env.stop()
        web_app._login_failures.clear()

    def login(self):
        return self.client.post(
            "/api/login",
            json={"password": "correct-horse-battery"},
        )

    def test_health_endpoint_and_security_headers(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_models_require_authentication(self):
        response = self.client.get("/api/models")
        self.assertEqual(response.status_code, 401)

    def test_successful_login_sets_http_only_session_cookie(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        cookie = response.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=lax", cookie)
        self.assertTrue(self.client.get("/api/session").json()["authenticated"])
        self.assertEqual(self.client.get("/api/models").status_code, 200)

    def test_conversation_history_requires_individual_account(self):
        response = self.client.get("/api/conversations")
        self.assertEqual(response.status_code, 401)

    def test_chat_requires_authentication(self):
        response = self.client.post(
            "/api/chat",
            json={"model": "openrouter:openai/gpt-4.1-mini", "messages": [
                {"role": "user", "content": "Hello"}
            ]},
        )
        self.assertEqual(response.status_code, 401)

    def test_chat_rejects_unconfigured_model(self):
        self.login()
        response = self.client.post(
            "/api/chat",
            json={"model": "missing:model", "messages": [
                {"role": "user", "content": "Hello"}
            ]},
        )
        self.assertEqual(response.status_code, 400)

    def test_login_is_rate_limited_after_five_failures(self):
        for _ in range(web_app.LOGIN_MAX_FAILURES):
            response = self.client.post("/api/login", json={"password": "wrong"})
            self.assertEqual(response.status_code, 401)
        blocked = self.login()
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("retry-after", blocked.headers)


if __name__ == "__main__":
    unittest.main()
