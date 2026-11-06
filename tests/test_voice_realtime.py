import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

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
            "DATABASE_URL": "sqlite://",
            "HUB_SIGNUP_CODE": "test-invite-code",
            "OPENAI_REALTIME_MODEL": "gpt-realtime-2.1-mini",
            "RENDER": "",
        }, clear=False)
        self.env.start()
        web_app._login_failures.clear()
        voice_realtime._voice_issue_history.clear()
        import accounts
        accounts._engines.clear()
        accounts._schema_ready.clear()
        accounts._auth_failures.clear()
        self.client = TestClient(web_app.app)
        self.client.post("/api/login", json={"password": "test-workspace-password"})

    def tearDown(self):
        self.client.close()
        web_app._login_failures.clear()
        voice_realtime._voice_issue_history.clear()
        import accounts
        for engine in accounts._engines.values():
            engine.dispose()
        accounts._engines.clear()
        accounts._schema_ready.clear()
        accounts._auth_failures.clear()
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


    def test_voice_session_cooldown_blocks_rapid_reconnects(self):
        request = SimpleNamespace(cookies={"aihub_session": "signed-workspace-session"})
        voice_realtime._check_voice_session_rate_limit(request, now=100.0)
        with self.assertRaises(HTTPException) as caught:
            voice_realtime._check_voice_session_rate_limit(request, now=102.0)
        self.assertEqual(caught.exception.status_code, 429)
        self.assertIn("Retry-After", caught.exception.headers)

    def test_voice_session_rolling_hourly_limit(self):
        request = SimpleNamespace(cookies={"aihub_session": "signed-workspace-session"})
        for index in range(voice_realtime.VOICE_SESSION_MAX_PER_WINDOW):
            voice_realtime._check_voice_session_rate_limit(request, now=100.0 + index * 6.0)
        with self.assertRaises(HTTPException) as caught:
            voice_realtime._check_voice_session_rate_limit(request, now=100.0 + 11 * 6.0 + 6.0)
        self.assertEqual(caught.exception.status_code, 429)
        voice_realtime._check_voice_session_rate_limit(
            request, now=100.0 + voice_realtime.VOICE_SESSION_WINDOW_SECONDS + 10.0
        )

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

    def test_voice_transcript_is_saved_as_text_for_account_users(self):
        registered = self.client.post("/api/auth/register", json={
            "email": "voice-user@example.com",
            "password": "a-very-long-test-password",
            "invite_code": "test-invite-code",
        })
        self.assertEqual(registered.status_code, 200)
        response = self.client.post("/api/voice/transcript", json={
            "model": "gpt-realtime-2.1-mini",
            "user_text": "Привет, AI HUB",
            "assistant_text": "Привет! Чем могу помочь?",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["persisted"])
        self.assertFalse(response.json()["raw_audio_stored_by_ai_hub"])
        conversations = self.client.get("/api/conversations").json()["conversations"]
        self.assertEqual(len(conversations), 1)
        self.assertEqual([m["role"] for m in conversations[0]["messages"]], ["user", "assistant"])

    def test_voice_transcript_is_not_saved_for_workspace_only_users(self):
        response = self.client.post("/api/voice/transcript", json={
            "model": "gpt-realtime-2.1-mini",
            "user_text": "Hello",
            "assistant_text": "Hi there",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["persisted"])

    def test_voice_transcript_rejects_unknown_models(self):
        response = self.client.post("/api/voice/transcript", json={
            "model": "not-realtime",
            "user_text": "Hello",
            "assistant_text": "Hi there",
        })
        self.assertEqual(response.status_code, 400)

    def test_provider_failure_returns_safe_error(self):
        fake = FakeAsyncClient(FakeResponse({}, status_code=401))
        with patch.object(voice_realtime.httpx, "AsyncClient", return_value=fake):
            response = self.client.post("/api/voice/session", json={"language": "en"})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("test-openai-key", response.text)


if __name__ == "__main__":
    unittest.main()
