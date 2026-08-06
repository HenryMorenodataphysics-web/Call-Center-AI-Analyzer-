#!/usr/bin/env python3
"""Build the lightweight, source-backed Supervisor Board artifact."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from . import build_kpi_dashboard as agent_dashboard


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = agent_dashboard.DEFAULT_INPUT
DEFAULT_CONFIG = agent_dashboard.DEFAULT_CONFIG
DEFAULT_OUTPUT = PROJECT_ROOT / "dashboard" / "supervisor_artifact.json"

PRIORITY_RANK = {"Needs attention": 1, "Watch": 2, "On track": 3}


def _one(rows: list[dict[str, Any]], **matches: Any) -> dict[str, Any]:
    selected = [
        row for row in rows if all(row.get(field) == value for field, value in matches.items())
    ]
    if len(selected) != 1:
        raise ValueError(f"Expected one row for {matches}, found {len(selected)}")
    return selected[0]


def _priority(aht_status: str, risk_status: str) -> tuple[str, str]:
    statuses = {aht_status, risk_status}
    if "Needs attention" in statuses:
        return "Needs attention", "At least one analyzed proxy is outside its portfolio threshold."
    if "Watch" in statuses:
        return "Watch", "At least one analyzed proxy is near its portfolio threshold."
    return "On track", "Analyzed AHT and risk proxies are within portfolio thresholds."


def build_supervisor_datasets(
    calls: list[dict[str, Any]],
    config: dict[str, Any],
    generated_at: str,
) -> dict[str, list[dict[str, Any]]]:
    base = agent_dashboard.build_datasets(calls, config, generated_at)
    datasets: dict[str, list[dict[str, Any]]] = {
        "team_summary": [],
        "agent_overview": [],
        "priority_distribution": [],
        "team_behavior_coverage": [],
        "coaching_queue": [],
        "review_calls": [],
    }

    summaries = base["kpi_summary"]
    statuses = base["kpi_status"]
    focuses = base["todays_focus"]
    highlights = base["call_highlights"]
    behavior_rows = base["behavior_rates"]

    for stage in config["stages"]:
        stage_id = stage["id"]
        stage_label = stage["label"]
        stage_summaries = sorted(
            (row for row in summaries if row["stage_id"] == stage_id),
            key=lambda row: row["agent_id"],
        )
        priority_counts: Counter[str] = Counter()
        overview_by_agent: dict[str, dict[str, Any]] = {}

        for summary in stage_summaries:
            common = {
                "agent_id": summary["agent_id"],
                "agent_name": summary["agent_name"],
                "agent_label": summary["agent_label"],
                "stage_id": stage_id,
                "stage": stage_label,
            }
            aht = _one(
                statuses,
                agent_id=summary["agent_id"],
                stage_id=stage_id,
                metric="Estimated AHT",
            )
            risk = _one(
                statuses,
                agent_id=summary["agent_id"],
                stage_id=stage_id,
                metric="Heuristic risk",
            )
            focus = _one(
                focuses,
                agent_id=summary["agent_id"],
                stage_id=stage_id,
            )
            priority, priority_reason = _priority(aht["status"], risk["status"])
            priority_counts[priority] += 1

            overview = {
                **common,
                "calls_reviewed": summary["calls_considered"],
                "estimated_aht_sec": summary["estimated_aht_sec"],
                "aht_goal_sec": summary["estimated_aht_goal_sec"],
                "aht_status": aht["status"],
                "heuristic_risk_score": summary["conversation_risk_score"],
                "risk_threshold": summary["risk_rubric_threshold"],
                "risk_status": risk["status"],
                "priority": priority,
                "priority_rank": PRIORITY_RANK[priority],
                "priority_reason": priority_reason,
                "focus_area": focus["focus_area"],
                "focus_reason": focus["why"],
                "recommended_action": focus["recommended_action"],
                "guardrail": focus["guardrail"],
                "freshness": generated_at,
            }
            datasets["agent_overview"].append(overview)
            overview_by_agent[summary["agent_id"]] = overview
            datasets["coaching_queue"].append(
                {
                    **common,
                    "priority": priority,
                    "priority_rank": PRIORITY_RANK[priority],
                    "focus_area": focus["focus_area"],
                    "why_now": focus["why"],
                    "next_action": focus["recommended_action"],
                    "guardrail": focus["guardrail"],
                    "evidence_type": focus["evidence_type"],
                    "calls_reviewed": focus["calls_considered"],
                }
            )

        stage_behavior = [
            row
            for row in behavior_rows
            if row["stage_id"] == stage_id and row["series"] == "Detected"
        ]
        detected_by_behavior = {
            behavior: round(mean(row["value"] for row in stage_behavior if row["behavior"] == behavior), 4)
            for behavior in sorted({row["behavior"] for row in stage_behavior})
        }
        benchmark_by_label = {
            spec["label"]: float(spec["target"])
            for spec in config["behavior_benchmarks"].values()
        }
        for behavior, detected in detected_by_behavior.items():
            for series, value in (
                ("Team detected", detected),
                ("Coaching benchmark", benchmark_by_label[behavior]),
            ):
                datasets["team_behavior_coverage"].append(
                    {
                        "stage_id": stage_id,
                        "stage": stage_label,
                        "behavior": behavior,
                        "series": series,
                        "value": value,
                    }
                )

        team_summary = {
            "stage_id": stage_id,
            "stage": stage_label,
            "calls_reviewed": sum(row["calls_considered"] for row in stage_summaries),
            "agents_in_view": len(stage_summaries),
            "agents_needing_attention": priority_counts["Needs attention"],
            "agents_watch": priority_counts["Watch"],
            "team_estimated_aht_sec": round(mean(row["estimated_aht_sec"] for row in stage_summaries), 2),
            "aht_goal_sec": float(config["headline_kpis"]["estimated_aht_sec"]["target"]),
            "team_heuristic_risk": round(mean(row["conversation_risk_score"] for row in stage_summaries), 2),
            "risk_threshold": float(config["headline_kpis"]["conversation_risk_score"]["target"]),
            "next_steps_rate": detected_by_behavior["Next steps"],
            "next_steps_benchmark": benchmark_by_label["Next steps"],
            "freshness": generated_at,
        }
        datasets["team_summary"].append(team_summary)

        for priority in ("Needs attention", "Watch", "On track"):
            datasets["priority_distribution"].append(
                {
                    "stage_id": stage_id,
                    "stage": stage_label,
                    "priority": priority,
                    "priority_rank": PRIORITY_RANK[priority],
                    "agent_count": priority_counts[priority],
                }
            )

        stage_highlights = sorted(
            (row for row in highlights if row["stage_id"] == stage_id),
            key=lambda row: (row["agent_id"], row["highlight"]),
        )
        for row in stage_highlights:
            overview = overview_by_agent[row["agent_id"]]
            coachable = row["highlight"].startswith("Most coachable")
            queue_label = overview["priority"] if coachable else "Share strength"
            queue_order = overview["priority_rank"] if coachable else 4
            datasets["review_calls"].append(
                {
                    "agent_id": row["agent_id"],
                    "agent_name": row["agent_name"],
                    "agent_label": row["agent_label"],
                    "stage_id": stage_id,
                    "stage": stage_label,
                    "queue_label": queue_label,
                    "queue_order": queue_order,
                    "selection": row["highlight"],
                    "call_number": row["call_number"],
                    "call_id": row["call_id"],
                    "estimated_aht_sec": row["estimated_aht_sec"],
                    "heuristic_risk_score": row["heuristic_risk_score"],
                    "rubric_reasons": row["reason"],
                    "evidence": row["evidence"],
                }
            )

    return datasets


def source_specs(generated_at: str) -> list[dict[str, Any]]:
    sources = agent_dashboard.source_specs(generated_at)
    call_source = next(source for source in sources if source["id"] == "call_analysis")
    rule_source = next(source for source in sources if source["id"] == "dashboard_rules")
    rule_source = json.loads(json.dumps(rule_source))
    rule_source["label"] = "Auditable supervisor triage and coaching queue rules"
    rule_source["path"] = "src/dashboard/build_supervisor_dashboard.py"
    rule_source["query"]["description"] = (
        "Aggregates the validated agent-stage KPI artifact into team health, proxy-based "
        "attention categories, coaching actions, and call review queues."
    )
    rule_source["query"]["metric_definitions"] = [
        "Team AHT and risk = arithmetic mean of agent means; every agent contributes the same call count within a shift view.",
        "Needs attention = AHT or heuristic-risk proxy has Needs attention status; Watch applies only when neither proxy needs attention.",
        "Coaching queue is an evidence-review aid, not an employee ranking or disciplinary score.",
    ]
    return [call_source, rule_source]


def build_artifact(
    calls: list[dict[str, Any]],
    config: dict[str, Any],
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    datasets = build_supervisor_datasets(calls, config, generated_at)
    dataset_names = list(datasets)
    sources = source_specs(generated_at)
    default_stage = next(stage["label"] for stage in config["stages"] if stage["id"] == "live")

    cards = [
        {
            "id": "calls_reviewed",
            "description": "Analyzed calls included across all 10 agents in the selected simulated shift view.",
            "dataset": "team_summary",
            "sourceId": "call_analysis",
            "metrics": [{"label": "Calls reviewed", "field": "calls_reviewed", "format": "number"}],
        },
        {
            "id": "attention_queue",
            "description": "Agents whose AHT or risk proxy crosses a portfolio triage threshold; not a performance rank.",
            "dataset": "team_summary",
            "sourceId": "dashboard_rules",
            "metrics": [
                {"label": "Needs attention", "field": "agents_needing_attention", "format": "number"},
                {"label": "Watch", "field": "agents_watch", "format": "number"},
            ],
        },
        {
            "id": "team_aht",
            "description": "Mean analyzed audio duration across equal-sized agent views; proxy only.",
            "dataset": "team_summary",
            "sourceId": "call_analysis",
            "metrics": [
                {"label": "Team est. AHT - sec", "field": "team_estimated_aht_sec", "format": "number"},
                {"label": "Portfolio goal - sec", "field": "aht_goal_sec", "format": "number"},
            ],
        },
        {
            "id": "team_risk",
            "description": "Mean conversation_risk_v1 score; uncalibrated and not a customer outcome.",
            "dataset": "team_summary",
            "sourceId": "call_analysis",
            "metrics": [
                {"label": "Team heuristic risk", "field": "team_heuristic_risk", "format": "number"},
                {"label": "Rubric threshold", "field": "risk_threshold", "format": "number"},
            ],
        },
        {
            "id": "next_steps",
            "description": "Share of analyzed calls with at least one rule-based next-steps match.",
            "dataset": "team_summary",
            "sourceId": "call_analysis",
            "metrics": [
                {"label": "Next steps coverage", "field": "next_steps_rate", "format": "percent"},
                {"label": "Coaching benchmark", "field": "next_steps_benchmark", "format": "percent"},
            ],
        },
    ]

    charts = [
        {
            "id": "agent_proxy_map",
            "title": "Agent proxy map",
            "subtitle": "Use the map to select evidence for review, not to rank people or infer official outcomes.",
            "type": "scatter",
            "dataset": "agent_overview",
            "sourceId": "dashboard_rules",
            "xAxisTitle": "Estimated AHT - seconds",
            "yAxisTitle": "Heuristic risk points",
            "valueFormat": "number",
            "encodings": {
                "x": {"field": "estimated_aht_sec", "type": "quantitative", "label": "Est. AHT sec"},
                "y": {"field": "heuristic_risk_score", "type": "quantitative", "label": "Risk proxy"},
                "color": {"field": "priority", "type": "nominal", "label": "Triage status"},
                "tooltip": [
                    {"field": "agent_label", "type": "text", "label": "Agent"},
                    {"field": "focus_area", "type": "text", "label": "Coaching focus"},
                    {"field": "calls_reviewed", "type": "quantitative", "label": "Calls reviewed"},
                ],
            },
            "layout": "half",
        },
        {
            "id": "attention_distribution",
            "title": "Team triage distribution",
            "subtitle": "Count of agents by proxy-based review status in the selected shift view.",
            "type": "bar",
            "dataset": "priority_distribution",
            "sourceId": "dashboard_rules",
            "xAxisTitle": "Triage status",
            "yAxisTitle": "Agents",
            "valueFormat": "number",
            "encodings": {
                "x": {"field": "priority", "type": "nominal", "label": "Triage status"},
                "y": {"field": "agent_count", "type": "quantitative", "label": "Agents", "format": "number"},
            },
            "layout": "half",
        },
        {
            "id": "team_behaviors",
            "title": "Detected service behaviors",
            "subtitle": "Team call coverage versus portfolio coaching benchmarks; rule matches are coaching evidence, not QA failures.",
            "type": "bar",
            "dataset": "team_behavior_coverage",
            "sourceId": "call_analysis",
            "xAxisTitle": "Behavior",
            "yAxisTitle": "Call rate",
            "valueFormat": "percent",
            "encodings": {
                "x": {"field": "behavior", "type": "nominal", "label": "Behavior"},
                "y": {"field": "value", "type": "quantitative", "label": "Call rate", "format": "percent"},
                "color": {"field": "series", "type": "nominal", "label": "Series"},
            },
            "layout": "full",
        },
    ]

    tables = [
        {
            "id": "coaching_queue_table",
            "title": "Coaching queue",
            "subtitle": "One explainable action per agent, ordered for evidence review rather than discipline.",
            "dataset": "coaching_queue",
            "sourceId": "dashboard_rules",
            "defaultSort": {"field": "priority_rank", "direction": "asc"},
            "density": "dense",
            "layout": "full",
            "columns": [
                {"field": "priority_rank", "label": "Queue order", "format": "number"},
                {"field": "priority", "label": "Triage status", "type": "text"},
                {"field": "agent_label", "label": "Agent", "type": "text"},
                {"field": "focus_area", "label": "Focus", "type": "text"},
                {"field": "why_now", "label": "Why now", "type": "text"},
                {"field": "next_action", "label": "Next action", "type": "text"},
                {"field": "guardrail", "label": "Guardrail", "type": "text"},
                {"field": "calls_reviewed", "label": "Calls", "format": "number"},
            ],
        },
        {
            "id": "agent_overview_table",
            "title": "Agent context",
            "subtitle": "Exact proxy values and focus area supporting the team view.",
            "dataset": "agent_overview",
            "sourceId": "dashboard_rules",
            "defaultSort": {"field": "priority_rank", "direction": "asc"},
            "density": "dense",
            "layout": "full",
            "columns": [
                {"field": "priority_rank", "label": "Queue order", "format": "number"},
                {"field": "agent_label", "label": "Agent", "type": "text"},
                {"field": "calls_reviewed", "label": "Calls", "format": "number"},
                {"field": "estimated_aht_sec", "label": "Est. AHT sec", "format": "number"},
                {"field": "aht_status", "label": "AHT status", "type": "text"},
                {"field": "heuristic_risk_score", "label": "Risk proxy", "format": "number"},
                {"field": "risk_status", "label": "Risk status", "type": "text"},
                {"field": "focus_area", "label": "Coaching focus", "type": "text"},
            ],
        },
        {
            "id": "review_calls_table",
            "title": "Calls to review or share",
            "subtitle": "Coachable candidates appear first; best-call examples remain available for positive reinforcement.",
            "dataset": "review_calls",
            "sourceId": "dashboard_rules",
            "defaultSort": {"field": "queue_order", "direction": "asc"},
            "density": "dense",
            "layout": "full",
            "columns": [
                {"field": "queue_order", "label": "Review order", "format": "number"},
                {"field": "queue_label", "label": "Purpose", "type": "text"},
                {"field": "agent_label", "label": "Agent", "type": "text"},
                {"field": "selection", "label": "Selection", "type": "text"},
                {"field": "call_number", "label": "Call #", "format": "number"},
                {"field": "call_id", "label": "Call ID", "type": "text"},
                {"field": "heuristic_risk_score", "label": "Risk proxy", "format": "number"},
                {"field": "estimated_aht_sec", "label": "Est. AHT sec", "format": "number"},
                {"field": "rubric_reasons", "label": "Rubric reasons", "type": "text"},
                {"field": "evidence", "label": "Turn evidence", "type": "text"},
            ],
        },
    ]

    manifest = {
        "version": 1,
        "surface": "dashboard",
        "title": "Supervisor Team Performance Board - MVP",
        "description": "Lightweight supervisor view for team health, explainable triage, coaching actions, and call evidence without running the Copilot.",
        "generatedAt": generated_at,
        "filters": [
            {
                "id": "shift_view",
                "label": "Shift view",
                "dataset": "team_summary",
                "field": "stage",
                "defaultValue": default_stage,
                "includeAll": False,
                "targets": agent_dashboard.filter_targets(dataset_names, "stage"),
            }
        ],
        "cards": cards,
        "charts": charts,
        "tables": tables,
        "sources": sources,
        "blocks": [
            {
                "id": "operating_boundary",
                "type": "markdown",
                "body": (
                    "## Team view without micromanagement\n\n"
                    "Use this board to choose where evidence deserves review and where strong examples can be shared. "
                    "It does not run the local LLM. Estimated AHT and conversation risk are proxies; triage categories "
                    "are not employee ratings, disciplinary findings, or official customer outcomes."
                ),
            },
            {"id": "team_health", "type": "metric-strip", "cardIds": [card["id"] for card in cards]},
            {"id": "proxy_map_block", "type": "chart", "chartId": "agent_proxy_map", "layout": "half"},
            {"id": "distribution_block", "type": "chart", "chartId": "attention_distribution", "layout": "half"},
            {"id": "behavior_block", "type": "chart", "chartId": "team_behaviors", "layout": "full"},
            {"id": "coaching_queue_block", "type": "table", "tableId": "coaching_queue_table", "layout": "full"},
            {"id": "agent_context_block", "type": "table", "tableId": "agent_overview_table", "layout": "full"},
            {"id": "review_calls_block", "type": "table", "tableId": "review_calls_table", "layout": "full"},
            {
                "id": "limitations",
                "type": "markdown",
                "body": (
                    "## Evidence and limits\n\n"
                    "Shift views simulate progress from call sequence. Behavior coverage is rule-based and a missing flag "
                    "does not prove the behavior was absent. Targets are portfolio assumptions. Replace demo thresholds "
                    "with governed workforce definitions before operational use."
                ),
            },
        ],
    }
    return {
        "surface": "dashboard",
        "manifest": manifest,
        "snapshot": {
            "version": 1,
            "generatedAt": generated_at,
            "status": "fixture",
            "datasets": datasets,
        },
        "sources": sources,
        "package_info": {
            "root": "dashboard",
            "manifestPath": "dashboard/supervisor_artifact.json",
            "snapshotPath": "dashboard/supervisor_artifact.json",
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = agent_dashboard.load_config(args.config)
    calls = agent_dashboard.normalize_calls(agent_dashboard.read_calls_via_sqlite(args.input))
    agent_dashboard.validate_input(calls)
    artifact = build_artifact(calls, config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"Wrote {args.output} with {len(artifact['snapshot']['datasets']['agent_overview'])} "
        "agent-stage rows."
    )


if __name__ == "__main__":
    main()
