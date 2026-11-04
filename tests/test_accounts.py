import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import accounts
import web_app


class AccountApiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "DATABASE_URL": "sqlite://",
            "HUB_SIGNUP_CODE": "test-invite-code",
            "RENDER": "",
        }, clear=False)
        self.env.start()
        accounts._engines.clear()
        self.client = TestClient(web_app.app)

    def tearDown(self):
        self.client.close()
        for engine in accounts._engines.values():
            engine.dispose()
        accounts._engines.clear()
        self.env.stop()

    def register(self, email="person@example.com"):
        return self.client.post("/api/auth/register", json={
            "email": email,
            "password": "a-very-long-test-password",
            "invite_code": "test-invite-code",
        })

    def test_registration_requires_invite_and_creates_account_session(self):
        response = self.register()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["email"], "person@example.com")
        self.assertTrue(self.client.get("/api/auth/me").json()["authenticated"])

    def test_duplicate_email_is_rejected(self):
        self.assertEqual(self.register().status_code, 200)
        duplicate = self.register()
        self.assertEqual(duplicate.status_code, 409)

    def test_account_login_and_logout(self):
        self.assertEqual(self.register().status_code, 200)
        self.client.post("/api/auth/logout", json={})
        response = self.client.post("/api/auth/login", json={
            "email": "PERSON@example.com",
            "password": "a-very-long-test-password",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.client.get("/api/auth/me").json()["authenticated"])
        self.client.post("/api/auth/logout", json={})
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_invalid_invitation_code_is_rejected(self):
        response = self.client.post("/api/auth/register", json={
            "email": "person@example.com",
            "password": "a-very-long-test-password",
            "invite_code": "wrong",
        })
        self.assertEqual(response.status_code, 403)

    def test_registration_requires_a_long_password(self):
        response = self.client.post("/api/auth/register", json={
            "email": "person@example.com",
            "password": "short",
            "invite_code": "test-invite-code",
        })
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
