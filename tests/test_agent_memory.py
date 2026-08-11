import json
import unittest

from src.copilot.service import CopilotService
from src.personalization.build_agent_memory import (
    DEFAULT_ARTIFACT,
    DEFAULT_CALLS,
    AgentMemoryRepository,
    read_calls,
    source_context,
)


class AgentMemoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifact = json.loads(DEFAULT_ARTIFACT.read_text(encoding="utf-8"))
        cls.rows = cls.artifact["snapshot"]["datasets"]["agent_memories"]
        cls.call_ids = {row["call_id"] for row in read_calls(DEFAULT_CALLS)}

    def test_artifact_reconciles_agents_calls_and_stages(self):
        population = self.artifact["snapshot"]["population"]
        self.assertEqual(population["agents"], 10)
        self.assertEqual(population["calls"], 100)
        self.assertEqual(population["memory_rows"], 30)
        self.assertEqual(population["end_stage_calls"], 100)
        self.assertEqual(
            {(row["agent_id"], row["stage_id"]) for row in self.rows},
            {
                (f"Agent_{number:03d}", stage)
                for number in range(1, 11)
                for stage in ("start", "live", "end")
            },
        )

    def test_cumulative_stage_memory_does_not_use_later_calls(self):
        repository = AgentMemoryRepository()
        start = repository.summary("Agent_001", "start")
        live = repository.summary("Agent_001", "live")
        end = repository.summary("Agent_001", "end")
        self.assertEqual(start["calls_analyzed"], 3)
        self.assertEqual(live["calls_analyzed"], 7)
        self.assertEqual(end["calls_analyzed"], 10)
        self.assertEqual(start["last_agent_call_number"], 3)
        self.assertEqual(live["last_agent_call_number"], 7)
        self.assertEqual(end["last_agent_call_number"], 10)

    def test_current_memory_preserves_low_confidence_and_history_boundary(self):
        self.assertTrue(all(row["sample_confidence"] == "low" for row in self.rows))
        self.assertTrue(
            all(
                row["longitudinal_status"]["status"] == "initial_snapshot_only"
                and not row["longitudinal_status"]["multiple_dated_snapshots_available"]
                for row in self.rows
            )
        )
        self.assertTrue(
            all(row["business_profile_status"] == "planned_not_resolved" for row in self.rows)
        )

    def test_personalization_tracks_self_history_without_fabricating_dates(self):
        for agent_id in {row["agent_id"] for row in self.rows}:
            agent_rows = {
                row["stage_id"]: row for row in self.rows if row["agent_id"] == agent_id
            }
            self.assertIsNone(
                agent_rows["start"]["personalization"]["self_history"]["previous_stage_id"]
            )
            self.assertEqual(
                agent_rows["live"]["personalization"]["self_history"]["previous_stage_id"],
                "start",
            )
            self.assertEqual(
                agent_rows["end"]["personalization"]["self_history"]["previous_stage_id"],
                "live",
            )
            self.assertTrue(
                all(
                    not row["personalization"]["time_window"]["governed_dates_available"]
                    for row in agent_rows.values()
                )
            )

    def test_personalized_recommendations_change_and_preserve_evidence(self):
        end_rows = [row for row in self.rows if row["stage_id"] == "end"]
        focuses = {
            row["personalization"]["recommendation"]["focus_behavior_id"]
            for row in end_rows
        }
        recommendations = {
            row["personalization"]["recommendation"]["text"] for row in end_rows
        }
        self.assertGreaterEqual(len(focuses), 2)
        self.assertGreaterEqual(len(recommendations), 8)
        for row in self.rows:
            recommendation = row["personalization"]["recommendation"]
            self.assertEqual(recommendation["sample_confidence"], "low")
            self.assertTrue(recommendation["supporting_call_ids"])
            self.assertTrue(set(recommendation["supporting_call_ids"]) <= self.call_ids)
            self.assertIn("no governed dated history", recommendation["interpretation_limit"])

    def test_pattern_evidence_references_canonical_calls(self):
        referenced = {
            call_id
            for row in self.rows
            for pattern in row["observed_strengths"] + row["coaching_opportunities"]
            for call_id in pattern["supporting_call_ids"] + pattern["missing_call_ids"]
        }
        self.assertTrue(referenced)
        self.assertTrue(referenced <= self.call_ids)

    def test_source_domain_is_explicitly_dataset_derived(self):
        context = source_context("en_AU_DeliveryService_1585416")
        self.assertEqual(context["language_market"], "en-AU")
        self.assertEqual(context["source_domain"], "DeliveryService")
        self.assertEqual(context["context_source"], "dataset_call_id_pattern")
        self.assertTrue(
            all(
                profile["context_source"] == "dataset_call_id_pattern"
                and "not an approved business call type"
                in profile["interpretation_limit"]
                for row in self.rows
                for profile in row["source_domain_profiles"]
            )
        )

    def test_copilot_uses_memory_tool_with_grounded_limits(self):
        response = CopilotService().ask(
            "Analyze my accumulated patterns and coaching needs",
            "Agent_001",
            "end",
        )
        self.assertTrue(response.grounded)
        self.assertIn("agent_memory", response.tool_calls)
        self.assertIn("Accumulated agent memory", response.answer)
        self.assertIn("Personalized recommendation", response.answer)
        self.assertIn("low sample confidence", response.answer)
        self.assertIn("not approved business call types", response.answer)
        self.assertTrue(
            any(citation.id == "agent-memory:Agent_001:end" for citation in response.citations)
        )


if __name__ == "__main__":
    unittest.main()
