import base64
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import web_app


class DocumentEndpointTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "HUB_ACCESS_PASSWORD": "correct-horse-battery",
            "HUB_SESSION_SECRET": "test-session-secret",
            "AI_PROVIDERS_JSON": "[]",
        }, clear=False)
        self.env.start()
        self.client = TestClient(web_app.app)

    def tearDown(self):
        self.client.close()
        self.env.stop()

    def test_extract_requires_authentication(self):
        response = self.client.post("/api/files/extract", json={
            "filename": "notes.txt",
            "content_base64": base64.b64encode(b"hello").decode(),
        })
        self.assertEqual(response.status_code, 401)

    def test_extracts_text_after_login_without_persisting(self):
        login = self.client.post("/api/login", json={"password": "correct-horse-battery"})
        self.assertEqual(login.status_code, 200)
        response = self.client.post("/api/files/extract", json={
            "filename": "notes.txt",
            "content_base64": base64.b64encode(b"hello AI HUB").decode(),
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["text"], "hello AI HUB")
        self.assertFalse(response.json()["stored"])

    def test_rejects_unsupported_file(self):
        self.client.post("/api/login", json={"password": "correct-horse-battery"})
        response = self.client.post("/api/files/extract", json={
            "filename": "program.exe",
            "content_base64": base64.b64encode(b"data").decode(),
        })
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
