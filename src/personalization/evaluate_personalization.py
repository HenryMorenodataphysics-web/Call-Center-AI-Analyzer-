"""Evaluate Agent Memory personalization against fixed Phase 5 portfolio gates."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT = PROJECT_ROOT / "dashboard" / "agent_memory_artifact.json"
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "personalization_evaluation_v1.json"
DEFAULT_CALLS = PROJECT_ROOT / "data" / "final_outputs" / "all_calls_summary.csv"
DEFAULT_RESULTS = PROJECT_ROOT / "data" / "validation" / "personalization_evaluation_results.json"
DEFAULT_REPORT = PROJECT_ROOT / "reports" / "personalization_evaluation_report.md"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_call_ids(path: Path) -> set[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {row["call_id"] for row in csv.DictReader(handle)}


def rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def evaluate(
    artifact: dict[str, Any], config: dict[str, Any], call_ids: set[str]
) -> dict[str, Any]:
    rows = artifact["snapshot"]["datasets"]["agent_memories"]
    end_rows = [row for row in rows if row["stage_id"] == "end"]
    later_rows = [row for row in rows if row["stage_id"] != "start"]
    by_agent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_agent[row["agent_id"]].append(row)

    end_focuses = {
        row["personalization"]["recommendation"]["focus_behavior_id"]
        for row in end_rows
    }
    agents_with_focus_change = sum(
        len(
            {
                row["personalization"]["recommendation"]["focus_behavior_id"]
                for row in agent_rows
            }
        )
        > 1
        for agent_rows in by_agent.values()
    )
    distinct_end_recommendations = {
        row["personalization"]["recommendation"]["text"] for row in end_rows
    }

    recommendations = [row["personalization"]["recommendation"] for row in rows]
    evidence_ok = sum(
        bool(item["supporting_call_ids"])
        and set(item["supporting_call_ids"]) <= call_ids
        for item in recommendations
    )
    confidence_ok = sum(
        item["sample_confidence"] in {"low", "moderate", "high"}
        for item in recommendations
    )
    boundary_ok = sum(
        not row["personalization"]["time_window"]["governed_dates_available"]
        and "no governed dated history"
        in row["personalization"]["recommendation"]["interpretation_limit"].casefold()
        for row in rows
    )
    end_context_ok = sum(
        row["personalization"]["recommendation"]["selected_context"] is not None
        for row in end_rows
    )
    context_rows = [
        row
        for row in rows
        if row["personalization"]["recommendation"]["selected_context"] is not None
    ]
    context_proxy_ok = sum(
        row["personalization"]["recommendation"]["selected_context"]["context_status"]
        == "dataset_proxy_not_approved_business_type"
        for row in context_rows
    )
    prior_stage_ok = sum(
        row["personalization"]["self_history"]["previous_stage_id"] is not None
        and row["personalization"]["self_history"]["additional_calls_analyzed"] > 0
        and all(
            item["previous_call_coverage"] is not None
            for item in row["personalization"]["self_history"]["behavior_changes"]
        )
        for row in later_rows
    )

    metrics = {
        "distinct_end_focus_behaviors": len(end_focuses),
        "agent_stage_focus_change_rate": rate(agents_with_focus_change, len(by_agent)),
        "distinct_end_recommendation_rate": rate(
            len(distinct_end_recommendations), len(end_rows)
        ),
        "evidence_rate": rate(evidence_ok, len(rows)),
        "confidence_label_rate": rate(confidence_ok, len(rows)),
        "history_boundary_rate": rate(boundary_ok, len(rows)),
        "end_context_rate": rate(end_context_ok, len(end_rows)),
        "context_proxy_label_rate": rate(context_proxy_ok, len(context_rows)),
        "prior_stage_trend_rate": rate(prior_stage_ok, len(later_rows)),
    }
    gate_map = {
        "minimum_distinct_end_focus_behaviors": "distinct_end_focus_behaviors",
        "minimum_agent_stage_focus_change_rate": "agent_stage_focus_change_rate",
        "minimum_distinct_end_recommendation_rate": "distinct_end_recommendation_rate",
        "required_evidence_rate": "evidence_rate",
        "required_confidence_label_rate": "confidence_label_rate",
        "required_history_boundary_rate": "history_boundary_rate",
        "required_end_context_rate": "end_context_rate",
        "required_context_proxy_label_rate": "context_proxy_label_rate",
        "required_prior_stage_trend_rate": "prior_stage_trend_rate",
    }
    checks = []
    for gate_name, metric_name in gate_map.items():
        required = config["gates"][gate_name]
        observed = metrics[metric_name]
        checks.append(
            {
                "gate": gate_name,
                "metric": metric_name,
                "required": required,
                "observed": observed,
                "status": "pass" if observed >= required else "fail",
            }
        )

    gate_status = "pass" if all(item["status"] == "pass" for item in checks) else "fail"
    return {
        "evaluation_version": config["evaluation_version"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": gate_status,
        "portfolio_gate": {
            "status": gate_status,
            "checks": checks,
        },
        "operational_longitudinal_gate": {
            "status": "blocked",
            **config["blocked_operational_gate"],
            "interpretation": (
                "Portfolio call sequence supports auditable personalization, but it is not "
                "a governed dated employment history."
            ),
        },
        "population": {
            "agents": len(by_agent),
            "memory_rows": len(rows),
            "end_rows": len(end_rows),
        },
        "metrics": metrics,
    }


def markdown_report(result: dict[str, Any]) -> str:
    lines = [
        "# Phase 5 personalization evaluation",
        "",
        f"- Portfolio status: **{result['status'].upper()}**",
        "- Operational longitudinal status: **BLOCKED** (`NO_GOVERNED_DATED_HISTORY`)",
        f"- Population: {result['population']['agents']} agents, "
        f"{result['population']['memory_rows']} agent-stage memories",
        "",
        "## Completion gates",
        "",
        "| Gate | Observed | Required | Status |",
        "| --- | ---: | ---: | --- |",
    ]
    for item in result["portfolio_gate"]["checks"]:
        lines.append(
            f"| `{item['metric']}` | {item['observed']:.2f} | "
            f"{item['required']:.2f} | **{item['status'].upper()}** |"
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "Agent Memory now changes its focus using the selected agent's cumulative "
            "evidence, stage-to-stage behavior coverage, and an explicitly labeled "
            "dataset-derived context. Recommendations retain call citations and low-sample limits.",
            "",
            "This closes the deterministic portfolio personalization gate. Production "
            "longitudinal personalization remains blocked until governed timestamps, approved "
            "business call types, complexity, language/market, and workload context exist.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--calls", type=Path, default=DEFAULT_CALLS)
    parser.add_argument("--output", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = evaluate(
        read_json(args.artifact), read_json(args.config), canonical_call_ids(args.calls)
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    args.report.write_text(markdown_report(result), encoding="utf-8")
    print(f"Phase 5 portfolio personalization: {result['status'].upper()}")
    print("Operational longitudinal gate: BLOCKED (NO_GOVERNED_DATED_HISTORY)")
    print(f"Results: {args.output.relative_to(PROJECT_ROOT)}")
    print(f"Report: {args.report.relative_to(PROJECT_ROOT)}")
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
