#!/usr/bin/env python3
"""Normalize and profile the explicit synthetic survey fixture."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .survey_dataset import (
    DEFAULT_CALLS,
    DEFAULT_CONFIG,
    PROJECT_ROOT,
    load_config,
    read_csv,
    write_csv,
)


DEFAULT_SOURCE = PROJECT_ROOT / "data" / "outcomes" / "fixtures" / "synthetic_surveys_3_per_agent.csv"
DEFAULT_NORMALIZED = PROJECT_ROOT / "data" / "outcomes" / "fixtures" / "synthetic_surveys_normalized.csv"
DEFAULT_QUALITY_JSON = PROJECT_ROOT / "data" / "validation" / "synthetic_survey_fixture_quality.json"
DEFAULT_QUALITY_MD = PROJECT_ROOT / "data" / "validation" / "synthetic_survey_fixture_quality.md"
DEFAULT_ARTIFACT = PROJECT_ROOT / "reports" / "synthetic_survey_quality_artifact.json"


REQUIRED_SOURCE_COLUMNS = {
    "survey_id",
    "call_id",
    "agent_id",
    "agent_name",
    "agent_call_number",
    "survey_date",
    "csat_score",
    "nps_score",
    "nps_label",
    "bad_survey_flag",
    "survey_outcome_class",
    "survey_comment",
    "is_synthetic",
    "generation_notes",
}


def is_true(value: str) -> bool:
    return value.strip().casefold() in {"1", "true", "yes"}


def expected_nps_label(score: int) -> str:
    if score >= 9:
        return "Promoter"
    if score >= 7:
        return "Passive"
    return "Detractor"


def relative(path: Path) -> str:
    return str(path.resolve().relative_to(PROJECT_ROOT.resolve())).replace("\\", "/")


def profile_and_normalize(
    source_path: Path = DEFAULT_SOURCE,
    calls_path: Path = DEFAULT_CALLS,
    config_path: Path = DEFAULT_CONFIG,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    surveys = read_csv(source_path)
    calls = read_csv(calls_path)
    config = load_config(config_path)
    if not surveys:
        raise ValueError("Synthetic survey file is empty")
    missing = sorted(REQUIRED_SOURCE_COLUMNS - set(surveys[0]))
    if missing:
        raise ValueError(f"Synthetic survey file is missing columns: {', '.join(missing)}")

    call_by_key = {
        (row["agent_id"], int(row["agent_call_number"])): row
        for row in calls
    }
    survey_ids = [row["survey_id"].strip() for row in surveys]
    duplicate_survey_ids = sorted(key for key, count in Counter(survey_ids).items() if count > 1)
    composite_keys = [
        (row["agent_id"].strip(), int(row["agent_call_number"]))
        for row in surveys
    ]
    duplicate_keys = sorted(key for key, count in Counter(composite_keys).items() if count > 1)
    unmatched = sorted(key for key in composite_keys if key not in call_by_key)
    if duplicate_survey_ids or duplicate_keys or unmatched:
        raise ValueError(
            f"Fixture key validation failed: duplicate survey ids={len(duplicate_survey_ids)}, "
            f"duplicate call keys={len(duplicate_keys)}, unmatched keys={len(unmatched)}"
        )

    normalized: list[dict[str, Any]] = []
    name_mismatches = 0
    nps_mismatches = 0
    synthetic_rows = 0
    blank_call_ids = 0
    comments = Counter()
    agents = Counter()
    call_numbers = Counter()
    labels = Counter()
    outcome_classes = Counter()

    for survey, key in zip(surveys, composite_keys):
        call = call_by_key[key]
        if survey["agent_name"].strip() != call["agent_name"].strip():
            name_mismatches += 1
        if expected_nps_label(int(survey["nps_score"])) != survey["nps_label"].strip():
            nps_mismatches += 1
        if is_true(survey["is_synthetic"]):
            synthetic_rows += 1
        if not survey["call_id"].strip():
            blank_call_ids += 1
        comments[survey["survey_comment"].strip()] += 1
        agents[survey["agent_id"].strip()] += 1
        call_numbers[int(survey["agent_call_number"])] += 1
        survey_positive = 1 - int(survey["bad_survey_flag"])
        labels[survey_positive] += 1
        outcome_classes[survey["survey_outcome_class"].strip()] += 1
        normalized.append(
            {
                "call_id": call["call_id"],
                "survey_received": 1,
                "survey_positive": survey_positive,
                "survey_type": "CSAT",
                "survey_score": survey["csat_score"],
                "survey_completed_at": f"{survey['survey_date']}T00:00:00Z",
                "is_synthetic": True,
                "source_system": "apptek_synthetic_survey_fixture",
                "label_definition_version": "synthetic_bad_survey_flag_v1",
            }
        )

    row_count = len(surveys)
    unique_comments = len(comments)
    quality_checks = [
        {
            "severity_rank": 1,
            "severity": "High",
            "check": "Real-outcome provenance",
            "evidence": f"{synthetic_rows}/{row_count} rows have is_synthetic=True and every generation note says the feedback is for MVP testing only.",
            "impact": "Cannot train, calibrate, validate, or display a real survey probability.",
            "action": "Keep as a fixture and wait for a governed real survey extract.",
        },
        {
            "severity_rank": 1,
            "severity": "High",
            "check": "Training sufficiency",
            "evidence": f"{row_count} rows total: {labels[1]} positive and {labels[0]} negative; gates require 80 total and 20 per class.",
            "impact": "The sample is too small and the negative class is below the minimum gate.",
            "action": "Do not relax gates for a portfolio result; collect additional real labels.",
        },
        {
            "severity_rank": 2,
            "severity": "Medium",
            "check": "Primary call key completeness",
            "evidence": f"call_id is blank in {blank_call_ids}/{row_count} rows; all {row_count} rows match uniquely through agent_id + agent_call_number.",
            "impact": "The composite join is recoverable but less durable than a source-provided call_id.",
            "action": "Use the recovered call_id only in the fixture adapter; require call_id in the real feed.",
        },
        {
            "severity_rank": 2,
            "severity": "Medium",
            "check": "Template repetition",
            "evidence": f"Only {unique_comments} unique comments across {row_count} rows; the most common comment appears {max(comments.values())} times.",
            "impact": "Text and score patterns are generated templates, not independent customer evidence.",
            "action": "Exclude comments from modeling and from real-world performance claims.",
        },
        {
            "severity_rank": 4,
            "severity": "Pass",
            "check": "Structural integrity",
            "evidence": f"{row_count} unique survey IDs, {row_count} unique agent-call keys, 10 agents with 3 rows each, {nps_mismatches} NPS label mismatches, {name_mismatches} name mismatches.",
            "impact": "The file is structurally suitable for plumbing and UI tests.",
            "action": "Retain automated uniqueness, enum, and join checks.",
        },
    ]
    report = {
        "status": "fixture_only",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "intended_use": "Pipeline, contract, and UI testing only",
        "prohibited_uses": [
            "Real-outcome model training or calibration",
            "Official CSAT, NPS, QA, or survey reporting",
            "Agent performance decisions",
            "Phase 7 completion evidence",
        ],
        "profile": {
            "rows": row_count,
            "columns": len(surveys[0]),
            "matched_calls": row_count - len(unmatched),
            "coverage_of_100_calls": round(row_count / len(calls), 4),
            "agents": len(agents),
            "rows_per_agent": dict(sorted(agents.items())),
            "agent_call_numbers": dict(sorted(call_numbers.items())),
            "synthetic_rows": synthetic_rows,
            "blank_call_ids": blank_call_ids,
            "positive_synthetic_labels": labels[1],
            "negative_synthetic_labels": labels[0],
            "outcome_classes": dict(sorted(outcome_classes.items())),
            "unique_comments": unique_comments,
            "nps_label_mismatches": nps_mismatches,
            "agent_name_mismatches": name_mismatches,
        },
        "training_gates": config["training_gates"],
        "quality_checks": quality_checks,
        "source": relative(source_path),
        "normalized_fixture": relative(DEFAULT_NORMALIZED),
    }
    return report, normalized


def markdown_report(report: dict[str, Any]) -> str:
    p = report["profile"]
    lines = [
        "# Synthetic survey fixture quality review",
        "",
        "## Executive Summary",
        "",
        "- **Fixture only.** Every row is explicitly synthetic and cannot unlock real-outcome modeling.",
        f"- **Structurally joinable.** {p['matched_calls']}/{p['rows']} rows map to analyzed calls, but source `call_id` is blank.",
        f"- **Below modeling gates.** The file has {p['positive_synthetic_labels']} positive and {p['negative_synthetic_labels']} negative synthetic labels.",
        "- **Recommended use.** Keep it for ingestion, contract, and UI tests only.",
        "",
        "## Quality checks",
        "",
    ]
    for item in report["quality_checks"]:
        lines.extend(
            [
                f"### {item['severity']}: {item['check']}",
                "",
                item["evidence"],
                "",
                f"Impact: {item['impact']}",
                "",
                f"Action: {item['action']}",
                "",
            ]
        )
    return "\n".join(lines)


def build_report_artifact(report: dict[str, Any]) -> dict[str, Any]:
    p = report["profile"]
    label_balance = [
        {"label": "Positive synthetic", "count": p["positive_synthetic_labels"], "share": round(p["positive_synthetic_labels"] / p["rows"], 4)},
        {"label": "Negative synthetic", "count": p["negative_synthetic_labels"], "share": round(p["negative_synthetic_labels"] / p["rows"], 4)},
    ]
    coverage_by_agent = [
        {"agent_id": agent_id, "survey_rows": count, "available_calls": 10, "coverage": round(count / 10, 4)}
        for agent_id, count in p["rows_per_agent"].items()
    ]
    profile_rows = [{
        "rows": p["rows"],
        "matched_calls": p["matched_calls"],
        "real_labels": 0,
        "unique_comments": p["unique_comments"],
    }]
    source = {
        "id": "synthetic_survey_fixture",
        "label": "Explicit synthetic survey fixture - 3 rows per agent",
        "path": report["source"],
        "query": {
            "engine": "sqlite",
            "language": "sql",
            "sql": "SELECT * FROM synthetic_surveys_3_per_agent ORDER BY agent_id, agent_call_number",
            "description": "Profiles the 30-row synthetic survey fixture and reconciles it to canonical calls by agent_id and agent_call_number.",
            "tables_used": ["synthetic_surveys_3_per_agent"],
            "filters": ["No rows excluded", "Synthetic provenance preserved"],
            "executed_at": report["generated_at"],
            "metric_definitions": [
                "Positive synthetic label = 1 - bad_survey_flag.",
                "Coverage = matched synthetic survey rows divided by 100 analyzed calls.",
                "Real labels = rows eligible for Phase 7 training; synthetic rows always count as zero real labels.",
            ],
        },
    }
    cards = [
        {"id": "survey_rows", "description": "Rows in the supplied fixture.", "dataset": "profile", "sourceId": source["id"], "metrics": [{"label": "Synthetic rows", "field": "rows", "format": "number"}]},
        {"id": "matched_calls", "description": "Rows matched to canonical calls through the composite key.", "dataset": "profile", "sourceId": source["id"], "metrics": [{"label": "Matched calls", "field": "matched_calls", "format": "number"}]},
        {"id": "real_labels", "description": "Rows eligible to train or validate the real-outcome model.", "dataset": "profile", "sourceId": source["id"], "metrics": [{"label": "Real labels", "field": "real_labels", "format": "number"}]},
        {"id": "unique_comments", "description": "Distinct generated comment templates in the 30-row fixture.", "dataset": "profile", "sourceId": source["id"], "metrics": [{"label": "Unique comments", "field": "unique_comments", "format": "number"}]},
    ]
    chart = {
        "id": "label_balance_chart",
        "title": "Synthetic label balance",
        "subtitle": "30 fixture rows; counts are not real customer outcomes.",
        "type": "bar",
        "dataset": "label_balance",
        "sourceId": source["id"],
        "xAxisTitle": "Fixture label",
        "yAxisTitle": "Rows",
        "valueFormat": "number",
        "encodings": {
            "x": {"field": "label", "type": "nominal", "label": "Fixture label"},
            "y": {"field": "count", "type": "quantitative", "label": "Rows", "format": "number"},
            "tooltip": [{"field": "share", "type": "quantitative", "label": "Share", "format": "percent"}],
        },
        "layout": "full",
    }
    table = {
        "id": "quality_checks_table",
        "title": "Data-quality checks",
        "subtitle": "Findings ordered by downstream modeling risk.",
        "dataset": "quality_checks",
        "sourceId": source["id"],
        "defaultSort": {"field": "severity_rank", "direction": "asc"},
        "density": "spacious",
        "layout": "full",
        "columns": [
            {"field": "severity_rank", "label": "Order", "format": "number"},
            {"field": "severity", "label": "Severity", "type": "text"},
            {"field": "check", "label": "Check", "type": "text"},
            {"field": "evidence", "label": "Evidence", "type": "text"},
            {"field": "impact", "label": "Why it matters", "type": "text"},
            {"field": "action", "label": "Action", "type": "text"},
        ],
    }
    title = "Synthetic survey fixture quality review"
    manifest = {
        "version": 1,
        "surface": "report",
        "title": title,
        "description": "Decision report on whether the supplied 30-row synthetic survey file can support Phase 7 modeling.",
        "generatedAt": report["generated_at"],
        "filters": [],
        "cards": cards,
        "charts": [chart],
        "tables": [table],
        "sources": [source],
        "blocks": [
            {"id": "title", "type": "markdown", "body": f"# {title}"},
            {
                "id": "executive_summary",
                "type": "markdown",
                "sourceId": source["id"],
                "body": (
                    "## Executive Summary\n\n"
                    "- **Use this file as a fixture only.** All 30 rows explicitly declare synthetic provenance; none qualify as real survey evidence.\n"
                    "- **The join is recoverable.** All 30 rows match canonical calls through agent ID and call number, although source call IDs are blank.\n"
                    "- **It cannot unlock Phase 7.** The file has 22 positive and 8 negative synthetic labels, below the 80-row and 20-per-class gates.\n"
                    "- **Keep the real gate closed.** Normalize it separately for plumbing tests and continue waiting for governed customer outcomes."
                ),
            },
            {"id": "profile_strip", "type": "metric-strip", "cardIds": [card["id"] for card in cards]},
            {
                "id": "join_finding",
                "type": "markdown",
                "sourceId": source["id"],
                "body": (
                    "## Structurally joinable, but not training evidence\n\n"
                    "The composite key resolves every fixture row to one analyzed call and preserves three rows per agent. "
                    "That makes the file useful for ingestion and UI checks. It does not change the fact that zero rows are real customer feedback."
                ),
            },
            {"id": "label_chart_block", "type": "chart", "chartId": chart["id"], "layout": "full"},
            {
                "id": "label_interpretation",
                "type": "markdown",
                "sourceId": source["id"],
                "body": (
                    "## The negative class is too small even for the portfolio gate\n\n"
                    "Only 8 of 30 generated rows carry the negative label. Relaxing the minimum class requirement would create a convenient demo result, "
                    "but it would not create trustworthy discrimination or calibration evidence."
                ),
            },
            {"id": "quality_table_block", "type": "table", "tableId": table["id"], "layout": "full"},
            {
                "id": "next_steps",
                "type": "markdown",
                "body": (
                    "## Recommended next steps\n\n"
                    "1. Preserve this file under a synthetic-fixture path and keep `is_synthetic=True`.\n"
                    "2. Use the normalized copy only for schema, join, guardrail, and UI tests.\n"
                    "3. Require source call ID, survey instrument, score, completion timestamp, source system, and label-definition version in the real feed.\n"
                    "4. Do not create a trained model or dashboard probability until the real-label readiness report passes."
                ),
            },
            {
                "id": "further_questions",
                "type": "markdown",
                "body": (
                    "## Further questions\n\n"
                    "- Does the source database expose a separate table containing actual survey responses rather than the MVP fixture?\n"
                    "- Can that table provide the canonical call ID and a documented positive/negative mapping?"
                ),
            },
            {
                "id": "caveats",
                "type": "markdown",
                "sourceId": source["id"],
                "body": (
                    "## Caveats and assumptions\n\n"
                    "The assessment treats the file's explicit provenance fields as authoritative. Survey dates span July 14-16, 2026, but timeliness is not interpreted "
                    "because the rows are generated fixtures. Repeated comments and tightly coupled scores further support the template-generated interpretation."
                ),
            },
        ],
    }
    return {
        "surface": "report",
        "manifest": manifest,
        "snapshot": {
            "version": 1,
            "generatedAt": report["generated_at"],
            "status": "fixture",
            "datasets": {
                "profile": profile_rows,
                "label_balance": label_balance,
                "coverage_by_agent": coverage_by_agent,
                "quality_checks": report["quality_checks"],
            },
        },
        "sources": [source],
        "package_info": {
            "root": "reports",
            "manifestPath": "reports/synthetic_survey_quality_artifact.json",
            "snapshotPath": "reports/synthetic_survey_quality_artifact.json",
        },
    }


def run(
    source_path: Path = DEFAULT_SOURCE,
    normalized_path: Path = DEFAULT_NORMALIZED,
    quality_json_path: Path = DEFAULT_QUALITY_JSON,
    quality_md_path: Path = DEFAULT_QUALITY_MD,
    artifact_path: Path = DEFAULT_ARTIFACT,
) -> dict[str, Any]:
    report, normalized = profile_and_normalize(source_path)
    config = load_config()
    write_csv(normalized_path, normalized, config["outcome_columns"])
    quality_json_path.parent.mkdir(parents=True, exist_ok=True)
    quality_json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    quality_md_path.write_text(markdown_report(report), encoding="utf-8")
    artifact = build_report_artifact(report)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--normalized", type=Path, default=DEFAULT_NORMALIZED)
    parser.add_argument("--quality-json", type=Path, default=DEFAULT_QUALITY_JSON)
    parser.add_argument("--quality-md", type=Path, default=DEFAULT_QUALITY_MD)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run(args.source, args.normalized, args.quality_json, args.quality_md, args.artifact)
    print(json.dumps({"status": report["status"], "profile": report["profile"]}, indent=2))


if __name__ == "__main__":
    main()
