"""Apply analytical contract v1 to existing final outputs without inference."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.contracts.analytical_contract import (  # noqa: E402
    build_call_contract_fields,
    enrich_turn_fusion,
    export_metric_catalog,
    write_analysis_manifest,
)


FINAL_OUTPUTS_DIR = PROJECT_ROOT / "data" / "final_outputs"


def apply_contract_to_existing_outputs() -> tuple[int, Path, Path]:
    summary_files = sorted(FINAL_OUTPUTS_DIR.glob("*_call_summary.csv"))

    if not summary_files:
        raise FileNotFoundError(
            f"No per-call summaries found in {FINAL_OUTPUTS_DIR}"
        )

    migrated_calls = 0

    for summary_path in summary_files:
        call_id = summary_path.name.removesuffix("_call_summary.csv")
        turn_path = FINAL_OUTPUTS_DIR / f"{call_id}_turn_fusion.csv"

        if not turn_path.exists():
            raise FileNotFoundError(
                f"Missing turn fusion file for {call_id}: {turn_path}"
            )

        turn_df = pd.read_csv(turn_path)
        summary_df = pd.read_csv(summary_path)

        if len(summary_df) != 1:
            raise ValueError(
                f"Expected one row in {summary_path.name}, found {len(summary_df)}"
            )

        enriched_turn_df = enrich_turn_fusion(turn_df)
        summary_row = summary_df.iloc[0].to_dict()
        summary_row.update(
            build_call_contract_fields(
                enriched_turn_df, summary_row["main_reasons"]
            )
        )

        enriched_turn_df.to_csv(turn_path, index=False, encoding="utf-8")
        pd.DataFrame([summary_row]).to_csv(
            summary_path, index=False, encoding="utf-8"
        )
        migrated_calls += 1

    manifest_path = write_analysis_manifest()
    metric_catalog_path = export_metric_catalog()
    return migrated_calls, manifest_path, metric_catalog_path


def main() -> None:
    migrated_calls, manifest_path, metric_catalog_path = (
        apply_contract_to_existing_outputs()
    )
    print(f"Contract v1 applied to {migrated_calls} calls.")
    print(f"Analysis manifest: {manifest_path}")
    print(f"KPI catalog: {metric_catalog_path}")


if __name__ == "__main__":
    main()
