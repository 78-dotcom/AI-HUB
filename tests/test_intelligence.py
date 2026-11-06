import unittest

from intelligence import classify_task, public_routing_payload, select_model


class TaskClassificationTests(unittest.TestCase):
    def test_classifies_common_task_types(self):
        self.assertEqual(classify_task("Help me debug this Python code").task, "coding")
        self.assertEqual(classify_task("Find sources and research the latest market").task, "research")
        self.assertEqual(classify_task("Проанализируй договор PDF").task, "document")
        self.assertEqual(classify_task("Write a creative story").task, "creative")
        self.assertEqual(classify_task("Помоги с продажами и клиентскими заявками").task, "business")
        self.assertEqual(classify_task("Hello there").task, "general")


class ModelRoutingTests(unittest.TestCase):
    def setUp(self):
        self.models = {
            "provider:general": {
                "id": "provider:general", "provider": "provider",
                "provider_name": "Provider", "model": "general",
                "display_name": "General", "category": "general",
                "capabilities": ["chat"], "input_modalities": ["text"],
                "output_modalities": ["text"], "context_window": 32000,
                "api_key": "must-not-leak", "base_url": "https://secret.example",
            },
            "provider:coder": {
                "id": "provider:coder", "provider": "provider",
                "provider_name": "Provider", "model": "coder",
                "display_name": "Coder", "category": "coding",
                "capabilities": ["chat", "code"], "input_modalities": ["text"],
                "output_modalities": ["text"], "context_window": 64000,
                "api_key": "must-not-leak", "base_url": "https://secret.example",
            },
            "provider:writer": {
                "id": "provider:writer", "provider": "provider",
                "provider_name": "Provider", "model": "writer",
                "display_name": "Writer", "category": "creative",
                "capabilities": ["chat", "creative"], "input_modalities": ["text"],
                "output_modalities": ["text"],
            },
        }

    def test_selects_specialist_for_coding(self):
        decision = select_model(self.models, "Please debug this code")
        self.assertEqual(decision.task, "coding")
        self.assertEqual(decision.model_id, "provider:coder")

    def test_preference_breaks_close_tie_without_overriding_specialist(self):
        candidates = {
            "provider:general": self.models["provider:general"],
            "provider:general-alt": {
                **self.models["provider:general"],
                "id": "provider:general-alt",
                "model": "general-alt",
                "display_name": "General Alt",
            },
            "provider:coder": self.models["provider:coder"],
        }
        decision = select_model(candidates, "Hello", "provider:general-alt")
        self.assertEqual(decision.model_id, "provider:general-alt")
        specialist = select_model(self.models, "Debug Python", "provider:writer")
        self.assertEqual(specialist.model_id, "provider:coder")

    def test_stable_fallback_when_specialist_is_missing(self):
        models = {"provider:general": self.models["provider:general"]}
        decision = select_model(models, "Debug this code")
        self.assertEqual(decision.model_id, "provider:general")

    def test_empty_catalogue_returns_none(self):
        self.assertIsNone(select_model({}, "Hello"))

    def test_public_payload_never_exposes_credentials_or_endpoints(self):
        decision = select_model(self.models, "Debug this code")
        payload = public_routing_payload(decision, self.models)
        serialized = str(payload)
        self.assertNotIn("must-not-leak", serialized)
        self.assertNotIn("secret.example", serialized)
        self.assertEqual(payload["selected_model"]["id"], "provider:coder")


if __name__ == "__main__":
    unittest.main()
