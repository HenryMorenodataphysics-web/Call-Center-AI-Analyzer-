#!/usr/bin/env python3
"""Build the portable KPI Performance Tracker artifact."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "final_outputs" / "all_calls_summary.csv"
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "demo_kpi_targets.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "dashboard" / "artifact.json"

SYNTHETIC_FIELDS = ("csat_demo", "qa_demo", "nps_demo", "five_star_demo")
ANALYZED_BEHAVIORS = {
    "empathy_call_rate": "agent_empathy_turns",
    "probing_call_rate": "agent_probing_turns",
    "ownership_call_rate": "agent_ownership_turns",
    "next_steps_call_rate": "agent_next_steps_turns",
}
SOURCE_SQL = (
    "SELECT * FROM all_calls_summary "
    "ORDER BY agent_id, CAST(agent_call_number AS INTEGER)"
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_calls_via_sqlite(path: Path) -> list[dict[str, str]]:
    """Load the canonical CSV and execute the exact source query in SQLite."""

    raw_rows = read_csv(path)
    if not raw_rows:
        return []
    columns = list(raw_rows[0])
    quoted_columns = ", ".join(f'"{column}" TEXT' for column in columns)
    placeholders = ", ".join("?" for _ in columns)
    insert_columns = ", ".join(f'"{column}"' for column in columns)
    with sqlite3.connect(":memory:") as connection:
        connection.execute(f"CREATE TABLE all_calls_summary ({quoted_columns})")
        connection.executemany(
            f"INSERT INTO all_calls_summary ({insert_columns}) VALUES ({placeholders})",
            [[row[column] for column in columns] for row in raw_rows],
        )
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(SOURCE_SQL).fetchall()]


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def stable_unit_interval(*parts: str) -> float:
    """Return a stable pseudo-random value in [0, 1) without global state."""

    digest = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def synthetic_call_kpis(call: dict[str, str]) -> dict[str, float]:
    """Generate deterministic UI fixtures that are never treated as outcomes."""

    agent_id = call["agent_id"]
    call_id = call["call_id"]

    def centered(key: str, scope: str) -> float:
        return stable_unit_interval(scope, key) - 0.5

    values = {
        "csat_demo": clamp(
            0.875
            + centered(agent_id, "csat-agent") * 0.08
            + centered(call_id, "csat-call") * 0.16,
            0.70,
            0.99,
        ),
        "qa_demo": clamp(
            0.90
            + centered(agent_id, "qa-agent") * 0.07
            + centered(call_id, "qa-call") * 0.12,
            0.76,
            0.99,
        ),
        "nps_demo": clamp(
            50
            + centered(agent_id, "nps-agent") * 24
            + centered(call_id, "nps-call") * 42,
            -20,
            90,
        ),
        "five_star_demo": clamp(
            0.82
            + centered(agent_id, "five-star-agent") * 0.10
            + centered(call_id, "five-star-call") * 0.20,
            0.55,
            0.98,
        ),
    }
    return {key: round(value, 4) for key, value in values.items()}


def projected_mean(values: list[float], total_calls: int = 10) -> float:
    """Project the final mean using the latest three observations for remainder."""

    if not values:
        return math.nan
    if len(values) >= total_calls:
        return mean(values)
    recent_mean = mean(values[-min(3, len(values)) :])
    remaining = total_calls - len(values)
    return (sum(values) + recent_mean * remaining) / total_calls


def format_value(metric: str, value: float) -> str:
    if metric in {"csat_demo", "qa_demo", "five_star_demo"}:
        return f"{value:.1%}"
    if metric == "estimated_aht_sec":
        return f"{value:.0f} sec"
    if metric == "conversation_risk_score":
        return f"{value:.1f} pts"
    return f"{value:.1f}"


def status_for(value: float, target: float, direction: str) -> str:
    if direction == "lower_is_better":
        ratio = value / target if target else 0
        if ratio <= 1:
            return "On track"
        if ratio <= 1.10:
            return "Watch"
        return "Needs attention"
    ratio = value / target if target else 1
    if ratio >= 1:
        return "On track"
    if ratio >= 0.95:
        return "Watch"
    return "Needs attention"


def trend_text(
    metric: str,
    current: float,
    previous: float | None,
    direction: str,
) -> str:
    if previous is None:
        return "Baseline"
    delta = current - previous
    if metric in {"csat_demo", "qa_demo", "five_star_demo"}:
        magnitude = f"{abs(delta) * 100:.1f} pp"
    elif metric == "estimated_aht_sec":
        magnitude = f"{abs(delta):.0f} sec"
    else:
        magnitude = f"{abs(delta):.1f} pts"
    if abs(delta) < 1e-9:
        return "No change"
    improving = delta < 0 if direction == "lower_is_better" else delta > 0
    arrow = "up" if delta > 0 else "down"
    return f"{arrow} {magnitude} - {'better' if improving else 'worse'}"


def metric_action(metric: str, status: str) -> str:
    if status == "On track":
        return "Maintain the current approach and protect customer-service guardrails."
    actions = {
        "estimated_aht_sec": (
            "Use a concise issue recap and confirm the next step before closing; "
            "do not shorten required troubleshooting or compliance steps."
        ),
        "conversation_risk_score": (
            "Review the coachable call evidence and practice the missing behavior "
            "shown in Today's Focus."
        ),
        "csat_demo": "Demo only: replace this placeholder with the real survey feed.",
        "qa_demo": "Demo only: replace this placeholder with the official QA scorecard.",
        "nps_demo": "Demo only: replace this placeholder with the real NPS feed.",
        "five_star_demo": "Demo only: replace this placeholder with the real rating feed.",
    }
    return actions[metric]


def evidence_excerpt(call: dict[str, str]) -> str:
    codes = [code for code in call.get("reason_codes", "").split("|") if code]
    try:
        evidence = json.loads(call.get("evidence_json", "{}") or "{}")
    except json.JSONDecodeError:
        evidence = {}
    parts: list[str] = []
    for code in codes[:3]:
        turns = evidence.get(code, [])
        if turns:
            preview = ", ".join(str(turn) for turn in turns[:3])
            parts.append(f"{code}: turns {preview}")
        else:
            parts.append(f"{code}: no matched turn")
    return "; ".join(parts) or "No stable reason code was emitted."


def choose_call_highlights(calls: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    def behavior_count(call: dict[str, Any]) -> int:
        return sum(int(float(call[column]) > 0) for column in ANALYZED_BEHAVIORS.values())

    best = min(
        calls,
        key=lambda call: (
            float(call["conversation_risk_score"]),
            -behavior_count(call),
            float(call["estimated_aht_sec"]),
            int(call["agent_call_number"]),
        ),
    )
    coachable = max(
        calls,
        key=lambda call: (
            float(call["conversation_risk_score"]),
            4 - behavior_count(call),
            float(call["negative_customer_turns"]),
            -int(call["agent_call_number"]),
        ),
    )
    return best, coachable


def focus_recommendation(
    calls: list[dict[str, Any]],
    config: dict[str, Any],
) -> dict[str, str]:
    behavior_rates: dict[str, float] = {}
    for behavior, source_column in ANALYZED_BEHAVIORS.items():
        behavior_rates[behavior] = mean(float(call[source_column]) > 0 for call in calls)

    aht = mean(float(call["estimated_aht_sec"]) for call in calls)
    aht_target = config["headline_kpis"]["estimated_aht_sec"]["target"]
    aht_gap = (aht - aht_target) / aht_target

    gaps = {
        behavior: (
            config["behavior_benchmarks"][behavior]["target"] - rate
        )
        / config["behavior_benchmarks"][behavior]["target"]
        for behavior, rate in behavior_rates.items()
    }
    weakest_behavior = max(gaps, key=gaps.get)
    weakest_gap = gaps[weakest_behavior]

    if aht_gap > 0.08 and weakest_gap <= 0.20:
        return {
            "focus_area": "Efficient resolution",
            "why": (
                f"Estimated AHT is {aht:.0f} sec versus the {aht_target:.0f}-sec "
                "portfolio demo goal, while analyzed behavior coverage is comparatively stable."
            ),
            "recommended_action": (
                "Open with one clarifying question, recap the issue once, and close with a "
                "specific next step."
            ),
            "guardrail": "Do not skip required troubleshooting, empathy, QA, or compliance steps.",
            "evidence_type": "Derived AHT proxy plus analyzed behavior flags",
        }

    labels = config["behavior_benchmarks"]
    behavior_label = labels[weakest_behavior]["label"]
    rate = behavior_rates[weakest_behavior]
    actions = {
        "empathy_call_rate": (
            "Acknowledge the customer's impact in one natural sentence before moving to the solution."
        ),
        "probing_call_rate": (
            "Ask one precise diagnostic question before proposing the resolution path."
        ),
        "ownership_call_rate": (
            "State what you will do next and what remains under your ownership."
        ),
        "next_steps_call_rate": (
            "End with owner, action, and expected timing in one concise recap."
        ),
    }
    return {
        "focus_area": behavior_label,
        "why": (
            f"{behavior_label} appeared in {rate:.0%} of the calls in this view, below the "
            f"{labels[weakest_behavior]['target']:.0%} portfolio coaching benchmark."
        ),
        "recommended_action": actions[weakest_behavior],
        "guardrail": "Treat the flag as coaching evidence, not as an official QA failure.",
        "evidence_type": "Rule-based analyzed behavior flags",
    }


def normalize_calls(raw_calls: Iterable[dict[str, str]]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    required = {
        "call_id",
        "agent_id",
        "agent_name",
        "agent_call_number",
        "estimated_aht_sec",
        "conversation_risk_score",
        *ANALYZED_BEHAVIORS.values(),
    }
    for raw in raw_calls:
        missing = required.difference(raw)
        if missing:
            raise ValueError(f"Call summary is missing required fields: {sorted(missing)}")
        call: dict[str, Any] = dict(raw)
        call.update(synthetic_call_kpis(raw))
        calls.append(call)
    return calls


def validate_input(calls: list[dict[str, Any]]) -> None:
    call_ids = [call["call_id"] for call in calls]
    if len(call_ids) != len(set(call_ids)):
        raise ValueError("all_calls_summary.csv contains duplicate call_id values")
    by_agent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for call in calls:
        by_agent[call["agent_id"]].append(call)
    if len(by_agent) != 10:
        raise ValueError(f"Expected 10 agents, found {len(by_agent)}")
    invalid = {agent: len(rows) for agent, rows in by_agent.items() if len(rows) != 10}
    if invalid:
        raise ValueError(f"Expected 10 calls per agent, found {invalid}")


def build_datasets(
    calls: list[dict[str, Any]],
    config: dict[str, Any],
    generated_at: str,
) -> dict[str, list[dict[str, Any]]]:
    by_agent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for call in calls:
        by_agent[call["agent_id"]].append(call)
    for agent_calls in by_agent.values():
        agent_calls.sort(key=lambda call: int(call["agent_call_number"]))

    datasets: dict[str, list[dict[str, Any]]] = {
        "kpi_summary": [],
        "aht_trend": [],
        "quality_demo_trend": [],
        "risk_trend": [],
        "behavior_rates": [],
        "kpi_status": [],
        "todays_focus": [],
        "call_highlights": [],
    }
    prior_values: dict[tuple[str, str], float] = {}
    targets = config["headline_kpis"]

    for agent_id in sorted(by_agent):
        all_agent_calls = by_agent[agent_id]
        agent_name = all_agent_calls[0]["agent_name"]
        agent_label = f"{agent_name} - {agent_id}"

        for stage in config["stages"]:
            stage_label = stage["label"]
            stage_calls = all_agent_calls[: int(stage["calls"])]
            common = {
                "agent_id": agent_id,
                "agent_name": agent_name,
                "agent_label": agent_label,
                "stage": stage_label,
                "stage_id": stage["id"],
            }

            metric_values: dict[str, list[float]] = {
                "estimated_aht_sec": [float(call["estimated_aht_sec"]) for call in stage_calls],
                "conversation_risk_score": [
                    float(call["conversation_risk_score"]) for call in stage_calls
                ],
            }
            for metric in SYNTHETIC_FIELDS:
                metric_values[metric] = [float(call[metric]) for call in stage_calls]

            current = {metric: mean(values) for metric, values in metric_values.items()}
            projection = {
                metric: projected_mean(values) for metric, values in metric_values.items()
            }
            summary = {
                **common,
                "calls_considered": len(stage_calls),
                "estimated_aht_sec": round(current["estimated_aht_sec"], 2),
                "estimated_aht_goal_sec": targets["estimated_aht_sec"]["target"],
                "estimated_aht_projection_sec": round(projection["estimated_aht_sec"], 2),
                "conversation_risk_score": round(current["conversation_risk_score"], 2),
                "risk_rubric_threshold": targets["conversation_risk_score"]["target"],
                "conversation_risk_projection": round(
                    projection["conversation_risk_score"], 2
                ),
                "csat_demo": round(current["csat_demo"], 4),
                "csat_demo_goal": targets["csat_demo"]["target"],
                "csat_demo_projection": round(projection["csat_demo"], 4),
                "qa_demo": round(current["qa_demo"], 4),
                "qa_demo_goal": targets["qa_demo"]["target"],
                "qa_demo_projection": round(projection["qa_demo"], 4),
                "nps_demo": round(current["nps_demo"], 2),
                "nps_demo_goal": targets["nps_demo"]["target"],
                "nps_demo_projection": round(projection["nps_demo"], 2),
                "five_star_demo": round(current["five_star_demo"], 4),
                "five_star_demo_goal": targets["five_star_demo"]["target"],
                "five_star_demo_projection": round(projection["five_star_demo"], 4),
                "freshness": generated_at,
            }
            datasets["kpi_summary"].append(summary)

            for metric, metric_config in targets.items():
                value = current[metric]
                target = float(metric_config["target"])
                status = status_for(value, target, metric_config["direction"])
                previous = prior_values.get((agent_id, metric))
                datasets["kpi_status"].append(
                    {
                        **common,
                        "metric": metric_config["label"],
                        "current": format_value(metric, value),
                        "goal": format_value(metric, target),
                        "trend": trend_text(
                            metric, value, previous, metric_config["direction"]
                        ),
                        "projection": format_value(metric, projection[metric]),
                        "status": status,
                        "freshness": "Generated portfolio snapshot",
                        "recommended_action": metric_action(metric, status),
                        "source_type": metric_config["source_type"],
                    }
                )
                prior_values[(agent_id, metric)] = value

            for call in stage_calls:
                call_common = {
                    **common,
                    "call_number": int(call["agent_call_number"]),
                    "call_id": call["call_id"],
                }
                for series, value in (
                    ("Estimated AHT", float(call["estimated_aht_sec"])),
                    ("Demo goal", targets["estimated_aht_sec"]["target"]),
                ):
                    datasets["aht_trend"].append(
                        {**call_common, "series": series, "value": round(value, 2)}
                    )
                for series, value in (
                    ("CSAT - demo", call["csat_demo"]),
                    ("QA - demo", call["qa_demo"]),
                    ("Five Stars - demo", call["five_star_demo"]),
                ):
                    datasets["quality_demo_trend"].append(
                        {**call_common, "series": series, "value": value}
                    )
                for series, value in (
                    ("Heuristic risk", float(call["conversation_risk_score"])),
                    ("Rubric threshold", targets["conversation_risk_score"]["target"]),
                ):
                    datasets["risk_trend"].append(
                        {**call_common, "series": series, "value": value}
                    )

            for behavior, source_column in ANALYZED_BEHAVIORS.items():
                rate = mean(float(call[source_column]) > 0 for call in stage_calls)
                behavior_config = config["behavior_benchmarks"][behavior]
                for series, value in (
                    ("Detected", round(rate, 4)),
                    ("Coaching benchmark", behavior_config["target"]),
                ):
                    datasets["behavior_rates"].append(
                        {
                            **common,
                            "behavior": behavior_config["label"],
                            "series": series,
                            "value": value,
                        }
                    )

            best, coachable = choose_call_highlights(stage_calls)
            focus = focus_recommendation(stage_calls, config)
            datasets["todays_focus"].append(
                {
                    **common,
                    **focus,
                    "calls_considered": len(stage_calls),
                    "freshness": "Generated portfolio snapshot",
                    "recap": (
                        f"Reviewed {len(stage_calls)} calls. Best analyzed call: "
                        f"#{best['agent_call_number']}. Most coachable candidate: "
                        f"#{coachable['agent_call_number']}."
                    ),
                }
            )

            for highlight_type, call in (
                ("Best analyzed call - heuristic", best),
                ("Most coachable candidate - heuristic", coachable),
            ):
                datasets["call_highlights"].append(
                    {
                        **common,
                        "highlight": highlight_type,
                        "call_number": int(call["agent_call_number"]),
                        "call_id": call["call_id"],
                        "estimated_aht_sec": round(float(call["estimated_aht_sec"]), 2),
                        "heuristic_risk_score": float(call["conversation_risk_score"]),
                        "risk_level": call["conversation_risk_level"],
                        "reason": call.get("main_reasons", ""),
                        "evidence": evidence_excerpt(call),
                    }
                )

    return datasets


def source_specs(generated_at: str) -> list[dict[str, Any]]:
    query_base = {
        "engine": "sqlite",
        "language": "sql",
        "sql": SOURCE_SQL,
        "executed_at": generated_at,
        "tables_used": ["all_calls_summary"],
        "filters": [
            "Canonical CSV validated as 10 agents with 10 unique calls each",
            "Rows ordered by agent_id and integer agent_call_number before Python transformations",
        ],
    }
    return [
        {
            "id": "call_analysis",
            "label": "Analyzed call summaries - canonical 100-call CSV",
            "path": "data/final_outputs/all_calls_summary.csv",
            "query": {
                **query_base,
                "description": (
                    "Selects the canonical analyzed call summaries that feed AHT, risk, "
                    "behavior rates, and call-highlight rules."
                ),
                "metric_definitions": [
                    "Estimated AHT = mean analyzed audio duration in seconds for calls in the selected view.",
                    "Heuristic risk = mean conversation_risk_v1 score; it is uncalibrated and not an outcome.",
                    "Behavior call rate = calls with at least one matched behavior turn divided by calls in view.",
                ],
            },
        },
        {
            "id": "synthetic_business_kpis",
            "label": "Synthetic business KPI fixture definitions - portfolio demo only",
            "path": "config/demo_kpi_targets.json",
            "query": {
                **query_base,
                "description": (
                    "Selects call and agent identifiers used as deterministic SHA-256 seeds; "
                    "Python then creates portfolio-only UI fixtures, not predictions."
                ),
                "metric_definitions": [
                    "Synthetic KPI current value = arithmetic mean of deterministic per-call fixture values.",
                    "Projection = observed fixtures plus the latest three-value mean for remaining demo calls, divided by 10.",
                ],
            },
        },
        {
            "id": "dashboard_rules",
            "label": "Auditable KPI, projection, focus, and call-highlight rules",
            "path": "src/dashboard/build_kpi_dashboard.py",
            "query": {
                **query_base,
                "description": (
                    "Selects the ordered call rows consumed by deterministic Python coaching "
                    "and call-highlight rules."
                ),
                "metric_definitions": [
                    "Best call = lowest heuristic risk, then more detected positive behaviors, then lower estimated AHT.",
                    "Coachable candidate = highest heuristic risk, then more missing positive behaviors and negative customer turns.",
                    "Today's Focus prioritizes material AHT gaps only when behavior coverage is stable; otherwise it selects the largest behavior benchmark gap.",
                ],
            },
        },
    ]


def filter_targets(dataset_names: Iterable[str], primary: str) -> list[dict[str, str]]:
    return [
        {"dataset": dataset, "field": primary}
        for dataset in dataset_names
        if dataset != "kpi_summary"
    ]


def build_artifact(
    calls: list[dict[str, Any]],
    config: dict[str, Any],
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    datasets = build_datasets(calls, config, generated_at)
    dataset_names = list(datasets)
    sources = source_specs(generated_at)
    first_agent = min(calls, key=lambda call: call["agent_id"])
    default_agent = f"{first_agent['agent_name']} - {first_agent['agent_id']}"
    default_stage = next(stage["label"] for stage in config["stages"] if stage["id"] == "live")

    cards = [
        {
            "id": "calls_considered",
            "description": "Calls included in the selected simulated shift view.",
            "dataset": "kpi_summary",
            "sourceId": "call_analysis",
            "metrics": [{"label": "Calls considered", "field": "calls_considered", "format": "number"}],
        },
        {
            "id": "estimated_aht",
            "description": "Mean analyzed audio duration; proxy only, not production telephony AHT.",
            "dataset": "kpi_summary",
            "sourceId": "call_analysis",
            "metrics": [
                {"label": "Est. AHT - sec", "field": "estimated_aht_sec", "format": "number"},
                {"label": "Goal - sec", "field": "estimated_aht_goal_sec", "format": "number"},
                {"label": "Projection - sec", "field": "estimated_aht_projection_sec", "format": "number"},
            ],
        },
        {
            "id": "heuristic_risk",
            "description": "Uncalibrated conversation_risk_v1 proxy; not CSAT, QA, or survey probability.",
            "dataset": "kpi_summary",
            "sourceId": "call_analysis",
            "metrics": [
                {"label": "Heuristic risk", "field": "conversation_risk_score", "format": "number"},
                {"label": "Rubric threshold", "field": "risk_rubric_threshold", "format": "number"},
                {"label": "Projection", "field": "conversation_risk_projection", "format": "number"},
            ],
        },
        {
            "id": "csat_demo",
            "description": "Synthetic portfolio fixture. Not observed CSAT and not a model prediction.",
            "dataset": "kpi_summary",
            "sourceId": "synthetic_business_kpis",
            "metrics": [
                {"label": "CSAT - demo", "field": "csat_demo", "format": "percent"},
                {"label": "Goal", "field": "csat_demo_goal", "format": "percent"},
                {"label": "Projection", "field": "csat_demo_projection", "format": "percent"},
            ],
        },
        {
            "id": "qa_demo",
            "description": "Synthetic portfolio fixture. Not an official QA evaluation.",
            "dataset": "kpi_summary",
            "sourceId": "synthetic_business_kpis",
            "metrics": [
                {"label": "QA - demo", "field": "qa_demo", "format": "percent"},
                {"label": "Goal", "field": "qa_demo_goal", "format": "percent"},
                {"label": "Projection", "field": "qa_demo_projection", "format": "percent"},
            ],
        },
        {
            "id": "nps_demo",
            "description": "Synthetic portfolio fixture. Not observed NPS.",
            "dataset": "kpi_summary",
            "sourceId": "synthetic_business_kpis",
            "metrics": [
                {"label": "NPS - demo", "field": "nps_demo", "format": "number"},
                {"label": "Goal", "field": "nps_demo_goal", "format": "number"},
                {"label": "Projection", "field": "nps_demo_projection", "format": "number"},
            ],
        },
        {
            "id": "five_star_demo",
            "description": "Synthetic portfolio fixture. Not an observed customer rating.",
            "dataset": "kpi_summary",
            "sourceId": "synthetic_business_kpis",
            "metrics": [
                {"label": "Five Stars - demo", "field": "five_star_demo", "format": "percent"},
                {"label": "Goal", "field": "five_star_demo_goal", "format": "percent"},
                {"label": "Projection", "field": "five_star_demo_projection", "format": "percent"},
            ],
        },
    ]

    charts = [
        {
            "id": "aht_by_call",
            "title": "Estimated AHT by call sequence",
            "subtitle": "Audio-duration proxy versus a portfolio demo goal; lower is better only within service guardrails.",
            "type": "line",
            "dataset": "aht_trend",
            "sourceId": "call_analysis",
            "xAxisTitle": "Call sequence",
            "yAxisTitle": "Seconds",
            "valueFormat": "number",
            "encodings": {
                "x": {"field": "call_number", "type": "ordinal", "label": "Call sequence"},
                "y": {"field": "value", "type": "quantitative", "label": "Seconds", "format": "number"},
                "color": {"field": "series", "type": "nominal", "label": "Series"},
                "tooltip": [{"field": "call_id", "type": "text", "label": "Call ID"}],
            },
            "layout": "half",
        },
        {
            "id": "risk_by_call",
            "title": "Heuristic conversation risk by call sequence",
            "subtitle": "Uncalibrated proxy with the rubric's medium-risk threshold; it is not an outcome score.",
            "type": "line",
            "dataset": "risk_trend",
            "sourceId": "call_analysis",
            "xAxisTitle": "Call sequence",
            "yAxisTitle": "Risk points",
            "valueFormat": "number",
            "encodings": {
                "x": {"field": "call_number", "type": "ordinal", "label": "Call sequence"},
                "y": {"field": "value", "type": "quantitative", "label": "Risk points", "format": "number"},
                "color": {"field": "series", "type": "nominal", "label": "Series"},
                "tooltip": [{"field": "call_id", "type": "text", "label": "Call ID"}],
            },
            "layout": "half",
        },
        {
            "id": "synthetic_quality_by_call",
            "title": "Synthetic quality KPI demo by call sequence",
            "subtitle": "UI fixtures only: these values are neither observed outcomes nor model predictions.",
            "type": "line",
            "dataset": "quality_demo_trend",
            "sourceId": "synthetic_business_kpis",
            "xAxisTitle": "Call sequence",
            "yAxisTitle": "Synthetic rate",
            "valueFormat": "percent",
            "encodings": {
                "x": {"field": "call_number", "type": "ordinal", "label": "Call sequence"},
                "y": {"field": "value", "type": "quantitative", "label": "Synthetic rate", "format": "percent"},
                "color": {"field": "series", "type": "nominal", "label": "Synthetic KPI"},
                "tooltip": [{"field": "call_id", "type": "text", "label": "Call ID"}],
            },
            "layout": "half",
        },
        {
            "id": "behavior_coverage",
            "title": "Detected service behaviors",
            "subtitle": "Share of calls with at least one rule-based behavior match versus portfolio coaching benchmarks.",
            "type": "bar",
            "dataset": "behavior_rates",
            "sourceId": "call_analysis",
            "xAxisTitle": "Behavior",
            "yAxisTitle": "Call rate",
            "valueFormat": "percent",
            "encodings": {
                "x": {"field": "behavior", "type": "nominal", "label": "Behavior"},
                "y": {"field": "value", "type": "quantitative", "label": "Call rate", "format": "percent"},
                "color": {"field": "series", "type": "nominal", "label": "Series"},
            },
            "layout": "half",
        },
    ]

    tables = [
        {
            "id": "focus_table",
            "title": "Today's Focus",
            "subtitle": "One evidence-backed next action for the selected agent and simulated shift view.",
            "dataset": "todays_focus",
            "sourceId": "dashboard_rules",
            "defaultSort": {"field": "focus_area", "direction": "asc"},
            "density": "spacious",
            "layout": "full",
            "columns": [
                {"field": "focus_area", "label": "Focus", "type": "text"},
                {"field": "why", "label": "Why now", "type": "text"},
                {"field": "recommended_action", "label": "Next action", "type": "text"},
                {"field": "guardrail", "label": "Guardrail", "type": "text"},
                {"field": "evidence_type", "label": "Evidence type", "type": "text"},
                {"field": "recap", "label": "Daily recap", "type": "text"},
            ],
        },
        {
            "id": "kpi_detail",
            "title": "My Performance - goal and projection detail",
            "subtitle": "Every KPI shows source type and freshness; demo outcomes remain visibly separated.",
            "dataset": "kpi_status",
            "sourceId": "dashboard_rules",
            "defaultSort": {"field": "metric", "direction": "asc"},
            "density": "dense",
            "layout": "full",
            "columns": [
                {"field": "metric", "label": "KPI", "type": "text"},
                {"field": "current", "label": "Current", "type": "text"},
                {"field": "goal", "label": "Goal", "type": "text"},
                {"field": "trend", "label": "Trend", "type": "text"},
                {"field": "projection", "label": "Projection", "type": "text"},
                {"field": "status", "label": "Status", "type": "text"},
                {"field": "recommended_action", "label": "Recommended action", "type": "text"},
                {"field": "source_type", "label": "Source type", "type": "text"},
                {"field": "freshness", "label": "Freshness", "type": "text"},
            ],
        },
        {
            "id": "call_highlights_table",
            "title": "Call highlights",
            "subtitle": "Heuristic selections with reason codes and turn-level evidence references.",
            "dataset": "call_highlights",
            "sourceId": "dashboard_rules",
            "defaultSort": {"field": "highlight", "direction": "asc"},
            "density": "dense",
            "layout": "full",
            "columns": [
                {"field": "highlight", "label": "Selection", "type": "text"},
                {"field": "call_number", "label": "Call #", "format": "number"},
                {"field": "call_id", "label": "Call ID", "type": "text"},
                {"field": "heuristic_risk_score", "label": "Risk proxy", "format": "number"},
                {"field": "estimated_aht_sec", "label": "Est. AHT sec", "format": "number"},
                {"field": "reason", "label": "Rubric reasons", "type": "text"},
                {"field": "evidence", "label": "Evidence", "type": "text"},
            ],
        },
    ]

    manifest = {
        "version": 1,
        "surface": "dashboard",
        "title": "Agent KPI Performance Tracker - Phase 2 MVP",
        "description": (
            "Portfolio dashboard combining analyzed call signals, explicit proxies, and "
            "clearly labeled synthetic business KPI fixtures."
        ),
        "generatedAt": generated_at,
        "filters": [
            {
                "id": "agent",
                "label": "Agent",
                "dataset": "kpi_summary",
                "field": "agent_label",
                "defaultValue": default_agent,
                "includeAll": False,
                "targets": filter_targets(dataset_names, "agent_label"),
            },
            {
                "id": "shift_view",
                "label": "Shift view",
                "dataset": "kpi_summary",
                "field": "stage",
                "defaultValue": default_stage,
                "includeAll": False,
                "targets": filter_targets(dataset_names, "stage"),
            },
        ],
        "cards": cards,
        "charts": charts,
        "tables": tables,
        "sources": sources,
        "blocks": [
            {
                "id": "demo_boundary",
                "type": "markdown",
                "body": (
                    "## Portfolio demo boundary\n\n"
                    "Shift views simulate progress using call sequence. CSAT, QA, NPS, and "
                    "Five Stars are synthetic UI fixtures. Estimated AHT and conversation risk "
                    "are derived proxies, not official workforce or customer outcomes."
                ),
            },
            {"id": "focus", "type": "table", "tableId": "focus_table", "layout": "full"},
            {
                "id": "my_performance",
                "type": "metric-strip",
                "cardIds": [card["id"] for card in cards],
            },
            {"id": "aht_chart", "type": "chart", "chartId": "aht_by_call", "layout": "half"},
            {"id": "risk_chart", "type": "chart", "chartId": "risk_by_call", "layout": "half"},
            {
                "id": "quality_demo_chart",
                "type": "chart",
                "chartId": "synthetic_quality_by_call",
                "layout": "half",
            },
            {
                "id": "behavior_chart",
                "type": "chart",
                "chartId": "behavior_coverage",
                "layout": "half",
            },
            {"id": "kpi_detail_block", "type": "table", "tableId": "kpi_detail", "layout": "full"},
            {
                "id": "call_highlights_block",
                "type": "table",
                "tableId": "call_highlights_table",
                "layout": "full",
            },
            {
                "id": "limitations",
                "type": "markdown",
                "body": (
                    "## How to read this MVP\n\n"
                    "Use analyzed signals for coaching evidence, not employee discipline. "
                    "Replace synthetic KPI fixtures with governed business feeds before any "
                    "operational use. Goal values are portfolio assumptions and can be customized "
                    "in `config/demo_kpi_targets.json`."
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
            "manifestPath": "dashboard/artifact.json",
            "snapshotPath": "dashboard/artifact.json",
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
    calls = normalize_calls(read_calls_via_sqlite(args.input))
    validate_input(calls)
    config = load_config(args.config)
    artifact = build_artifact(calls, config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"Wrote {args.output} with {len(calls)} calls, "
        f"{len(artifact['snapshot']['datasets']['kpi_summary'])} agent-stage KPI rows, "
        "and explicit synthetic-demo provenance."
    )


if __name__ == "__main__":
    main()
