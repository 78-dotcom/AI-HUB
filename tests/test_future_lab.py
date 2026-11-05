import unittest

from future_lab import build_scenarios


class FutureLabTests(unittest.TestCase):
    def test_builds_three_transparent_stress_cases(self):
        result = build_scenarios(
            "Assess a small online store", "business", 12,
            [{"name": "monthly_sales", "current_value": 10000,
              "downside_change_pct": -20, "upside_change_pct": 30, "unit": "USD"}],
        )
        self.assertEqual(result["mode"], "assumption_stress_test")
        self.assertEqual([case["id"] for case in result["scenarios"]],
                         ["downside", "base", "upside"])
        self.assertEqual(result["scenarios"][0]["variables"][0]["projected_value"], 8000)
        self.assertEqual(result["scenarios"][2]["variables"][0]["projected_value"], 13000)
        self.assertEqual(result["scenarios"][1]["variables"][0]["projected_value"], 10000)
        self.assertIn("No probabilities", result["assumptions"][2])

    def test_rejects_invalid_horizon_and_duplicate_variables(self):
        with self.assertRaises(ValueError):
            build_scenarios("Goal", "business", 0, [{"name": "x", "current_value": 1,
                "downside_change_pct": 0, "upside_change_pct": 0}])
        variable = {"name": "x", "current_value": 1,
                    "downside_change_pct": 0, "upside_change_pct": 0}
        with self.assertRaises(ValueError):
            build_scenarios("Goal", "business", 12, [variable, variable])

    def test_rejects_non_finite_values(self):
        with self.assertRaises(ValueError):
            build_scenarios("Goal", "business", 12, [{"name": "x", "current_value": float("nan"),
                "downside_change_pct": 0, "upside_change_pct": 0}])


if __name__ == "__main__":
    unittest.main()
