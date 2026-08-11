import json
import unittest
from pathlib import Path
from statistics import mean

from src.dashboard import build_kpi_dashboard as agent_dashboard
from src.dashboard import build_supervisor_dashboard as supervisor


class SupervisorDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = agent_dashboard.load_config(agent_dashboard.DEFAULT_CONFIG)
        cls.calls = agent_dashboard.normalize_calls(
            agent_dashboard.read_calls_via_sqlite(agent_dashboard.DEFAULT_INPUT)
        )
        agent_dashboard.validate_input(cls.calls)
        cls.artifact = supervisor.build_artifact(
            cls.calls,
            cls.config,
            generated_at="2026-07-14T22:30:00+00:00",
        )

    def test_team_and_agent_grains_reconcile(self):
        datasets = self.artifact["snapshot"]["datasets"]
        self.assertEqual(len(datasets["team_summary"]), 3)
        self.assertEqual(len(datasets["agent_overview"]), 30)
        self.assertEqual(len(datasets["coaching_queue"]), 30)
        self.assertEqual(len(datasets["review_calls"]), 60)
        self.assertEqual(len(datasets["team_behavior_coverage"]), 24)
        self.assertEqual(len(datasets["cross_agent_suggestions"]), 7)

    def test_end_view_reconciles_to_all_100_calls(self):
        end = next(
            row for row in self.artifact["snapshot"]["datasets"]["team_summary"]
            if row["stage_id"] == "end"
        )
        self.assertEqual(end["calls_reviewed"], 100)
        expected_aht = round(mean(float(call["estimated_aht_sec"]) for call in self.calls), 2)
        self.assertEqual(end["team_estimated_aht_sec"], expected_aht)

    def test_priority_distribution_reconciles_to_ten_agents(self):
        rows = self.artifact["snapshot"]["datasets"]["priority_distribution"]
        for stage_id in ("start", "live", "end"):
            self.assertEqual(
                sum(row["agent_count"] for row in rows if row["stage_id"] == stage_id),
                10,
            )

    def test_filter_targets_every_supervisor_dataset(self):
        datasets = set(self.artifact["snapshot"]["datasets"])
        filter_spec = self.artifact["manifest"]["filters"][0]
        covered = {filter_spec["dataset"]} | {
            target["dataset"] for target in filter_spec["targets"]
        }
        self.assertEqual(covered, datasets)

    def test_review_queue_references_valid_calls(self):
        valid_calls = {call["call_id"] for call in self.calls}
        rows = self.artifact["snapshot"]["datasets"]["review_calls"]
        self.assertTrue(all(row["call_id"] in valid_calls for row in rows))
        self.assertTrue(all(row["evidence"] for row in rows))

    def test_supervisor_board_excludes_synthetic_business_kpis(self):
        payload = json.dumps(self.artifact).casefold()
        self.assertNotIn("csat_demo", payload)
        self.assertNotIn("synthetic_business_kpis", payload)

    def test_cross_agent_suggestions_hide_peer_identity_and_block_outcomes(self):
        valid_calls = {call["call_id"] for call in self.calls}
        rows = self.artifact["snapshot"]["datasets"]["cross_agent_suggestions"]
        self.assertTrue(rows)
        for row in rows:
            self.assertTrue(row["peer_identity_hidden"])
            self.assertFalse(row["outcome_association_available"])
            self.assertGreaterEqual(row["context_calls"], 4)
            self.assertGreaterEqual(row["context_anonymous_agents"], 2)
            self.assertFalse({"agent_id", "agent_name", "agent_label"} & set(row))
            self.assertTrue(set(row["supporting_call_ids"]) <= valid_calls)

    def test_sources_are_relative_and_artifact_is_serializable(self):
        self.assertTrue(
            all(not Path(source["path"]).is_absolute() for source in self.artifact["sources"])
        )
        loaded = json.loads(json.dumps(self.artifact))
        self.assertEqual(loaded["surface"], "dashboard")
        self.assertEqual(loaded["manifest"]["version"], 1)


if __name__ == "__main__":
    unittest.main()
