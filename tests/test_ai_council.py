import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import web_app
from ai_council import build_critic_prompt, estimate_council_cost


def configured_models(input_price=1.0, output_price=2.0):
    common = {
        "provider_name": "Test Provider",
        "base_url": "https://private.example/v1",
        "api_key": "never-return-this-secret",
        "input_cost_per_1m_usd": input_price,
        "output_cost_per_1m_usd": output_price,
        "input_modalities": ["text"],
    }
    return {
        "test:lead": {
            **common, "id": "test:lead", "model": "lead-model",
            "display_name": "Lead Model",
        },
        "test:critic": {
            **common, "id": "test:critic", "model": "critic-model",
            "display_name": "Critic Model",
        },
    }


class CouncilPrimitiveTests(unittest.TestCase):
    def test_estimate_counts_two_bounded_model_calls(self):
        models = configured_models()
        estimate = estimate_council_cost("Plan a product launch", models["test:lead"], models["test:critic"])
        self.assertEqual(estimate["model_calls"], 2)
        self.assertEqual(estimate["max_output_tokens_per_model"], 800)
        self.assertGreater(estimate["estimated_max_cost_usd"], 0)

    def test_estimate_rejects_missing_or_invalid_pricing(self):
        models = configured_models(input_price=None)
        with self.assertRaises(ValueError):
            estimate_council_cost("Task", models["test:lead"], models["test:critic"])
        models["test:lead"]["input_cost_per_1m_usd"] = float("nan")
        with self.assertRaises(ValueError):
            estimate_council_cost("Task", models["test:lead"], models["test:critic"])

    def test_critic_prompt_keeps_task_and_answer_context(self):
        prompt = build_critic_prompt("Build a budget", "Revenue is 100.")
        self.assertIn("Build a budget", prompt)
        self.assertIn("Revenue is 100.", prompt)


class CouncilEndpointTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "HUB_ACCESS_PASSWORD": "correct-horse-battery",
            "HUB_SESSION_SECRET": "test-session-secret",
        }, clear=False)
        self.env.start()
        self.client = TestClient(web_app.app)
        self.client.post("/api/login", json={"password": "correct-horse-battery"})

    def tearDown(self):
        self.client.close()
        self.env.stop()

    def payload(self, budget=1.0):
        return {
            "prompt": "Create a short launch plan",
            "lead_model": "test:lead",
            "critic_model": "test:critic",
            "budget_cap_usd": budget,
        }

    def test_council_requires_authentication(self):
        client = TestClient(web_app.app)
        response = client.post("/api/council/run", json=self.payload())
        client.close()
        self.assertEqual(response.status_code, 401)

    def test_council_refuses_to_run_without_pricing(self):
        with patch.object(web_app, "load_models", return_value=configured_models(input_price=None)):
            with patch.object(web_app.httpx, "AsyncClient") as provider:
                response = self.client.post("/api/council/run", json=self.payload())
        self.assertEqual(response.status_code, 503)
        provider.assert_not_called()

    def test_council_refuses_budget_overrun_before_provider_calls(self):
        with patch.object(web_app, "load_models", return_value=configured_models()):
            with patch.object(web_app.httpx, "AsyncClient") as provider:
                response = self.client.post("/api/council/run", json=self.payload(budget=0.000001))
        self.assertEqual(response.status_code, 402)
        provider.assert_not_called()

    def test_council_runs_two_models_and_returns_attribution(self):
        calls = []

        class FakeResponse:
            def __init__(self, model):
                self.model = model

            def raise_for_status(self):
                return None

            def json(self):
                answer = "Initial plan" if self.model == "lead-model" else "Add a risk section."
                return {
                    "choices": [{"message": {"content": answer}}],
                    "usage": {"prompt_tokens": 20, "completion_tokens": 30},
                }

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, url, headers, json):
                calls.append(json["model"])
                return FakeResponse(json["model"])

        with patch.object(web_app, "load_models", return_value=configured_models()):
            with patch.object(web_app.httpx, "AsyncClient", FakeAsyncClient):
                response = self.client.post("/api/council/run", json=self.payload())

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(calls, ["lead-model", "critic-model"])
        self.assertEqual(result["mode"], "two_model_review")
        self.assertEqual(result["lead"]["answer"], "Initial plan")
        self.assertEqual(result["critic"]["review"], "Add a risk section.")
        self.assertTrue(result["critic"]["available"])
        self.assertEqual(result["model_calls"], 2)
        self.assertNotIn("never-return-this-secret", response.text)
        self.assertNotIn("private.example", response.text)


    def test_council_returns_partial_answer_when_critic_fails_without_usage(self):
        class FakeResponse:
            def __init__(self, critic=False):
                self.critic = critic

            def raise_for_status(self):
                if self.critic:
                    request = web_app.httpx.Request("POST", "https://private.example/v1/chat/completions")
                    response = web_app.httpx.Response(503, request=request)
                    raise web_app.httpx.HTTPStatusError("critic unavailable", request=request, response=response)

            def json(self):
                return {"choices": [{"message": {"content": "Lead proposal"}}]}

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                self.calls = 0

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, url, headers, json):
                self.calls += 1
                return FakeResponse(critic=self.calls == 2)

        with patch.object(web_app, "load_models", return_value=configured_models()):
            with patch.object(web_app.httpx, "AsyncClient", FakeAsyncClient):
                response = self.client.post("/api/council/run", json=self.payload())

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["lead"]["answer"], "Lead proposal")
        self.assertFalse(result["critic"]["available"])
        self.assertEqual(result["model_calls"], 1)
        self.assertIsNone(result["actual_cost_usd"])

    def test_council_requires_distinct_models(self):
        body = self.payload()
        body["critic_model"] = body["lead_model"]
        response = self.client.post("/api/council/run", json=body)
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
