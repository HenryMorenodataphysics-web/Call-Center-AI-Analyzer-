"""Evaluate Phase 6 cross-agent learning against fixed portfolio gates."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT = PROJECT_ROOT / "dashboard" / "cross_agent_learning_artifact.json"
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "cross_agent_learning_evaluation_v1.json"
DEFAULT_CONTRACT = PROJECT_ROOT / "config" / "cross_agent_learning_contract_v1.json"
DEFAULT_CALLS = PROJECT_ROOT / "data" / "final_outputs" / "all_calls_summary.csv"
DEFAULT_RESULTS = PROJECT_ROOT / "data" / "validation" / "cross_agent_learning_evaluation_results.json"
DEFAULT_REPORT = PROJECT_ROOT / "reports" / "cross_agent_learning_evaluation_report.md"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_call_ids(path: Path) -> set[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {row["call_id"] for row in csv.DictReader(handle)}


def rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def evaluate(
    artifact: dict[str, Any],
    config: dict[str, Any],
    contract: dict[str, Any],
    call_ids: set[str],
) -> dict[str, Any]:
    datasets = artifact["snapshot"]["datasets"]
    contexts = datasets["context_profiles"]
    suggestions = datasets["cross_agent_suggestions"]
    end_contexts = [row for row in contexts if row["stage_id"] == "end" and row["eligible"]]
    end_suggestions = [row for row in suggestions if row["stage_id"] == "end"]
    thresholds = contract["thresholds"]

    evidence_ok = sum(
        bool(row["supporting_call_ids"])
        and set(row["supporting_call_ids"]) <= call_ids
        for row in suggestions
    )
    anonymity_ok = sum(
        row["peer_identity_hidden"]
        and row["context_anonymous_agents"] >= 2
        and row["behavior_anonymous_agents"] >= 2
        and not ({"agent_id", "agent_name", "agent_label"} & set(row))
        for row in suggestions
    )
    threshold_ok = sum(
        row["context_calls"] >= thresholds["minimum_context_calls"]
        and row["context_anonymous_agents"] >= thresholds["minimum_context_agents"]
        and row["behavior_calls"] >= thresholds["minimum_behavior_calls"]
        and row["behavior_anonymous_agents"] >= thresholds["minimum_behavior_agents"]
        for row in suggestions
    )
    proxy_ok = sum(
        row["context_status"] == "dataset_proxy_not_approved_business_type"
        for row in suggestions
    )
    noncausal_ok = sum(
        row["evidence_basis"] == "recurring_observed_behavior_only"
        and "causal effect" in row["interpretation_limit"].casefold()
        for row in suggestions
    )
    outcome_block_ok = sum(
        row["outcome_association_available"] is False for row in suggestions
    )
    early_stage_suggestions = [
        row for row in suggestions if row["stage_id"] in {"start", "live"}
    ]

    metrics = {
        "end_contexts": len(end_contexts),
        "end_suggestions": len(end_suggestions),
        "distinct_behaviors": len({row["behavior_id"] for row in end_suggestions}),
        "evidence_rate": rate(evidence_ok, len(suggestions)),
        "anonymity_rate": rate(anonymity_ok, len(suggestions)),
        "sample_threshold_rate": rate(threshold_ok, len(suggestions)),
        "context_proxy_label_rate": rate(proxy_ok, len(suggestions)),
        "noncausal_boundary_rate": rate(noncausal_ok, len(suggestions)),
        "outcome_block_rate": rate(outcome_block_ok, len(suggestions)),
        "no_early_stage_leakage_rate": 1.0 if not early_stage_suggestions else 0.0,
    }
    gate_map = {
        "minimum_end_contexts": "end_contexts",
        "minimum_end_suggestions": "end_suggestions",
        "minimum_distinct_behaviors": "distinct_behaviors",
        "required_evidence_rate": "evidence_rate",
        "required_anonymity_rate": "anonymity_rate",
        "required_sample_threshold_rate": "sample_threshold_rate",
        "required_context_proxy_label_rate": "context_proxy_label_rate",
        "required_noncausal_boundary_rate": "noncausal_boundary_rate",
        "required_outcome_block_rate": "outcome_block_rate",
        "required_no_early_stage_leakage_rate": "no_early_stage_leakage_rate",
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
    status = "pass" if all(item["status"] == "pass" for item in checks) else "fail"
    return {
        "evaluation_version": config["evaluation_version"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "portfolio_gate": {"status": status, "checks": checks},
        "operational_outcome_gate": {
            "status": "blocked",
            **config["blocked_operational_gate"],
            "interpretation": (
                "Portfolio recurrence supports reviewable technique candidates, but no "
                "governed outcome association or causal effect can be evaluated."
            ),
        },
        "population": {
            "context_rows": len(contexts),
            "eligible_end_contexts": len(end_contexts),
            "suggestions": len(suggestions),
        },
        "metrics": metrics,
    }


def markdown_report(result: dict[str, Any]) -> str:
    lines = [
        "# Phase 6 cross-agent learning evaluation",
        "",
        f"- Portfolio status: **{result['status'].upper()}**",
        "- Operational outcome status: **BLOCKED** "
        "(`NO_GOVERNED_OUTCOMES_FOR_CROSS_AGENT_LEARNING`)",
        f"- Population: {result['population']['eligible_end_contexts']} eligible end contexts, "
        f"{result['population']['suggestions']} anonymous suggestions",
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
            "The bounded portfolio gate passes only for anonymous recurring techniques "
            "within an exact dataset-derived language-market and source-domain context. "
            "Every suggestion cites canonical calls and preserves its low-sample boundary.",
            "",
            "This does not identify a best agent or prove a best practice. Production outcome "
            "learning remains blocked until governed outcomes and approved context controls exist.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--calls", type=Path, default=DEFAULT_CALLS)
    parser.add_argument("--output", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = evaluate(
        read_json(args.artifact),
        read_json(args.config),
        read_json(args.contract),
        canonical_call_ids(args.calls),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    args.report.write_text(markdown_report(result), encoding="utf-8")
    print(f"Phase 6 portfolio cross-agent learning: {result['status'].upper()}")
    print(
        "Operational outcome gate: BLOCKED "
        "(NO_GOVERNED_OUTCOMES_FOR_CROSS_AGENT_LEARNING)"
    )
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
