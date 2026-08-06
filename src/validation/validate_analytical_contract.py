"""Validate all pipeline stages against analytical contract v1."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.contracts.analytical_contract import (  # noqa: E402
    ANALYTICAL_CONTRACT_VERSION,
    load_contract,
)


VALIDATION_DIR = PROJECT_ROOT / "data" / "validation"
JSON_REPORT_PATH = VALIDATION_DIR / "analytical_contract_validation.json"
MARKDOWN_REPORT_PATH = VALIDATION_DIR / "analytical_contract_validation.md"


def add_issue(
    issues: list[dict[str, Any]],
    severity: str,
    check: str,
    message: str,
    evidence: dict[str, Any] | None = None,
) -> None:
    issues.append(
        {
            "severity": severity,
            "check": check,
            "message": message,
            "evidence": evidence or {},
        }
    )


def read_entity_files(entity: dict[str, Any]) -> list[tuple[Path, pd.DataFrame]]:
    file_pattern = entity["file_pattern"]
    paths = sorted(PROJECT_ROOT.glob(file_pattern))
    return [(path, pd.read_csv(path)) for path in paths]


def validate_schema_and_keys(
    entity_name: str,
    entity: dict[str, Any],
    files: list[tuple[Path, pd.DataFrame]],
    issues: list[dict[str, Any]],
) -> None:
    if not files:
        add_issue(
            issues,
            "critical",
            f"{entity_name}.files",
            f"No files matched {entity['file_pattern']}",
        )
        return

    required_columns = set(entity["required_columns"])
    primary_key = entity["primary_key"]

    for path, dataframe in files:
        missing_columns = sorted(required_columns - set(dataframe.columns))
        if missing_columns:
            add_issue(
                issues,
                "critical",
                f"{entity_name}.required_columns",
                f"{path.name} is missing required columns.",
                {"missing_columns": missing_columns},
            )
            continue

        null_key_rows = int(dataframe[primary_key].isna().any(axis=1).sum())
        duplicate_key_rows = int(
            dataframe.duplicated(subset=primary_key, keep=False).sum()
        )

        if null_key_rows:
            add_issue(
                issues,
                "critical",
                f"{entity_name}.primary_key_not_null",
                f"{path.name} contains null primary keys.",
                {"affected_rows": null_key_rows},
            )

        if duplicate_key_rows:
            add_issue(
                issues,
                "critical",
                f"{entity_name}.primary_key_unique",
                f"{path.name} contains duplicate primary keys.",
                {"affected_rows": duplicate_key_rows},
            )


def validate_call_coverage(
    entity_name: str,
    files: list[tuple[Path, pd.DataFrame]],
    expected_call_ids: set[str],
    issues: list[dict[str, Any]],
) -> None:
    actual_call_ids: set[str] = set()
    for _, dataframe in files:
        if "call_id" in dataframe.columns:
            actual_call_ids.update(dataframe["call_id"].dropna().astype(str))

    missing = sorted(expected_call_ids - actual_call_ids)
    unexpected = sorted(actual_call_ids - expected_call_ids)

    if missing or unexpected:
        add_issue(
            issues,
            "critical",
            f"{entity_name}.call_coverage",
            "Call coverage does not match metadata.",
            {"missing": missing, "unexpected": unexpected},
        )


def validate_domain_rules(
    entity_frames: dict[str, list[tuple[Path, pd.DataFrame]]],
    metadata_df: pd.DataFrame,
    issues: list[dict[str, Any]],
) -> None:
    allowed_speakers = {"agent", "customer"}
    allowed_sentiments = {"negative", "neutral", "positive", "unknown"}
    allowed_levels = {"low", "medium", "high", "unknown"}

    for entity_name in ("speaker_turn", "text_analysis", "acoustic_analysis", "call_turn"):
        for path, dataframe in entity_frames[entity_name]:
            if "speaker" in dataframe.columns:
                invalid = sorted(
                    set(dataframe["speaker"].dropna().astype(str).str.lower())
                    - allowed_speakers
                )
                if invalid:
                    add_issue(
                        issues,
                        "high",
                        f"{entity_name}.speaker_values",
                        f"{path.name} contains invalid speaker values.",
                        {"invalid_values": invalid},
                    )

    for path, dataframe in entity_frames["call_turn"]:
        invalid_sentiments = sorted(
            set(
                dataframe["normalized_sentiment"]
                .dropna()
                .astype(str)
                .str.lower()
            )
            - allowed_sentiments
        )
        invalid_intensity = sorted(
            set(
                dataframe["vocal_intensity_level"]
                .dropna()
                .astype(str)
                .str.lower()
            )
            - allowed_levels
        )
        out_of_range_scores = int(
            (~dataframe["turn_risk_score"].between(0, 100)).sum()
        )
        out_of_range_confidence = int(
            (~dataframe["signal_coverage_confidence"].between(0, 1)).sum()
        )

        if invalid_sentiments:
            add_issue(
                issues,
                "high",
                "call_turn.sentiment_values",
                f"{path.name} has invalid normalized sentiment values.",
                {"invalid_values": invalid_sentiments},
            )
        if invalid_intensity:
            add_issue(
                issues,
                "high",
                "call_turn.vocal_intensity_values",
                f"{path.name} has invalid vocal intensity levels.",
                {"invalid_values": invalid_intensity},
            )
        if out_of_range_scores:
            add_issue(
                issues,
                "critical",
                "call_turn.risk_score_range",
                f"{path.name} has out-of-range risk scores.",
                {"affected_rows": out_of_range_scores},
            )
        if out_of_range_confidence:
            add_issue(
                issues,
                "high",
                "call_turn.signal_coverage_range",
                f"{path.name} has out-of-range signal coverage confidence.",
                {"affected_rows": out_of_range_confidence},
            )

    summary_frames = [frame for _, frame in entity_frames["call_summary"]]
    call_summary_df = pd.concat(summary_frames, ignore_index=True)

    inconsistent_turn_totals = int(
        (
            call_summary_df["total_turns"]
            != call_summary_df["customer_turns"] + call_summary_df["agent_turns"]
        ).sum()
    )
    invalid_contract_versions = int(
        (
            call_summary_df["analytical_contract_version"].astype(str)
            != ANALYTICAL_CONTRACT_VERSION
        ).sum()
    )
    calibrated_rows = int(
        call_summary_df["risk_score_calibrated"]
        .astype(str)
        .str.lower()
        .isin({"true", "1", "yes"})
        .sum()
    )
    outcome_rows = int(
        call_summary_df["real_outcome_available"]
        .astype(str)
        .str.lower()
        .isin({"true", "1", "yes"})
        .sum()
    )

    if inconsistent_turn_totals:
        add_issue(
            issues,
            "critical",
            "call_summary.turn_totals",
            "Call turn totals are inconsistent.",
            {"affected_rows": inconsistent_turn_totals},
        )
    if invalid_contract_versions:
        add_issue(
            issues,
            "critical",
            "call_summary.contract_version",
            "Call summaries contain an unexpected contract version.",
            {"affected_rows": invalid_contract_versions},
        )
    if calibrated_rows:
        add_issue(
            issues,
            "critical",
            "call_summary.calibration_claim",
            "Uncalibrated heuristic rows are marked as calibrated.",
            {"affected_rows": calibrated_rows},
        )
    if outcome_rows:
        add_issue(
            issues,
            "critical",
            "call_summary.outcome_claim",
            "Rows claim real outcomes that are unavailable in this dataset.",
            {"affected_rows": outcome_rows},
        )

    for _, row in call_summary_df.iterrows():
        try:
            evidence = json.loads(row["evidence_json"])
        except (TypeError, json.JSONDecodeError):
            add_issue(
                issues,
                "high",
                "call_summary.evidence_json",
                f"Invalid evidence JSON for {row['call_id']}.",
            )
            continue

        reason_codes = {
            value for value in str(row["reason_codes"]).split("|") if value
        }
        if set(evidence) != reason_codes:
            add_issue(
                issues,
                "high",
                "call_summary.evidence_reason_alignment",
                f"Evidence keys do not match reason codes for {row['call_id']}.",
            )

    expected_agent_counts = metadata_df.groupby("agent_id")["call_id"].nunique()
    agent_df = entity_frames["agent_summary"][0][1].set_index("agent_id")
    actual_agent_counts = agent_df["total_calls"].astype(int)

    if expected_agent_counts.to_dict() != actual_agent_counts.to_dict():
        add_issue(
            issues,
            "critical",
            "agent_summary.call_counts",
            "Agent summary counts do not reconcile with metadata.",
            {
                "expected": expected_agent_counts.to_dict(),
                "actual": actual_agent_counts.to_dict(),
            },
        )

    high_risk_calls = int(
        (call_summary_df["conversation_risk_level"] == "high").sum()
    )
    add_issue(
        issues,
        "warning",
        "risk_rubric.calibration_status",
        "The heuristic risk rubric has no ground-truth calibration.",
        {
            "high_risk_calls": high_risk_calls,
            "maximum_score": int(call_summary_df["conversation_risk_score"].max()),
            "required_action": "Calibrate only after real labeled outcomes exist.",
        },
    )


def write_reports(report: dict[str, Any]) -> None:
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)

    with JSON_REPORT_PATH.open("w", encoding="utf-8") as json_file:
        json.dump(report, json_file, indent=2)
        json_file.write("\n")

    lines = [
        "# Analytical Contract Validation",
        "",
        f"- Status: **{report['status']}**",
        f"- Contract version: `{report['contract_version']}`",
        f"- Validated at: `{report['validated_at_utc']}`",
        f"- Calls: {report['profile']['calls']}",
        f"- Agents: {report['profile']['agents']}",
        f"- Turn rows: {report['profile']['turn_rows']}",
        "",
        "## Findings",
        "",
    ]

    if not report["issues"]:
        lines.append("No issues found.")
    else:
        for issue in report["issues"]:
            lines.append(
                f"- **{issue['severity'].upper()} — {issue['check']}**: "
                f"{issue['message']}"
            )
            if issue["evidence"]:
                lines.append(
                    f"  Evidence: `{json.dumps(issue['evidence'], sort_keys=True)}`"
                )

    MARKDOWN_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_contract() -> dict[str, Any]:
    contract = load_contract()
    issues: list[dict[str, Any]] = []
    entity_frames = {
        entity_name: read_entity_files(entity)
        for entity_name, entity in contract["entities"].items()
    }

    for entity_name, entity in contract["entities"].items():
        validate_schema_and_keys(
            entity_name, entity, entity_frames[entity_name], issues
        )

    metadata_df = entity_frames["metadata"][0][1]
    expected_call_ids = set(metadata_df["call_id"].astype(str))

    for entity_name in (
        "transcript",
        "speaker_turn",
        "text_analysis",
        "acoustic_analysis",
        "call_turn",
        "call_summary",
    ):
        validate_call_coverage(
            entity_name,
            entity_frames[entity_name],
            expected_call_ids,
            issues,
        )

    critical_schema_issues = [
        issue
        for issue in issues
        if issue["severity"] == "critical"
        and "required_columns" in issue["check"]
    ]
    if not critical_schema_issues:
        validate_domain_rules(entity_frames, metadata_df, issues)

    blocking_issues = [
        issue for issue in issues if issue["severity"] in {"critical", "high"}
    ]
    call_turn_df = pd.concat(
        [frame for _, frame in entity_frames["call_turn"]], ignore_index=True
    )

    report = {
        "status": "pass" if not blocking_issues else "fail",
        "contract_version": contract["contract_version"],
        "validated_at_utc": datetime.now(timezone.utc).isoformat(),
        "profile": {
            "calls": len(expected_call_ids),
            "agents": int(metadata_df["agent_id"].nunique()),
            "turn_rows": len(call_turn_df),
        },
        "blocking_issue_count": len(blocking_issues),
        "warning_count": sum(
            issue["severity"] == "warning" for issue in issues
        ),
        "issues": issues,
    }
    write_reports(report)
    return report


def main() -> None:
    report = validate_contract()
    print(json.dumps(report, indent=2))
    print(f"JSON report: {JSON_REPORT_PATH}")
    print(f"Markdown report: {MARKDOWN_REPORT_PATH}")

    if report["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
