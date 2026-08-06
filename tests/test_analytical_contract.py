import json
import unittest

import pandas as pd

from src.contracts.analytical_contract import (
    ANALYTICAL_CONTRACT_VERSION,
    CALL_REASON_TEXT_TO_CODE,
    TURN_REASON_TEXT_TO_CODE,
    build_call_contract_fields,
    calculate_signal_coverage_confidence,
    enrich_turn_fusion,
    load_contract,
    reason_codes_from_text,
)


class AnalyticalContractTests(unittest.TestCase):
    def test_contract_file_matches_code_version(self):
        contract = load_contract()
        self.assertEqual(
            contract["contract_version"], ANALYTICAL_CONTRACT_VERSION
        )
        self.assertFalse(contract["risk_rubric"]["calibrated"])

    def test_reason_text_maps_to_stable_codes(self):
        turn_codes = reason_codes_from_text(
            "negative customer sentiment | high customer vocal intensity",
            TURN_REASON_TEXT_TO_CODE,
        )
        call_codes = reason_codes_from_text(
            "negative customer sentiment detected | no agent ownership detected",
            CALL_REASON_TEXT_TO_CODE,
        )

        self.assertEqual(
            turn_codes,
            ["CUST_NEGATIVE_SENTIMENT", "CUST_HIGH_VOCAL_INTENSITY"],
        )
        self.assertEqual(
            call_codes,
            ["CUST_NEGATIVE_SENTIMENT", "AGENT_NO_OWNERSHIP"],
        )

    def test_signal_coverage_is_not_a_predictive_probability(self):
        full_row = pd.Series(
            {
                "text": "I can help with that.",
                "normalized_sentiment": "positive",
                "sentiment_score": 0.95,
                "rms_db": -24.0,
                "speaking_rate_wps": 2.1,
                "pitch_mean_hz": 180.0,
            }
        )
        missing_pitch_row = full_row.copy()
        missing_pitch_row["pitch_mean_hz"] = None

        self.assertEqual(calculate_signal_coverage_confidence(full_row), 1.0)
        self.assertEqual(
            calculate_signal_coverage_confidence(missing_pitch_row), 0.833
        )

    def test_enrichment_adds_evidence_and_call_contract_fields(self):
        turns = pd.DataFrame(
            [
                {
                    "call_id": "call_1",
                    "turn_id": 1,
                    "speaker": "customer",
                    "text": "This is not working.",
                    "sentiment_score": 0.91,
                    "normalized_sentiment": "negative",
                    "vocal_intensity_level": "high",
                    "frustration_flag_bool": False,
                    "empathy_flag_bool": False,
                    "probing_flag_bool": False,
                    "ownership_flag_bool": False,
                    "next_steps_flag_bool": False,
                    "rms_db": -20.0,
                    "speaking_rate_wps": 2.0,
                    "pitch_mean_hz": 220.0,
                    "turn_main_signal": (
                        "negative customer sentiment | "
                        "high customer vocal intensity"
                    ),
                },
                {
                    "call_id": "call_1",
                    "turn_id": 2,
                    "speaker": "agent",
                    "text": "Let me check that for you.",
                    "sentiment_score": 0.80,
                    "normalized_sentiment": "neutral",
                    "vocal_intensity_level": "low",
                    "frustration_flag_bool": False,
                    "empathy_flag_bool": False,
                    "probing_flag_bool": False,
                    "ownership_flag_bool": True,
                    "next_steps_flag_bool": False,
                    "rms_db": -30.0,
                    "speaking_rate_wps": 1.5,
                    "pitch_mean_hz": 160.0,
                    "turn_main_signal": "agent ownership detected",
                },
            ]
        )

        enriched = enrich_turn_fusion(turns)
        fields = build_call_contract_fields(
            enriched,
            "negative customer sentiment detected | "
            "high customer vocal intensity detected | "
            "agent ownership detected",
        )
        evidence = json.loads(fields["evidence_json"])

        self.assertEqual(enriched.loc[0, "evidence_id"], "call_1:turn:1")
        self.assertEqual(evidence["CUST_NEGATIVE_SENTIMENT"], [1])
        self.assertEqual(evidence["AGENT_OWNERSHIP"], [2])
        self.assertFalse(fields["risk_score_calibrated"])
        self.assertFalse(fields["real_outcome_available"])


if __name__ == "__main__":
    unittest.main()
