import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, select

import accounts
import conversations
from accounts import Base, User
from conversations import Conversation, Message, UsageEvent


class ConversationPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_url = "sqlite:///" + os.path.join(self.temp_dir.name, "test.db")
        self.engine = create_engine(self.database_url)
        Base.metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            from sqlalchemy import insert
            connection.execute(insert(User).values(
                id="user-one", email="one@example.test", password_hash="test-hash"
            ))
            connection.execute(insert(User).values(
                id="user-two", email="two@example.test", password_hash="test-hash"
            ))
        accounts._engines.clear()
        self.env = patch.dict(os.environ, {"DATABASE_URL": self.database_url})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        accounts._engines.clear()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_persists_only_new_user_turn_and_assistant_reply(self):
        request = object()
        with patch.object(conversations, "account_user", return_value={"id": "user-one"}):
            conversation_id = conversations.persist_chat(
                request, None, "provider:model",
                [
                    {"role": "user", "content": "Earlier question"},
                    {"role": "assistant", "content": "Earlier answer"},
                    {"role": "user", "content": "Latest question"},
                ],
                "Latest answer",
                {"prompt_tokens": 12, "completion_tokens": 7},
            )

        with self.engine.connect() as connection:
            conversation_user_id = connection.execute(
                select(Conversation.user_id).where(Conversation.id == conversation_id)
            ).scalar_one()
            messages = connection.execute(
                select(Message.role, Message.content).where(Message.conversation_id == conversation_id)
            ).all()
            usage = connection.execute(
                select(UsageEvent.input_tokens, UsageEvent.output_tokens,
                       UsageEvent.provider_id, UsageEvent.model_id)
                .where(UsageEvent.conversation_id == conversation_id)
            ).one()

        self.assertEqual(conversation_user_id, "user-one")
        self.assertEqual({message.role for message in messages}, {"user", "assistant"})
        self.assertEqual({message.content for message in messages},
                         {"Latest question", "Latest answer"})
        self.assertEqual(usage[0], 12)
        self.assertEqual(usage[1], 7)
        self.assertEqual(usage[2], "provider")
        self.assertEqual(usage[3], "model")

    def test_cannot_append_to_another_users_conversation(self):
        with patch.object(conversations, "account_user", return_value={"id": "user-one"}):
            conversation_id = conversations.persist_chat(
                object(), None, "provider:model",
                [{"role": "user", "content": "Private"}], "Reply"
            )

        with patch.object(conversations, "account_user", return_value={"id": "user-two"}):
            with self.assertRaises(HTTPException) as raised:
                conversations.persist_chat(
                    object(), conversation_id, "provider:model",
                    [{"role": "user", "content": "Attempt"}], "No access"
                )

        self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
