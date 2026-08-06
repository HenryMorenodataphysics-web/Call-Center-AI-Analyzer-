import json
import unittest
from pathlib import Path

from src.dashboard import build_kpi_dashboard as dashboard


class KpiDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = dashboard.load_config(dashboard.DEFAULT_CONFIG)
        cls.calls = dashboard.normalize_calls(
            dashboard.read_calls_via_sqlite(dashboard.DEFAULT_INPUT)
        )
        dashboard.validate_input(cls.calls)
        cls.artifact = dashboard.build_artifact(
            cls.calls,
            cls.config,
            generated_at="2026-07-14T20:00:00+00:00",
        )

    def test_synthetic_fixture_is_deterministic(self):
        first = dashboard.synthetic_call_kpis(self.calls[0])
        second = dashboard.synthetic_call_kpis(self.calls[0])
        self.assertEqual(first, second)
        self.assertTrue(0 <= first["csat_demo"] <= 1)
        self.assertTrue(0 <= first["qa_demo"] <= 1)
        self.assertTrue(0 <= first["five_star_demo"] <= 1)

    def test_artifact_has_10_agents_and_three_shift_views(self):
        rows = self.artifact["snapshot"]["datasets"]["kpi_summary"]
        self.assertEqual(len(rows), 30)
        self.assertEqual(len({row["agent_id"] for row in rows}), 10)
        self.assertEqual(len({row["stage"] for row in rows}), 3)
        self.assertEqual({row["calls_considered"] for row in rows}, {3, 7, 10})

    def test_every_kpi_exposes_goal_projection_source_and_freshness(self):
        rows = self.artifact["snapshot"]["datasets"]["kpi_status"]
        self.assertEqual(len(rows), 10 * 3 * 6)
        for row in rows:
            self.assertTrue(row["goal"])
            self.assertTrue(row["projection"])
            self.assertTrue(row["source_type"])
            self.assertTrue(row["freshness"])
            self.assertTrue(row["recommended_action"])

    def test_business_outcomes_are_labeled_synthetic_demo(self):
        synthetic_rows = [
            row
            for row in self.artifact["snapshot"]["datasets"]["kpi_status"]
            if row["source_type"] == "synthetic_demo"
        ]
        self.assertEqual(len(synthetic_rows), 10 * 3 * 4)
        self.assertTrue(all("synthetic demo" in row["metric"].lower() for row in synthetic_rows))
        self.assertEqual(self.artifact["snapshot"]["status"], "fixture")

    def test_filters_target_every_dashboard_dataset(self):
        datasets = set(self.artifact["snapshot"]["datasets"])
        for filter_spec in self.artifact["manifest"]["filters"]:
            covered = {filter_spec["dataset"]} | {
                target["dataset"] for target in filter_spec["targets"]
            }
            self.assertEqual(covered, datasets)

    def test_call_highlights_reference_valid_calls(self):
        valid_calls = {call["call_id"] for call in self.calls}
        rows = self.artifact["snapshot"]["datasets"]["call_highlights"]
        self.assertEqual(len(rows), 10 * 3 * 2)
        self.assertTrue(all(row["call_id"] in valid_calls for row in rows))
        self.assertTrue(all(row["evidence"] for row in rows))

    def test_artifact_contains_no_absolute_source_paths(self):
        for source in self.artifact["sources"]:
            self.assertFalse(Path(source["path"]).is_absolute())

    def test_artifact_is_json_serializable(self):
        artifact = dashboard.build_artifact(
            self.calls,
            self.config,
            generated_at="2026-07-14T20:00:00+00:00",
        )
        loaded = json.loads(json.dumps(artifact))
        self.assertEqual(loaded["surface"], "dashboard")
        self.assertEqual(loaded["manifest"]["version"], 1)


if __name__ == "__main__":
    unittest.main()
