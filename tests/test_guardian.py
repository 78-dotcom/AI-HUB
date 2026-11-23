from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import guardian_app


class GuardianChecksTests(unittest.TestCase):
    def test_incomplete_run_is_flagged(self):
        payload = guardian_app.AuditRequest(
            project="AI HUB",
            task_name="deploy",
            status="running",
            claims=["deployment completed"],
            evidence=[],
            actions_claimed=["deploy"],
            actions_confirmed=[],
        )
        checks = guardian_app.deterministic_checks(payload)
        codes = {item["code"] for item in checks}
        self.assertIn("RUN_NOT_CONFIRMED", codes)
        self.assertIn("NO_EVIDENCE", codes)
        self.assertIn("UNCONFIRMED_ACTIONS", codes)
        self.assertIn("CLAIMS_WITHOUT_EVIDENCE", codes)

    def test_repeated_errors_are_flagged(self):
        payload = guardian_app.AuditRequest(
            project="AI HUB",
            task_name="test",
            previous_errors=["DATABASE_URL missing", "timeout"],
            current_errors=["DATABASE_URL missing"],
        )
        checks = guardian_app.deterministic_checks(payload)
        self.assertIn("REPEATED_ERRORS", {item["code"] for item in checks})

    def test_clean_payload_only_gets_provisional_basic_check(self):
        payload = guardian_app.AuditRequest(
            project="AI HUB",
            task_name="unit tests",
            status="completed",
            evidence=["CI run passed"],
            actions_claimed=["run tests"],
            actions_confirmed=["run tests"],
        )
        checks = guardian_app.deterministic_checks(payload)
        self.assertEqual([item["code"] for item in checks], ["BASIC_CHECKS_PASSED"])

    def test_health_never_calls_ephemeral_storage_fully_ready(self):
        with patch.object(guardian_app, "initialize", return_value=None), \
             patch.object(guardian_app, "DB_MODE", "ephemeral_sqlite"), \
             patch.object(guardian_app, "MODEL_API_KEY", ""), \
             patch.object(guardian_app, "ADMIN_TOKEN", "test-token"):
            result = guardian_app.health()
        self.assertEqual(result["status"], "degraded")
        self.assertFalse(result["database_persistent"])
        self.assertIn("DATABASE_URL", result["missing_configuration"])
        self.assertIn("GUARDIAN_MODEL_API_KEY", result["missing_configuration"])

    def test_authorization_rejects_missing_token(self):
        with patch.object(guardian_app, "ADMIN_TOKEN", "expected-token"):
            with self.assertRaises(Exception) as caught:
                guardian_app.authorize("Bearer wrong-token")
        self.assertEqual(getattr(caught.exception, "status_code", None), 401)


if __name__ == "__main__":
    unittest.main()
