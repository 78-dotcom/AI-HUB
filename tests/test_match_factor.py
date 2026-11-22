import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import web_app


class MatchFactorAccessTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "HUB_ACCESS_PASSWORD": "test-password",
            "HUB_SESSION_SECRET": "test-session-secret",
            "ODDS_API_KEY": "",
        }, clear=False)
        self.env.start()
        self.client = TestClient(web_app.app)

    def tearDown(self):
        self.client.close()
        self.env.stop()

    def test_match_factor_status_requires_authentication(self):
        response = self.client.get("/api/match-factor/status")
        self.assertEqual(response.status_code, 401)

    def test_match_factor_page_requires_authentication(self):
        response = self.client.get("/match-factor")
        self.assertEqual(response.status_code, 401)

    def test_match_factor_status_never_exposes_api_key(self):
        self.client.post("/api/login", json={"password": "test-password"})
        with patch.dict(os.environ, {"ODDS_API_KEY": "private-test-key"}, clear=False):
            response = self.client.get("/api/match-factor/status")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["configured"])
        self.assertNotIn("private-test-key", response.text)

    def test_odds_endpoint_rejects_invalid_market(self):
        self.client.post("/api/login", json={"password": "test-password"})
        response = self.client.get(
            "/api/match-factor/odds?sport_key=icehockey_nhl&markets=outrights"
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
