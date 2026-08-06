import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.aggregation import create_dashboard_data as dashboard_data


FIXTURES_DIR = Path(__file__).parent / "fixtures"
SUMMARY_OUTPUTS_DIR = FIXTURES_DIR / "summary_outputs"
METADATA_PATH = FIXTURES_DIR / "calls_metadata.csv"


class DashboardDataTests(unittest.TestCase):
    def test_loader_ignores_overlapping_batch_summaries(self):
        with patch.object(
            dashboard_data, "FINAL_OUTPUTS_DIR", SUMMARY_OUTPUTS_DIR
        ):
            result = dashboard_data.load_call_summary_files()

        self.assertEqual(set(result["call_id"]), {"call_1", "call_2"})
        self.assertEqual(len(result), 2)

    def test_coverage_matches_metadata_and_agent_counts(self):
        metadata = pd.read_csv(METADATA_PATH)

        with patch.object(dashboard_data, "METADATA_PATH", METADATA_PATH):
            dashboard_data.validate_summary_coverage(metadata.copy())

    def test_coverage_rejects_duplicate_call_ids(self):
        metadata = pd.read_csv(METADATA_PATH)
        duplicate_summaries = pd.concat(
            [metadata.iloc[[0]], metadata.iloc[[0]]], ignore_index=True
        )

        with patch.object(dashboard_data, "METADATA_PATH", METADATA_PATH):
            with self.assertRaisesRegex(ValueError, "Duplicate call_id"):
                dashboard_data.validate_summary_coverage(duplicate_summaries)


if __name__ == "__main__":
    unittest.main()
