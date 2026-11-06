import os
import tempfile
import unittest
from decimal import Decimal
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert

import accounts
import wallet
import web_app
from accounts import Base, User


class HubCreditsLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_url = "sqlite:///" + os.path.join(self.temp_dir.name, "credits.db")
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
        self.owner_patch = patch.object(wallet, "account_user", side_effect=lambda request: {"id": "user-one"})
        self.owner_patch.start()
        self.client = TestClient(web_app.app)

    def tearDown(self):
        self.client.close()
        self.owner_patch.stop()
        self.env.stop()
        accounts._engines.clear()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_balance_and_ledger_are_account_scoped(self):
        wallet.record_credit_entry("user-one", "pay_evt_1", "purchase", Decimal("250"))
        wallet.record_credit_entry("user-two", "pay_evt_2", "purchase", Decimal("900"))
        balance = self.client.get("/api/credits/balance").json()
        self.assertEqual(balance["balance"], "250.0000")
        self.assertFalse(balance["cash_redemption_enabled"])
        ledger = self.client.get("/api/credits/ledger").json()["entries"]
        self.assertEqual(len(ledger), 1)
        self.assertEqual(ledger[0]["delta_credits"], "250.0000")

    def test_idempotency_prevents_duplicate_credit_issue(self):
        first = wallet.record_credit_entry("user-one", "same-event", "purchase", Decimal("100"))
        second = wallet.record_credit_entry("user-one", "same-event", "purchase", Decimal("100"))
        self.assertEqual(first, second)
        self.assertEqual(self.client.get("/api/credits/balance").json()["balance"], "100.0000")

    def test_negative_balance_and_invalid_events_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Insufficient"):
            wallet.record_credit_entry("user-one", "overspend", "spend", Decimal("-1"))
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            wallet.record_credit_entry("user-one", "unknown", "transfer", Decimal("10"))

    def test_duplicate_spend_does_not_double_deduct(self):
        wallet.record_credit_entry("user-one", "purchase", "purchase", Decimal("100"))
        first = wallet.record_credit_entry("user-one", "spend-1", "spend", Decimal("-30"))
        second = wallet.record_credit_entry("user-one", "spend-1", "spend", Decimal("-30"))
        self.assertEqual(first, second)
        self.assertEqual(self.client.get("/api/credits/balance").json()["balance"], "70.0000")

    def test_credit_routes_require_individual_account(self):
        with patch.object(wallet, "account_user", return_value=None):
            response = self.client.get("/api/credits/balance")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
