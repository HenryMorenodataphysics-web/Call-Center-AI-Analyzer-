import unittest

from src.personalization import build_cross_agent_learning as builder
from src.personalization import evaluate_cross_agent_learning as evaluator


class CrossAgentLearningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.calls = builder.read_calls(builder.DEFAULT_CALLS)
        cls.stage_config = builder.read_json(builder.DEFAULT_STAGES)
        cls.contract = builder.read_json(builder.DEFAULT_CONTRACT)
        cls.artifact = builder.build_artifact(
            cls.calls,
            cls.stage_config,
            cls.contract,
            generated_at="2026-08-11T03:14:11+00:00",
        )

    def test_population_and_early_stage_boundary(self):
        population = self.artifact["snapshot"]["population"]
        suggestions = self.artifact["snapshot"]["datasets"]["cross_agent_suggestions"]
        self.assertEqual(population["eligible_context_rows"], 4)
        self.assertEqual(population["suggestions"], 7)
        self.assertTrue(all(row["stage_id"] == "end" for row in suggestions))

    def test_suggestions_are_context_matched_anonymous_and_cited(self):
        valid_calls = {row["call_id"] for row in self.calls}
        suggestions = self.artifact["snapshot"]["datasets"]["cross_agent_suggestions"]
        for row in suggestions:
            self.assertEqual(
                row["context_status"], "dataset_proxy_not_approved_business_type"
            )
            self.assertGreaterEqual(row["context_calls"], 4)
            self.assertGreaterEqual(row["context_anonymous_agents"], 2)
            self.assertGreaterEqual(row["behavior_calls"], 2)
            self.assertGreaterEqual(row["behavior_anonymous_agents"], 2)
            self.assertTrue(row["peer_identity_hidden"])
            self.assertFalse(row["outcome_association_available"])
            self.assertFalse({"agent_id", "agent_name", "agent_label"} & set(row))
            self.assertTrue(set(row["supporting_call_ids"]) <= valid_calls)

    def test_portfolio_gate_passes_while_operational_gate_is_blocked(self):
        result = evaluator.evaluate(
            self.artifact,
            evaluator.read_json(evaluator.DEFAULT_CONFIG),
            self.contract,
            evaluator.canonical_call_ids(evaluator.DEFAULT_CALLS),
        )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["operational_outcome_gate"]["status"], "blocked")
        self.assertEqual(
            result["operational_outcome_gate"]["code"],
            "NO_GOVERNED_OUTCOMES_FOR_CROSS_AGENT_LEARNING",
        )


if __name__ == "__main__":
    unittest.main()
