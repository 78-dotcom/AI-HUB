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

    def test_model_catalog_supports_legacy_and_rich_entries(self):
        config = [{
            "id": "sample", "name": "Sample Provider",
            "base_url": "https://api.example.test/v1", "api_key": "secret",
            "models": [
                "legacy-model",
                {
                    "id": "vision-model", "name": "Vision Model",
                    "description": "Understands images", "category": "vision",
                    "capabilities": ["chat", "vision", "chat"],
                    "input_modalities": ["text", "image"],
                    "output_modalities": ["text"], "context_window": 128000,
                },
            ],
        }]
        with patch.dict(os.environ, {"AI_PROVIDERS_JSON": __import__("json").dumps(config)}, clear=False):
            models = web_app.load_models()
        self.assertEqual(models["sample:legacy-model"]["input_modalities"], ["text"])
        rich = models["sample:vision-model"]
        self.assertEqual(rich["display_name"], "Vision Model")
        self.assertEqual(rich["capabilities"], ["chat", "vision"])
        self.assertEqual(rich["context_window"], 128000)
        self.assertEqual(rich["api_key"], "secret")

    def test_model_catalog_does_not_expose_provider_credentials(self):
        self.login()
        response = self.client.get("/api/models")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["models"])
        self.assertNotIn("api_key", payload["models"][0])
        self.assertNotIn("base_url", payload["models"][0])

    def test_provider_text_response_accepts_plain_text(self):
        payload = {"choices": [{"message": {"content": "  Hello from AI  "}}]}
        self.assertEqual(web_app._extract_assistant_text(payload), "Hello from AI")

    def test_provider_text_response_accepts_text_content_blocks(self):
        payload = {"choices": [{"message": {"content": [
            {"type": "text", "text": "Hello "},
            {"type": "image_url", "image_url": {"url": "https://example.test/image.png"}},
            {"type": "output_text", "text": "there"},
        ]}}]}
        self.assertEqual(web_app._extract_assistant_text(payload), "Hello there")

    def test_provider_text_response_rejects_empty_or_malformed_payloads(self):
        for payload in ({}, {"choices": []}, {"choices": [{"message": {"content": []}}]}):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    web_app._extract_assistant_text(payload)

    def test_intelligence_route_requires_authentication(self):
        response = self.client.post(
            "/api/intelligence/route", json={"prompt": "Help me debug Python"}
        )
        self.assertEqual(response.status_code, 401)

    def test_intelligence_route_selects_specialist_without_exposing_secrets(self):
        self.login()
        models = {
            "provider:general": {
                "id": "provider:general", "provider": "provider",
                "provider_name": "Provider", "model": "general",
                "display_name": "General", "category": "general",
                "capabilities": ["chat"], "api_key": "private-key",
                "base_url": "https://private.example",
            },
            "provider:coder": {
                "id": "provider:coder", "provider": "provider",
                "provider_name": "Provider", "model": "coder",
                "display_name": "Coder", "category": "coding",
                "capabilities": ["chat", "code"], "api_key": "private-key",
                "base_url": "https://private.example",
            },
        }
        with patch.object(web_app, "load_models", return_value=models):
            response = self.client.post(
                "/api/intelligence/route",
                json={"prompt": "Please debug this Python code"},
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["task"], "coding")
        self.assertEqual(payload["selected_model"]["id"], "provider:coder")
        self.assertNotIn("api_key", response.text)
        self.assertNotIn("private.example", response.text)

    def test_intelligence_route_reports_no_configured_models(self):
        self.login()
        with patch.object(web_app, "load_models", return_value={}):
            response = self.client.post(
                "/api/intelligence/route", json={"prompt": "Hello"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["available"])

    def test_auto_chat_routes_to_specialist_model(self):
        self.login()

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "choices": [{"message": {"content": "Routed answer"}}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 2},
                }

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                self.requested_model = None

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, url, headers, json):
                self.requested_model = json["model"]
                return FakeResponse()

        models = {
            "provider:general": {
                "id": "provider:general", "provider": "provider",
                "provider_name": "Provider", "model": "general",
                "display_name": "General", "category": "general",
                "capabilities": ["chat"], "base_url": "https://api.example.test/v1",
                "api_key": "private-key",
            },
            "provider:coder": {
                "id": "provider:coder", "provider": "provider",
                "provider_name": "Provider", "model": "coder",
                "display_name": "Coder", "category": "coding",
                "capabilities": ["chat", "code"], "base_url": "https://api.example.test/v1",
                "api_key": "private-key",
            },
        }
        with patch.object(web_app, "load_models", return_value=models), patch.object(web_app.httpx, "AsyncClient", FakeAsyncClient), patch.object(web_app, "persist_chat", return_value="test-conversation-id"):
            response = self.client.post(
                "/api/chat",
                json={"model": "auto", "messages": [
                    {"role": "user", "content": "Please debug this Python code"}
                ]},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "Routed answer")
        self.assertEqual(response.json()["selected_model"], "provider:coder")
        self.assertEqual(response.json()["conversation_id"], "test-conversation-id")


    def test_future_lab_scenarios_require_authentication(self):
        response = self.client.post("/api/future-lab/scenarios", json={
            "objective": "Launch an online shop", "domain": "business",
            "horizon_months": 12, "variables": [{
                "name": "monthly revenue", "current_value": 10000,
                "downside_change_pct": -20, "upside_change_pct": 30,
            }],
        })
        self.assertEqual(response.status_code, 401)

    def test_future_lab_scenarios_returns_transparent_cases(self):
        self.login()
        response = self.client.post("/api/future-lab/scenarios", json={
            "objective": "Launch an online shop", "domain": "business",
            "horizon_months": 12, "variables": [{
                "name": "monthly revenue", "current_value": 10000,
                "downside_change_pct": -20, "upside_change_pct": 30,
            }],
        })
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "assumption_stress_test")
        self.assertEqual(payload["scenarios"][0]["variables"][0]["projected_value"], 8000)
        self.assertEqual(payload["scenarios"][2]["variables"][0]["projected_value"], 13000)
        self.assertIn("No probabilities", payload["assumptions"][2])

    def test_future_lab_rejects_invalid_horizon(self):
        self.login()
        response = self.client.post("/api/future-lab/scenarios", json={
            "objective": "Launch an online shop", "domain": "business",
            "horizon_months": 0, "variables": [{
                "name": "monthly revenue", "current_value": 10000,
                "downside_change_pct": -20, "upside_change_pct": 30,
            }],
        })
        self.assertEqual(response.status_code, 422)

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
