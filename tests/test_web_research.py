import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import web_app
from web_research import normalize_search_results


class WebResearchTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "HUB_ACCESS_PASSWORD": "correct-horse-battery",
            "HUB_SESSION_SECRET": "test-session-secret",
            "AI_PROVIDERS_JSON": "[]",
            "BRAVE_SEARCH_API_KEY": "test-brave-key",
        }, clear=False)
        self.env.start()
        self.client = TestClient(web_app.app)
        login = self.client.post("/api/login", json={"password": "correct-horse-battery"})
        self.assertEqual(login.status_code, 200)

    def tearDown(self):
        self.client.close()
        self.env.stop()

    def test_normalizer_rejects_non_https_and_deduplicates(self):
        payload = {"web": {"results": [
            {"title": "Unsafe", "url": "javascript:alert(1)", "description": "bad"},
            {"title": "Good", "url": "https://example.com/a", "description": "evidence"},
            {"title": "Duplicate", "url": "https://example.com/a", "description": "duplicate"},
        ]}}
        sources = normalize_search_results(payload)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["id"], "S1")
        self.assertEqual(sources[0]["domain"], "example.com")

    def test_search_requires_authentication(self):
        self.client.post("/api/logout", json={})
        response = self.client.post("/api/research/search", json={"query": "AI policy"})
        self.assertEqual(response.status_code, 401)

    def test_returns_answer_and_source_links(self):
        sources = [{
            "id": "S1", "title": "Official report", "url": "https://example.com/report",
            "domain": "example.com", "snippet": "The report states a finding.",
            "age": "2026-10-01",
        }]
        models = {"m1": {
            "id": "m1", "display_name": "Test model", "model": "test",
            "base_url": "https://provider.example/v1", "api_key": "secret",
            "input_modalities": ["text"],
        }}
        with patch("web_research._search_brave", new=AsyncMock(return_value=sources)), \
             patch("web_research._call_research_model", new=AsyncMock(return_value="Finding [S1].")), \
             patch("web_app.load_models", return_value=models):
            response = self.client.post("/api/research/search", json={
                "query": "What does the report say?", "model_id": "m1", "count": 6,
            })
        self.assertEqual(response.status_code, 200)
        self.assertIn("[S1]", response.json()["answer"])
        self.assertEqual(response.json()["sources"][0]["url"], "https://example.com/report")
        self.assertIn("not independently opened", response.json()["evidence_note"])

    def test_missing_search_key_returns_configuration_error(self):
        models = {"m1": {
            "id": "m1", "display_name": "Test model", "model": "test",
            "base_url": "https://provider.example/v1", "api_key": "secret",
            "input_modalities": ["text"],
        }}
        with patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": ""}), \
             patch("web_app.load_models", return_value=models):
            response = self.client.post("/api/research/search", json={"query": "AI policy"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("BRAVE_SEARCH_API_KEY", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
