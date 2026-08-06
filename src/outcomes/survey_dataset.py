#!/usr/bin/env python3
"""Validate real survey labels and build a leakage-controlled modeling dataset."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CALLS = PROJECT_ROOT / "data" / "final_outputs" / "all_calls_summary.csv"
DEFAULT_OUTCOMES = PROJECT_ROOT / "data" / "outcomes" / "survey_outcomes.csv"
DEFAULT_TEMPLATE = PROJECT_ROOT / "data" / "outcomes" / "survey_outcomes_template.csv"
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "survey_outcome_contract_v1.json"
DEFAULT_DATASET = PROJECT_ROOT / "data" / "modeling" / "survey_prediction_dataset.csv"
DEFAULT_REPORT = PROJECT_ROOT / "data" / "validation" / "survey_prediction_readiness.json"
DEFAULT_REPORT_MD = PROJECT_ROOT / "data" / "validation" / "survey_prediction_readiness.md"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def project_relative(path: Path) -> str:
    return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))


def build_template_rows(calls: list[dict[str, str]], columns: list[str]) -> list[dict[str, str]]:
    return [
        {column: call["call_id"] if column == "call_id" else "" for column in columns}
        for call in sorted(calls, key=lambda row: row["call_id"])
    ]


def initialize_template(
    calls_path: Path = DEFAULT_CALLS,
    template_path: Path = DEFAULT_TEMPLATE,
    config_path: Path = DEFAULT_CONFIG,
) -> Path:
    if template_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing outcome template: {template_path}")
    calls = read_csv(calls_path)
    config = load_config(config_path)
    write_csv(template_path, build_template_rows(calls, config["outcome_columns"]), config["outcome_columns"])
    return template_path


def add_synthetic_provenance_column(path: Path, config_path: Path = DEFAULT_CONFIG) -> None:
    config = load_config(config_path)
    rows = read_csv(path)
    if rows and "is_synthetic" in rows[0]:
        return
    upgraded = [{**row, "is_synthetic": ""} for row in rows]
    write_csv(path, upgraded, config["outcome_columns"])


def safe_rate(numerator: str, denominator: str) -> float:
    denominator_value = float(denominator or 0)
    if denominator_value <= 0:
        return 0.0
    return float(numerator or 0) / denominator_value


def engineered_features(call: dict[str, str]) -> dict[str, float]:
    duration_min = float(call["call_duration_min"])
    total_turns = float(call["total_turns"])
    customer_turns = call["customer_turns"]
    agent_turns = call["agent_turns"]
    return {
        "call_duration_min": round(duration_min, 6),
        "turns_per_minute": round(total_turns / duration_min if duration_min > 0 else 0.0, 6),
        "agent_talk_share": round(safe_rate(agent_turns, call["total_turns"]), 6),
        "negative_customer_rate": round(safe_rate(call["negative_customer_turns"], customer_turns), 6),
        "customer_frustration_rate": round(safe_rate(call["customer_frustration_turns"], customer_turns), 6),
        "high_intensity_customer_rate": round(safe_rate(call["high_intensity_customer_turns"], customer_turns), 6),
        "agent_empathy_rate": round(safe_rate(call["agent_empathy_turns"], agent_turns), 6),
        "agent_probing_rate": round(safe_rate(call["agent_probing_turns"], agent_turns), 6),
        "agent_ownership_rate": round(safe_rate(call["agent_ownership_turns"], agent_turns), 6),
        "agent_next_steps_rate": round(safe_rate(call["agent_next_steps_turns"], agent_turns), 6),
        "signal_coverage_confidence": round(float(call["signal_coverage_confidence"]), 6),
    }


def issue(severity: str, code: str, message: str, evidence: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"severity": severity, "code": code, "message": message}
    if evidence is not None:
        payload["evidence"] = evidence
    return payload


def validate_outcomes(
    calls: list[dict[str, str]],
    outcomes: list[dict[str, Any]],
    config: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    call_map = {row["call_id"]: row for row in calls}
    required = config["outcome_columns"]
    present = set(outcomes[0]) if outcomes else set(required)
    missing_columns = [column for column in required if column not in present]
    if missing_columns:
        issues.append(issue("blocking", "MISSING_COLUMNS", "Outcome extract is missing required columns.", missing_columns))
        return {"status": "blocked", "issues": issues}, []

    def cell(row: dict[str, Any], field: str) -> str:
        value = row[field]
        return "" if value is None else str(value).strip()

    call_ids = [cell(row, "call_id") for row in outcomes if cell(row, "call_id")]
    duplicates = sorted(call_id for call_id, count in Counter(call_ids).items() if count > 1)
    if duplicates:
        issues.append(issue("blocking", "DUPLICATE_CALL_IDS", "Outcome extract must contain at most one row per call.", duplicates))
    unknown = sorted(set(call_ids) - set(call_map))
    if unknown:
        issues.append(issue("blocking", "UNKNOWN_CALL_IDS", "Outcome extract contains calls outside the analyzed population.", unknown))

    labeled: list[dict[str, Any]] = []
    synthetic_completed_call_ids: list[str] = []
    responded_without_survey = 0
    for row_number, row in enumerate(outcomes, start=2):
        call_id = cell(row, "call_id")
        received = cell(row, "survey_received")
        positive = cell(row, "survey_positive")
        if not call_id or not received:
            continue
        if received not in {"0", "1"}:
            issues.append(issue("blocking", "INVALID_SURVEY_RECEIVED", f"Row {row_number} survey_received must be 0 or 1.", call_id))
            continue
        if received == "0":
            if positive:
                responded_without_survey += 1
            continue
        required_label_fields = (
            "survey_positive",
            "survey_type",
            "survey_completed_at",
            "is_synthetic",
            "source_system",
            "label_definition_version",
        )
        missing = [field for field in required_label_fields if not cell(row, field)]
        if missing:
            issues.append(issue("blocking", "INCOMPLETE_LABEL", f"Row {row_number} is missing governed label fields.", {"call_id": call_id, "fields": missing}))
            continue
        if positive not in {"0", "1"}:
            issues.append(issue("blocking", "INVALID_SURVEY_POSITIVE", f"Row {row_number} survey_positive must be 0 or 1.", call_id))
            continue
        survey_type = cell(row, "survey_type").upper()
        if survey_type not in config["allowed_survey_types"]:
            issues.append(issue("blocking", "INVALID_SURVEY_TYPE", f"Row {row_number} has an unsupported survey_type.", survey_type))
            continue
        synthetic_value = cell(row, "is_synthetic").casefold()
        if synthetic_value not in {"0", "1", "false", "true", "no", "yes"}:
            issues.append(issue("blocking", "INVALID_SYNTHETIC_FLAG", f"Row {row_number} is_synthetic must be an explicit boolean.", call_id))
            continue
        if synthetic_value in {"1", "true", "yes"}:
            synthetic_completed_call_ids.append(call_id)
            continue
        if call_id in call_map:
            labeled.append(
                {
                    "call_id": call_id,
                    "survey_positive": int(positive),
                    "survey_type": survey_type,
                    "survey_score": cell(row, "survey_score"),
                    "survey_completed_at": cell(row, "survey_completed_at"),
                    "source_system": cell(row, "source_system"),
                    "label_definition_version": cell(row, "label_definition_version"),
                }
            )
    if responded_without_survey:
        issues.append(issue("blocking", "LABEL_WITHOUT_SURVEY", "survey_positive must be blank when survey_received is 0.", responded_without_survey))
    if synthetic_completed_call_ids:
        issues.append(
            issue(
                "blocking",
                "SYNTHETIC_LABELS_NOT_ALLOWED",
                "Synthetic survey rows may test plumbing but cannot train or validate the real-outcome model.",
                {"rows": len(synthetic_completed_call_ids)},
            )
        )

    class_counts = Counter(row["survey_positive"] for row in labeled)
    agents = {call_map[row["call_id"]]["agent_id"] for row in labeled}
    survey_types = {row["survey_type"] for row in labeled}
    label_versions = {row["label_definition_version"] for row in labeled}
    gates = config["training_gates"]
    if not labeled:
        issues.append(issue("blocking", "NO_REAL_SURVEY_LABELS", "No completed real survey labels are available; training and probability display remain disabled."))
    if labeled and len(labeled) < gates["minimum_labeled_calls"]:
        issues.append(issue("blocking", "INSUFFICIENT_LABELED_CALLS", "Too few completed surveys for the baseline gate.", {"actual": len(labeled), "required": gates["minimum_labeled_calls"]}))
    if labeled and class_counts[1] < gates["minimum_positive_calls"]:
        issues.append(issue("blocking", "INSUFFICIENT_POSITIVE_LABELS", "Positive class count is below the baseline gate.", {"actual": class_counts[1], "required": gates["minimum_positive_calls"]}))
    if labeled and class_counts[0] < gates["minimum_negative_calls"]:
        issues.append(issue("blocking", "INSUFFICIENT_NEGATIVE_LABELS", "Negative class count is below the baseline gate.", {"actual": class_counts[0], "required": gates["minimum_negative_calls"]}))
    if labeled and len(agents) < gates["minimum_agents"]:
        issues.append(issue("blocking", "INSUFFICIENT_AGENT_COVERAGE", "Labels do not cover enough agents for group-aware evaluation.", {"actual": len(agents), "required": gates["minimum_agents"]}))
    if len(survey_types) > gates["maximum_survey_types_per_model"]:
        issues.append(issue("blocking", "MULTIPLE_SURVEY_TYPES", "Train separate models for survey instruments with different semantics.", sorted(survey_types)))
    if gates["require_single_label_definition_version"] and len(label_versions) > 1:
        issues.append(issue("blocking", "MULTIPLE_LABEL_DEFINITIONS", "A model run must use one governed label-definition version.", sorted(label_versions)))

    model_rows: list[dict[str, Any]] = []
    for label in labeled:
        call = call_map[label["call_id"]]
        model_rows.append(
            {
                "call_id": label["call_id"],
                "agent_id": call["agent_id"],
                "survey_positive": label["survey_positive"],
                "survey_type": label["survey_type"],
                "label_definition_version": label["label_definition_version"],
                **engineered_features(call),
            }
        )

    status = "ready" if not any(item["severity"] == "blocking" for item in issues) else "blocked"
    report = {
        "status": status,
        "contract_version": config["version"],
        "target": config["target"],
        "profile": {
            "analyzed_calls": len(calls),
            "outcome_rows": len(outcomes),
            "completed_survey_labels": len(labeled),
            "synthetic_completed_survey_rows": len(synthetic_completed_call_ids),
            "positive_labels": class_counts[1],
            "negative_labels": class_counts[0],
            "agents_with_labels": len(agents),
            "survey_types": sorted(survey_types),
            "label_definition_versions": sorted(label_versions),
        },
        "training_gates": gates,
        "feature_columns": config["feature_columns"],
        "excluded_feature_families": config["excluded_feature_families"],
        "issues": issues,
    }
    return report, model_rows


def markdown_report(report: dict[str, Any]) -> str:
    profile = report["profile"]
    lines = [
        "# Survey prediction readiness",
        "",
        f"- Status: **{report['status']}**",
        f"- Contract version: `{report['contract_version']}`",
        f"- Analyzed calls: {profile['analyzed_calls']}",
        f"- Completed real survey labels: {profile['completed_survey_labels']}",
        f"- Positive / negative: {profile['positive_labels']} / {profile['negative_labels']}",
        f"- Agents with labels: {profile['agents_with_labels']}",
        "",
        "## Target boundary",
        "",
        report["target"]["interpretation"],
        "",
        "## Issues",
        "",
    ]
    if report["issues"]:
        lines.extend(f"- `{item['severity']}` `{item['code']}`: {item['message']}" for item in report["issues"])
    else:
        lines.append("- No blocking readiness issues.")
    return "\n".join(lines) + "\n"


def run_readiness(
    calls_path: Path = DEFAULT_CALLS,
    outcomes_path: Path = DEFAULT_OUTCOMES,
    config_path: Path = DEFAULT_CONFIG,
    dataset_path: Path = DEFAULT_DATASET,
    report_path: Path = DEFAULT_REPORT,
    report_md_path: Path = DEFAULT_REPORT_MD,
) -> dict[str, Any]:
    calls = read_csv(calls_path)
    config = load_config(config_path)
    outcomes = read_csv(outcomes_path)
    report, model_rows = validate_outcomes(calls, outcomes, config)
    report["generated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    report["source_paths"] = {
        "calls": project_relative(calls_path),
        "outcomes": project_relative(outcomes_path),
        "modeling_dataset": project_relative(dataset_path),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report_md_path.write_text(markdown_report(report), encoding="utf-8")
    if report["status"] == "ready":
        columns = [
            "call_id",
            "agent_id",
            "survey_positive",
            "survey_type",
            "label_definition_version",
            *config["feature_columns"],
        ]
        write_csv(dataset_path, model_rows, columns)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calls", type=Path, default=DEFAULT_CALLS)
    parser.add_argument("--outcomes", type=Path, default=DEFAULT_OUTCOMES)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--report-md", type=Path, default=DEFAULT_REPORT_MD)
    parser.add_argument("--init-template", action="store_true")
    parser.add_argument("--init-outcomes", action="store_true")
    parser.add_argument("--upgrade-synthetic-flag", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.init_template:
        path = initialize_template(args.calls, DEFAULT_TEMPLATE, args.config)
        print(f"Created blank governed outcome template: {path}")
        return
    if args.init_outcomes:
        path = initialize_template(args.calls, args.outcomes, args.config)
        print(f"Created blank governed outcome input: {path}")
        return
    if args.upgrade_synthetic_flag:
        add_synthetic_provenance_column(args.outcomes, args.config)
        print(f"Added explicit synthetic provenance column: {args.outcomes}")
        return
    report = run_readiness(
        args.calls,
        args.outcomes,
        args.config,
        args.dataset,
        args.report,
        args.report_md,
    )
    print(json.dumps({"status": report["status"], "profile": report["profile"], "issues": report["issues"]}, indent=2))


if __name__ == "__main__":
    main()
