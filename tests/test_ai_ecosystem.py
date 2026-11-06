import os
import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

import web_app


class AIEcosystemTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "HUB_ACCESS_PASSWORD": "ecosystem-test-password",
            "HUB_SESSION_SECRET": "ecosystem-test-secret",
            "AI_PROVIDERS_JSON": "[]",
            "OPENROUTER_API_KEY": "",
        }, clear=False)
        self.env.start()
        self.client = TestClient(web_app.app)
        web_app._login_failures.clear()

    def tearDown(self):
        self.client.close()
        self.env.stop()
        web_app._login_failures.clear()

    def login(self):
        return self.client.post("/api/login", json={"password": "ecosystem-test-password"})

    def test_brain_requires_authentication(self):
        self.assertEqual(self.client.post("/api/brain/run", json={"prompt": "Write code"}).status_code, 401)

    def test_brain_routes_and_executes_selected_model(self):
        self.login()
        models = {
            "p:coder": {"id": "p:coder", "model": "coder", "base_url": "https://provider.invalid/v1",
                "api_key": "secret", "display_name": "Coder", "provider_name": "Provider",
                "category": "coding", "capabilities": ["code"], "input_modalities": ["text"]},
            "p:general": {"id": "p:general", "model": "general", "base_url": "https://provider.invalid/v1",
                "api_key": "secret", "display_name": "General", "provider_name": "Provider",
                "category": "general", "capabilities": ["chat"], "input_modalities": ["text"]},
        }
        with patch("ai_ecosystem._models", return_value=models), patch(
            "ai_ecosystem._call", new=AsyncMock(return_value=("Here is the solution.", {"total_tokens": 12}))
        ):
            response = self.client.post("/api/brain/run", json={"prompt": "Debug this Python code"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["selected_model"]["id"], "p:coder")
        self.assertEqual(response.json()["answer"], "Here is the solution.")
        self.assertFalse(response.json()["fallback_used"])

    def test_reality_check_requires_two_different_models(self):
        self.login()
        response = self.client.post("/api/reality-check/run", json={
            "prompt": "Check this claim", "lead_model": "same", "reviewer_model": "same"
        })
        self.assertEqual(response.status_code, 400)

    def test_marketplace_listing_requires_authentication(self):
        self.assertEqual(self.client.get("/api/marketplace").status_code, 401)

    def test_marketplace_publishing_requires_individual_account(self):
        self.login()
        response = self.client.post("/api/marketplace/assistants", json={
            "name": "My helper", "description": "Test", "instructions": "Help with useful tasks safely."
        })
        self.assertEqual(response.status_code, 401)

    def test_reality_check_runs_two_models_with_cost_cap(self):
        self.login()
        models = {
            key: {"id": key, "model": key, "base_url": "https://provider.invalid/v1",
                "api_key": "secret", "display_name": key, "provider_name": "Provider",
                "input_modalities": ["text"], "input_cost_per_1m_usd": 1.0,
                "output_cost_per_1m_usd": 2.0}
            for key in ("p:lead", "p:reviewer")
        }
        mocked = AsyncMock(side_effect=[
            ("A draft answer.", {"prompt_tokens": 10, "completion_tokens": 20}),
            ("One claim is uncertain.", {"prompt_tokens": 20, "completion_tokens": 30}),
        ])
        with patch("ai_ecosystem._models", return_value=models), patch("ai_ecosystem._call", new=mocked):
            response = self.client.post("/api/reality-check/run", json={
                "prompt": "Check this claim", "lead_model": "p:lead",
                "reviewer_model": "p:reviewer", "budget_cap_usd": 0.25
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["verification_level"], "cross_model_review_only")
        self.assertEqual(mocked.await_count, 2)
        self.assertEqual(mocked.await_args_list[0].args[2], 800)


if __name__ == "__main__":
    unittest.main()
