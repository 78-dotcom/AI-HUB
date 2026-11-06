import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert

import accounts
import project_memory
import web_app
from accounts import Base, User


class ProjectMemoryApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_url = "sqlite:///" + os.path.join(self.temp_dir.name, "memory.db")
        self.engine = create_engine(self.database_url)
        Base.metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            connection.execute(insert(User).values(
                id="user-one", email="one@example.test", password_hash="test-hash"
            ))
            connection.execute(insert(User).values(
                id="user-two", email="two@example.test", password_hash="test-hash"
            ))
        accounts._engines.clear()
        self.env = patch.dict(os.environ, {"DATABASE_URL": self.database_url}, clear=False)
        self.env.start()
        self.owner_patch = patch.object(project_memory, "account_user", side_effect=lambda request: {"id": "user-one"})
        self.owner_patch.start()
        self.client = TestClient(web_app.app)

    def tearDown(self):
        self.client.close()
        self.owner_patch.stop()
        self.env.stop()
        accounts._engines.clear()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_create_list_update_delete_project_memory(self):
        created = self.client.post("/api/project-memory", json={
            "project_key": "ai-hub", "category": "decision",
            "title": "Product direction", "content": "Start with a web app.",
        })
        self.assertEqual(created.status_code, 201)
        entry = created.json()["entry"]
        self.assertEqual(entry["project_key"], "ai-hub")

        listed = self.client.get("/api/project-memory?project_key=ai-hub")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["entries"]), 1)

        updated = self.client.put(f"/api/project-memory/{entry['id']}", json={
            "category": "goal", "title": "Updated direction", "content": "Build the international web app first.",
        })
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["entry"]["category"], "goal")

        deleted = self.client.delete(f"/api/project-memory/{entry['id']}")
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(deleted.json()["deleted"])
        self.assertEqual(self.client.get("/api/project-memory").json()["entries"], [])

    def test_project_memory_rejects_oversized_or_invalid_project_key(self):
        response = self.client.post("/api/project-memory", json={
            "project_key": "../other-user", "category": "decision",
            "title": "Bad key", "content": "No",
        })
        self.assertEqual(response.status_code, 422)

    def test_project_memory_is_account_scoped(self):
        created = self.client.post("/api/project-memory", json={
            "project_key": "ai-hub", "category": "decision",
            "title": "Private", "content": "Only user one.",
        }).json()["entry"]
        with patch.object(project_memory, "account_user", return_value={"id": "user-two"}):
            response = self.client.get("/api/project-memory")
            self.assertEqual(response.json()["entries"], [])
            forbidden = self.client.delete(f"/api/project-memory/{created['id']}")
            self.assertEqual(forbidden.status_code, 404)

    def test_project_memory_requires_individual_account(self):
        with patch.object(project_memory, "account_user", return_value=None):
            response = self.client.get("/api/project-memory")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
