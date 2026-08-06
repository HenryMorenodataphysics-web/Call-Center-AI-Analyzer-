import unittest
from unittest.mock import patch

from src.validation.evaluate_risk_review_pilot import evaluate
from src.validation.prepare_risk_review_pilot import build_pilot


class RiskReviewPilotTests(unittest.TestCase):
    def test_sample_has_three_unique_calls_per_agent(self):
        blinded, key = build_pilot()
        self.assertEqual(len(blinded), 30)
        self.assertEqual(len({row["call_id"] for row in blinded}), 30)
        counts = {}
        for row in key:
            counts[row["agent_id"]] = counts.get(row["agent_id"], 0) + 1
        self.assertEqual(set(counts.values()), {3})
        self.assertEqual({row["sample_stratum"] for row in key}, {"agent_min", "agent_middle", "agent_max"})

    def test_blinded_file_excludes_proxy_information(self):
        blinded, _ = build_pilot()
        forbidden = {"conversation_risk_score", "conversation_risk_level", "proxy_review_flag", "reason_codes"}
        self.assertFalse(forbidden.intersection(blinded[0]))

    def test_evaluator_requires_twenty_completed_labels(self):
        blinded, key = build_pilot()
        with patch(
            "src.validation.evaluate_risk_review_pilot.read_csv",
            side_effect=[blinded, key],
        ):
            with self.assertRaisesRegex(ValueError, "At least 20"):
                evaluate()


if __name__ == "__main__":
    unittest.main()
