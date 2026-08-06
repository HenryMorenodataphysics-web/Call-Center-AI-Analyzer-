import csv
import json
import unittest

from src.outcomes import survey_dataset
from src.outcomes import import_synthetic_surveys
from src.outcomes.train_survey_baseline import TrainingGateError, train_baseline


class SurveyOutcomeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.calls = survey_dataset.read_csv(survey_dataset.DEFAULT_CALLS)
        cls.config = survey_dataset.load_config()
        cls.temp_root = survey_dataset.PROJECT_ROOT / ".runtime" / "survey_outcome_tests"
        cls.temp_root.mkdir(parents=True, exist_ok=True)

    def governed_rows(self):
        rows = []
        for call in self.calls:
            positive = int(call["agent_call_number"]) % 2
            rows.append(
                {
                    "call_id": call["call_id"],
                    "survey_received": "1",
                    "survey_positive": str(positive),
                    "survey_type": "CSAT",
                    "survey_score": "5" if positive else "1",
                    "survey_completed_at": "2026-07-14T20:00:00Z",
                    "is_synthetic": "False",
                    "source_system": "unit_test_fixture_only",
                    "label_definition_version": "test_v1",
                }
            )
        return rows

    def test_blank_template_blocks_training_without_fabricating_labels(self):
        rows = survey_dataset.build_template_rows(self.calls, self.config["outcome_columns"])
        report, model_rows = survey_dataset.validate_outcomes(self.calls, rows, self.config)
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(model_rows, [])
        self.assertIn("NO_REAL_SURVEY_LABELS", {item["code"] for item in report["issues"]})

    def test_governed_labels_pass_readiness_gates(self):
        report, model_rows = survey_dataset.validate_outcomes(
            self.calls, self.governed_rows(), self.config
        )
        self.assertEqual(report["status"], "ready")
        self.assertEqual(len(model_rows), 100)
        self.assertEqual(report["profile"]["positive_labels"], 50)
        self.assertEqual(report["profile"]["negative_labels"], 50)

    def test_model_features_exclude_identity_risk_and_synthetic_kpis(self):
        features = survey_dataset.engineered_features(self.calls[0])
        self.assertEqual(set(features), set(self.config["feature_columns"]))
        forbidden = {"agent_id", "agent_name", "conversation_risk_score", "csat_demo"}
        self.assertFalse(forbidden & set(features))

    def test_duplicate_call_ids_are_blocking(self):
        rows = self.governed_rows()
        rows.append(dict(rows[0]))
        report, _ = survey_dataset.validate_outcomes(self.calls, rows, self.config)
        self.assertIn("DUPLICATE_CALL_IDS", {item["code"] for item in report["issues"]})

    def test_synthetic_labels_cannot_unlock_real_training(self):
        rows = self.governed_rows()
        for row in rows:
            row["is_synthetic"] = "True"
        report, model_rows = survey_dataset.validate_outcomes(self.calls, rows, self.config)
        codes = {item["code"] for item in report["issues"]}
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(model_rows, [])
        self.assertIn("SYNTHETIC_LABELS_NOT_ALLOWED", codes)
        self.assertEqual(report["profile"]["synthetic_completed_survey_rows"], 100)

    def test_supplied_synthetic_fixture_is_joinable_but_fixture_only(self):
        report, normalized = import_synthetic_surveys.profile_and_normalize()
        profile = report["profile"]
        self.assertEqual(report["status"], "fixture_only")
        self.assertEqual(profile["rows"], 30)
        self.assertEqual(profile["matched_calls"], 30)
        self.assertEqual(profile["synthetic_rows"], 30)
        self.assertEqual(profile["positive_synthetic_labels"], 22)
        self.assertEqual(profile["negative_synthetic_labels"], 8)
        self.assertEqual(len({row["call_id"] for row in normalized}), 30)
        self.assertTrue(all(row["is_synthetic"] is True for row in normalized))

    def test_supplied_synthetic_fixture_stays_out_of_modeling_dataset(self):
        _, normalized = import_synthetic_surveys.profile_and_normalize()
        report, model_rows = survey_dataset.validate_outcomes(
            self.calls, normalized, self.config
        )
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(model_rows, [])
        self.assertIn(
            "SYNTHETIC_LABELS_NOT_ALLOWED",
            {item["code"] for item in report["issues"]},
        )

    def test_training_refuses_blocked_readiness(self):
        readiness = self.temp_root / "blocked_readiness.json"
        readiness.write_text(
            json.dumps(
                {
                    "status": "blocked",
                    "issues": [
                        {
                            "severity": "blocking",
                            "code": "NO_REAL_SURVEY_LABELS",
                            "message": "No labels",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(TrainingGateError, "NO_REAL_SURVEY_LABELS"):
            train_baseline(readiness_path=readiness)

    def test_interpretable_baseline_runs_only_on_ready_fixture(self):
        report, model_rows = survey_dataset.validate_outcomes(
            self.calls, self.governed_rows(), self.config
        )
        self.assertEqual(report["status"], "ready")
        readiness_path = self.temp_root / "ready_readiness.json"
        dataset_path = self.temp_root / "dataset.csv"
        model_path = self.temp_root / "model.joblib"
        evaluation_path = self.temp_root / "evaluation.json"
        readiness_path.write_text(json.dumps(report), encoding="utf-8")
        columns = [
            "call_id",
            "agent_id",
            "survey_positive",
            "survey_type",
            "label_definition_version",
            *self.config["feature_columns"],
        ]
        with dataset_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(model_rows)
        evaluation = train_baseline(
            dataset_path=dataset_path,
            readiness_path=readiness_path,
            model_path=model_path,
            evaluation_path=evaluation_path,
        )
        self.assertEqual(evaluation["status"], "research_only")
        self.assertTrue(model_path.exists())
        self.assertTrue(evaluation_path.exists())
        self.assertEqual(evaluation["population"]["agents"], 10)


if __name__ == "__main__":
    unittest.main()
