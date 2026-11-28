import unittest
from datetime import timezone

from match_factor.ingest.valuebetennis import normalize_row


class ValuebetennisNormalizationTests(unittest.TestCase):
    def setUp(self):
        self.row = {
            "match_id": "abc-123",
            "date": "2026-06-15T12:30:00Z",
            "tournoi": "Example Open",
            "categorie": "Main tour",
            "surface": "Hard",
            "tour": "7",
            "joueur1": "Player One",
            "joueur1_id": "101",
            "joueur2": "Player Two",
            "joueur2_id": "202",
            "vainqueur_id": "202",
            "score": "6-4 3-6 6-2",
            "duree_min": "128",
            "cote1_ouverture": "1.80",
            "cote2_ouverture": "2.10",
            "cote1_cloture": "1.75",
            "cote2_cloture": "2.20",
        }

    def test_normalizes_event_and_winner(self):
        item = normalize_row(self.row)
        self.assertEqual(item["external_id"], "abc-123")
        self.assertEqual(item["event_start_utc"].tzinfo, timezone.utc)
        self.assertEqual(item["winner_role"], "player2")
        self.assertEqual(item["duration_minutes"], 128)
        self.assertEqual(item["opening"]["player1"], 1.8)

    def test_preserves_unknown_winner_as_unknown(self):
        self.row["vainqueur_id"] = "999"
        item = normalize_row(self.row)
        self.assertIsNone(item["winner_role"])

    def test_rejects_missing_event_id(self):
        self.row["match_id"] = ""
        with self.assertRaises(ValueError):
            normalize_row(self.row)

    def test_comma_decimal_odds(self):
        self.row["cote1_ouverture"] = "1,85"
        item = normalize_row(self.row)
        self.assertEqual(item["opening"]["player1"], 1.85)


if __name__ == "__main__":
    unittest.main()
