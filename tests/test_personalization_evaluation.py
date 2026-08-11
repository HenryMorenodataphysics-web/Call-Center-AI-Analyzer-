import unittest

from src.personalization.evaluate_personalization import (
    DEFAULT_ARTIFACT,
    DEFAULT_CALLS,
    DEFAULT_CONFIG,
    canonical_call_ids,
    evaluate,
    markdown_report,
    read_json,
)


class PersonalizationEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = evaluate(
            read_json(DEFAULT_ARTIFACT),
            read_json(DEFAULT_CONFIG),
            canonical_call_ids(DEFAULT_CALLS),
        )

    def test_portfolio_personalization_gates_pass(self):
        self.assertEqual(self.result["status"], "pass")
        self.assertTrue(
            all(
                item["status"] == "pass"
                for item in self.result["portfolio_gate"]["checks"]
            )
        )

    def test_operational_history_gate_remains_blocked(self):
        gate = self.result["operational_longitudinal_gate"]
        self.assertEqual(gate["status"], "blocked")
        self.assertEqual(gate["code"], "NO_GOVERNED_DATED_HISTORY")
        self.assertIn("governed_event_timestamp", gate["required_fields"])

    def test_report_states_both_decisions(self):
        report = markdown_report(self.result)
        self.assertIn("Portfolio status: **PASS**", report)
        self.assertIn("Operational longitudinal status: **BLOCKED**", report)


if __name__ == "__main__":
    unittest.main()
