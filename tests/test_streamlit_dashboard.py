import unittest

from app.dashboard import (
    KPI_ARTIFACT,
    MEMORY_ARTIFACT,
    PROJECT_ROOT,
    SUPERVISOR_ARTIFACT,
    SURVEY_ARTIFACT,
    build_copilot_service,
    build_supervisor_agent_service,
    dataset_frames,
    filter_frame,
    load_artifacts,
    stage_labels,
)


class StreamlitDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kpi, cls.supervisor, cls.survey = load_artifacts()
        cls.kpi_frames = dataset_frames(cls.kpi)
        cls.supervisor_frames = dataset_frames(cls.supervisor)
        cls.survey_frames = dataset_frames(cls.survey)

    def test_stage_and_agent_filters_use_canonical_kpi_rows(self):
        stages = stage_labels(self.kpi_frames["kpi_summary"])
        self.assertEqual(list(stages), ["start", "live", "end"])

        row = filter_frame(
            self.kpi_frames["kpi_summary"], "end", "Agent_001"
        )
        self.assertEqual(len(row), 1)
        self.assertEqual(int(row.iloc[0]["calls_considered"]), 10)

    def test_end_stage_reconciles_to_complete_portfolio(self):
        team = filter_frame(self.supervisor_frames["team_summary"], "end")
        self.assertEqual(len(team), 1)
        self.assertEqual(int(team.iloc[0]["calls_reviewed"]), 100)
        self.assertEqual(int(team.iloc[0]["agents_in_view"]), 10)

    def test_every_end_stage_agent_has_coaching_and_call_evidence(self):
        queue = filter_frame(self.supervisor_frames["coaching_queue"], "end")
        calls = filter_frame(self.supervisor_frames["review_calls"], "end")
        self.assertEqual(queue["agent_id"].nunique(), 10)
        self.assertEqual(calls["agent_id"].nunique(), 10)
        self.assertFalse(queue[["why_now", "next_action"]].isna().any().any())

    def test_streamlit_copilot_uses_existing_grounded_service(self):
        config_path = PROJECT_ROOT / "config" / "copilot_config.json"
        service = build_copilot_service(
            "deterministic",
            KPI_ARTIFACT.stat().st_mtime_ns,
            SURVEY_ARTIFACT.stat().st_mtime_ns,
            MEMORY_ARTIFACT.stat().st_mtime_ns,
            config_path.stat().st_mtime_ns,
        )
        response = service.ask(
            "Give me my daily recap and coaching focus", "Agent_001", "end"
        )
        self.assertTrue(response.grounded)
        self.assertEqual(response.provider, "deterministic")
        self.assertIn("Evidence:", response.answer)
        self.assertIn("daily_recap", response.tool_calls)

    def test_streamlit_survey_view_reconciles_fixture_and_call_population(self):
        summary = filter_frame(self.survey_frames["agent_summary"], "end")
        self.assertEqual(summary["agent_id"].nunique(), 10)
        self.assertEqual(int(summary["calls_analyzed"].sum()), 100)
        self.assertEqual(int(summary["surveys_received"].sum()), 30)
        self.assertEqual(int(summary["real_survey_labels"].sum()), 0)

    def test_streamlit_supervisor_agent_uses_controlled_team_tools(self):
        config_path = PROJECT_ROOT / "config" / "copilot_config.json"
        service = build_supervisor_agent_service(
            "deterministic",
            SUPERVISOR_ARTIFACT.stat().st_mtime_ns,
            MEMORY_ARTIFACT.stat().st_mtime_ns,
            config_path.stat().st_mtime_ns,
        )
        response = service.ask("Summarize team health", "end")
        self.assertEqual(response.agent_id, "team")
        self.assertEqual(response.tool_calls, ["team_metrics"])
        self.assertIn("Evidence:", response.answer)


if __name__ == "__main__":
    unittest.main()
