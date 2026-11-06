import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import web_app
import voice_realtime


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            request = httpx.Request("POST", voice_realtime.OPENAI_CLIENT_SECRETS_URL)
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("provider error", request=request, response=response)

    def json(self):
        return self._payload


class FakeAsyncClient:
    def __init__(self, response):
        self.response = response
        self.request = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, **kwargs):
        self.request = (url, kwargs)
        return self.response


class RealtimeVoiceApiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "HUB_ACCESS_PASSWORD": "test-workspace-password",
            "HUB_SESSION_SECRET": "test-session-secret",
            "OPENAI_API_KEY": "test-openai-key",
            "OPENAI_REALTIME_MODEL": "gpt-realtime-2.1-mini",
            "RENDER": "",
        }, clear=False)
        self.env.start()
        web_app._login_failures.clear()
        self.client = TestClient(web_app.app)
        self.client.post("/api/login", json={"password": "test-workspace-password"})

    def tearDown(self):
        self.client.close()
        web_app._login_failures.clear()
        self.env.stop()

    def test_capabilities_require_authentication(self):
        self.client.post("/api/logout", json={})
        response = self.client.get("/api/voice/capabilities")
        self.assertEqual(response.status_code, 401)

    def test_capabilities_report_configured_realtime_provider(self):
        response = self.client.get("/api/voice/capabilities")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["realtime_voice"])
        self.assertEqual(response.json()["model"], "gpt-realtime-2.1-mini")

    def test_session_mints_ephemeral_secret_without_exposing_project_key(self):
        fake = FakeAsyncClient(FakeResponse({
            "client_secret": {"value": "ek_test_ephemeral", "expires_at": 1_800_000_000}
        }))
        with patch.object(voice_realtime.httpx, "AsyncClient", return_value=fake):
            response = self.client.post("/api/voice/session", json={"language": "ru"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["client_secret"], "ek_test_ephemeral")
        self.assertNotIn("test-openai-key", response.text)
        url, kwargs = fake.request
        self.assertEqual(url, voice_realtime.OPENAI_CLIENT_SECRETS_URL)
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-openai-key")
        self.assertEqual(kwargs["json"]["expires_after"]["seconds"], 60)
        session = kwargs["json"]["session"]
        self.assertEqual(session["model"], "gpt-realtime-2.1-mini")
        self.assertEqual(session["audio"]["input"]["transcription"]["language"], "ru")
        self.assertTrue(session["audio"]["input"]["turn_detection"]["interrupt_response"])
        self.assertEqual(session["audio"]["output"]["voice"], "marin")

    def test_missing_provider_key_keeps_voice_disabled(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            response = self.client.post("/api/voice/session", json={"language": "en"})
            capabilities = self.client.get("/api/voice/capabilities")
        self.assertEqual(response.status_code, 503)
        self.assertFalse(capabilities.json()["realtime_voice"])

    def test_unsupported_model_is_rejected_before_provider_call(self):
        with patch.dict(os.environ, {"OPENAI_REALTIME_MODEL": "not-a-realtime-model"}):
            response = self.client.post("/api/voice/session", json={"language": "en"})
        self.assertEqual(response.status_code, 503)

    def test_provider_failure_returns_safe_error(self):
        fake = FakeAsyncClient(FakeResponse({}, status_code=401))
        with patch.object(voice_realtime.httpx, "AsyncClient", return_value=fake):
            response = self.client.post("/api/voice/session", json={"language": "en"})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("test-openai-key", response.text)


if __name__ == "__main__":
    unittest.main()
