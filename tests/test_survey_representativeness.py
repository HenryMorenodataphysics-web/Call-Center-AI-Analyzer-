import json
import unittest

import pandas as pd

from src.copilot.service import CopilotService
from src.outcomes.survey_representativeness import (
    DEFAULT_ARTIFACT,
    build_artifact,
)


STAGES = [{"id": "end", "label": "End view", "calls": 10}]


def hypothetical_calls() -> pd.DataFrame:
    rows = []
    for number in range(1, 11):
        high = number >= 9
        rows.append(
            {
                "call_id": f"call_{number}",
                "agent_id": "Agent_999",
                "agent_name": "Example Agent",
                "agent_call_number": number,
                "conversation_risk_score": 70 if high else 10,
                "conversation_risk_level": "high" if high else "low",
                "risk_score_type": "heuristic_proxy",
                "risk_score_calibrated": False,
            }
        )
    return pd.DataFrame(rows)


def hypothetical_surveys() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "call_id": call_id,
                "survey_received": 1,
                "survey_positive": 0,
                "survey_type": "CSAT",
                "survey_score": 20,
                "survey_completed_at": "2026-01-01T00:00:00Z",
                "is_synthetic": True,
                "source_system": "synthetic_test",
            }
            for call_id in ("call_9", "call_10")
        ]
    )


class SurveyRepresentativenessTests(unittest.TestCase):
    def test_user_scenario_flags_survey_subset_as_higher_risk_mix(self):
        artifact = build_artifact(
            hypothetical_calls(),
            hypothetical_surveys(),
            STAGES,
            generated_at="2026-01-01T00:00:00+00:00",
        )
        summary = artifact["snapshot"]["datasets"]["agent_summary"][0]
        self.assertEqual(summary["low_calls"], 8)
        self.assertEqual(summary["high_calls"], 2)
        self.assertEqual(summary["surveys_received"], 2)
        self.assertEqual(summary["elevated_share_gap"], 0.8)
        self.assertEqual(
            summary["representativeness_signal"],
            "Skewed toward higher review-priority calls",
        )
        self.assertIn("do not generalize", summary["interpretation"])

    def test_checked_in_artifact_preserves_synthetic_training_gate(self):
        artifact = json.loads(DEFAULT_ARTIFACT.read_text(encoding="utf-8"))
        end_rows = [
            row
            for row in artifact["snapshot"]["datasets"]["agent_summary"]
            if row["stage_id"] == "end"
        ]
        self.assertEqual(sum(row["calls_analyzed"] for row in end_rows), 100)
        self.assertEqual(sum(row["surveys_received"] for row in end_rows), 30)
        self.assertTrue(all(not row["training_eligible"] for row in end_rows))
        self.assertEqual(sum(row["real_survey_labels"] for row in end_rows), 0)

    def test_copilot_explains_survey_mix_without_agent_label(self):
        response = CopilotService().ask(
            "Are my surveys representative of all my calls?", "Agent_004", "end"
        )
        self.assertTrue(response.grounded)
        self.assertIn("survey_representativeness", response.tool_calls)
        self.assertIn("Survey sample representativeness", response.answer)
        self.assertIn("synthetic fixtures", response.answer)
        self.assertNotIn("bad agent", response.answer.casefold())


if __name__ == "__main__":
    unittest.main()
