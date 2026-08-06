"""Build the versioned Agent Memory v1 artifact from canonical call summaries."""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CALLS = PROJECT_ROOT / "data" / "final_outputs" / "all_calls_summary.csv"
DEFAULT_STAGE_CONFIG = PROJECT_ROOT / "config" / "demo_kpi_targets.json"
DEFAULT_CONTRACT = PROJECT_ROOT / "config" / "agent_memory_contract_v1.json"
DEFAULT_ARTIFACT = PROJECT_ROOT / "dashboard" / "agent_memory_artifact.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_calls(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("Agent Memory requires at least one canonical call summary")
    call_ids = [row["call_id"] for row in rows]
    if len(call_ids) != len(set(call_ids)):
        raise ValueError("Agent Memory source contains duplicate call IDs")
    return rows


def integer(row: dict[str, str], field: str) -> int:
    return int(float(row.get(field, 0) or 0))


def number(row: dict[str, str], field: str) -> float:
    return float(row.get(field, 0) or 0)


def source_context(call_id: str) -> dict[str, str]:
    match = re.fullmatch(r"([a-z]{2})_([A-Z]{2})_(.+)_([0-9]+)", call_id)
    if not match:
        return {
            "language_market": "unknown",
            "source_domain": "unknown",
            "context_source": "unavailable",
        }
    return {
        "language_market": f"{match.group(1)}-{match.group(2)}",
        "source_domain": match.group(3),
        "context_source": "dataset_call_id_pattern",
    }


def sample_confidence(call_count: int, contract: dict[str, Any]) -> str:
    thresholds = contract["sample_confidence_thresholds"]
    if call_count >= int(thresholds["high_min_calls"]):
        return "high"
    if call_count >= int(thresholds["moderate_min_calls"]):
        return "moderate"
    return "low"


def behavior_patterns(
    calls: list[dict[str, str]], contract: dict[str, Any]
) -> list[dict[str, Any]]:
    patterns: list[dict[str, Any]] = []
    total = len(calls)
    for behavior in contract["behaviors"]:
        field = behavior["source_field"]
        detected = [row for row in calls if integer(row, field) > 0]
        missing = [row for row in calls if integer(row, field) == 0]
        coverage = len(detected) / total
        target = float(behavior["portfolio_benchmark"])
        strongest = sorted(
            detected,
            key=lambda row: (-integer(row, field), integer(row, "agent_call_number")),
        )
        patterns.append(
            {
                "behavior_id": behavior["id"],
                "label": behavior["label"],
                "source_field": field,
                "calls_detected": len(detected),
                "calls_missing": len(missing),
                "call_coverage": round(coverage, 4),
                "portfolio_benchmark": target,
                "benchmark_gap": round(coverage - target, 4),
                "benchmark_status": (
                    "meets_portfolio_benchmark"
                    if coverage >= target
                    else "below_portfolio_benchmark"
                ),
                "supporting_call_ids": [row["call_id"] for row in strongest[:3]],
                "missing_call_ids": [
                    row["call_id"]
                    for row in sorted(
                        missing, key=lambda row: integer(row, "agent_call_number")
                    )[:3]
                ],
            }
        )
    return patterns


def risk_profile(calls: list[dict[str, str]]) -> dict[str, Any]:
    counts = {level: 0 for level in ("low", "medium", "high")}
    scores: list[float] = []
    manual_review: list[str] = []
    for row in calls:
        level = row.get("conversation_risk_level", "unknown").casefold()
        if level in counts:
            counts[level] += 1
        scores.append(number(row, "conversation_risk_score"))
        if row.get("needs_manual_review", "").casefold() == "true":
            manual_review.append(row["call_id"])
    total = len(calls)
    return {
        "score_type": "uncalibrated_heuristic_proxy",
        "calibrated": False,
        "average_score": round(sum(scores) / total, 2),
        "median_score": round(statistics.median(scores), 2),
        "low_calls": counts["low"],
        "medium_calls": counts["medium"],
        "high_calls": counts["high"],
        "low_share": round(counts["low"] / total, 4),
        "elevated_share": round((counts["medium"] + counts["high"]) / total, 4),
        "manual_review_call_ids": manual_review,
    }


def context_profiles(
    calls: list[dict[str, str]], contract: dict[str, Any]
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in calls:
        grouped[source_context(row["call_id"])["source_domain"]].append(row)

    profiles: list[dict[str, Any]] = []
    for domain, rows in sorted(grouped.items()):
        patterns = behavior_patterns(rows, contract)
        strongest = sorted(patterns, key=lambda item: (-item["call_coverage"], item["label"]))[0]
        opportunity = sorted(patterns, key=lambda item: (item["benchmark_gap"], item["label"]))[0]
        profiles.append(
            {
                "source_domain": domain,
                "context_source": source_context(rows[0]["call_id"])["context_source"],
                "calls_analyzed": len(rows),
                "sample_confidence": sample_confidence(len(rows), contract),
                "risk_proxy": risk_profile(rows),
                "strongest_observed_behavior": {
                    "behavior_id": strongest["behavior_id"],
                    "label": strongest["label"],
                    "call_coverage": strongest["call_coverage"],
                },
                "largest_portfolio_benchmark_gap": {
                    "behavior_id": opportunity["behavior_id"],
                    "label": opportunity["label"],
                    "benchmark_gap": opportunity["benchmark_gap"],
                },
                "call_ids": [
                    row["call_id"]
                    for row in sorted(rows, key=lambda row: integer(row, "agent_call_number"))
                ],
                "interpretation_limit": (
                    "Dataset-derived source domain, not an approved business call type; "
                    "the sample is too small for a stable contextual conclusion."
                ),
            }
        )
    return profiles


def selected_patterns(
    patterns: list[dict[str, Any]], contract: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    minimum = int(contract["pattern_rules"]["minimum_evidence_calls"])
    maximum = int(contract["pattern_rules"]["maximum_patterns_per_group"])
    strengths = [
        pattern
        for pattern in patterns
        if pattern["benchmark_status"] == "meets_portfolio_benchmark"
        and pattern["calls_detected"] >= minimum
    ]
    opportunities = [
        pattern
        for pattern in patterns
        if pattern["benchmark_status"] == "below_portfolio_benchmark"
        and pattern["calls_missing"] >= minimum
    ]
    strengths.sort(key=lambda item: (-item["benchmark_gap"], -item["call_coverage"], item["label"]))
    opportunities.sort(key=lambda item: (item["benchmark_gap"], item["label"]))
    keep = (
        "behavior_id",
        "label",
        "call_coverage",
        "portfolio_benchmark",
        "benchmark_gap",
        "supporting_call_ids",
        "missing_call_ids",
    )
    return (
        [{key: item[key] for key in keep} for item in strengths[:maximum]],
        [{key: item[key] for key in keep} for item in opportunities[:maximum]],
    )


def structured_summary(
    calls: list[dict[str, str]],
    confidence: str,
    risk: dict[str, Any],
    strengths: list[dict[str, Any]],
    opportunities: list[dict[str, Any]],
) -> dict[str, str]:
    if strengths:
        strength_text = ", ".join(
            f"{item['label']} ({item['call_coverage']:.0%} call coverage)"
            for item in strengths
        )
    else:
        strength_text = "No behavior yet meets its portfolio coaching benchmark"
    if opportunities:
        opportunity_text = ", ".join(
            f"{item['label']} ({item['call_coverage']:.0%} call coverage)"
            for item in opportunities
        )
    else:
        opportunity_text = "No benchmark gap met the evidence threshold"
    return {
        "headline": (
            f"Initial memory covers {len(calls)} calls with {confidence} sample confidence."
        ),
        "risk_context": (
            f"The uncalibrated review proxy is low for {risk['low_calls']} calls, "
            f"medium for {risk['medium_calls']}, and high for {risk['high_calls']}."
        ),
        "observed_strengths": strength_text + ".",
        "coaching_opportunities": opportunity_text + ".",
        "history_limit": (
            "This is an accumulated portfolio-sequence snapshot, not a dated "
            "longitudinal employment record."
        ),
    }


def build_memory_row(
    calls: list[dict[str, str]],
    stage: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    ordered = sorted(calls, key=lambda row: integer(row, "agent_call_number"))
    selected = ordered[: min(int(stage["calls"]), len(ordered))]
    patterns = behavior_patterns(selected, contract)
    strengths, opportunities = selected_patterns(patterns, contract)
    risk = risk_profile(selected)
    confidence = sample_confidence(len(selected), contract)
    contexts = [source_context(row["call_id"]) for row in selected]
    return {
        "business_id": contract["default_business_id"],
        "business_profile_status": "planned_not_resolved",
        "agent_id": selected[0]["agent_id"],
        "agent_name": selected[0]["agent_name"],
        "agent_label": f"{selected[0]['agent_name']} - {selected[0]['agent_id']}",
        "stage_id": stage["id"],
        "stage_label": stage["label"],
        "memory_version": contract["contract_version"],
        "memory_scope": "cumulative_portfolio_sequence",
        "calls_analyzed": len(selected),
        "first_agent_call_number": integer(selected[0], "agent_call_number"),
        "last_agent_call_number": integer(selected[-1], "agent_call_number"),
        "sample_confidence": confidence,
        "language_markets": sorted({item["language_market"] for item in contexts}),
        "risk_proxy_profile": risk,
        "behavior_patterns": patterns,
        "observed_strengths": strengths,
        "coaching_opportunities": opportunities,
        "source_domain_profiles": context_profiles(selected, contract),
        "longitudinal_status": {
            "multiple_dated_snapshots_available": False,
            "status": "initial_snapshot_only",
            "reason": (
                "The source contains call sequence but no governed event timestamp "
                "or prior Agent Memory snapshots."
            ),
        },
        "structured_summary": structured_summary(
            selected, confidence, risk, strengths, opportunities
        ),
        "supporting_call_ids": [row["call_id"] for row in selected],
    }


def build_artifact(
    calls: list[dict[str, str]],
    stage_config: dict[str, Any],
    contract: dict[str, Any],
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in calls:
        grouped[row["agent_id"]].append(row)

    memories = [
        build_memory_row(grouped[agent_id], stage, contract)
        for agent_id in sorted(grouped)
        for stage in stage_config["stages"]
    ]
    end_rows = [row for row in memories if row["stage_id"] == "end"]
    return {
        "schemaVersion": "agent_memory_v1",
        "generatedAt": generated_at,
        "status": "portfolio_initial_memory",
        "businessContext": {
            "business_id": contract["default_business_id"],
            "profile_status": "planned_not_resolved",
        },
        "sources": [
            {
                "path": "data/final_outputs/all_calls_summary.csv",
                "grain": "call",
                "role": "canonical analyzed call evidence",
            },
            {
                "path": "config/demo_kpi_targets.json",
                "grain": "portfolio configuration",
                "role": "stage definitions and coaching benchmarks",
            },
            {
                "path": "config/agent_memory_contract_v1.json",
                "grain": "contract",
                "role": "memory thresholds and guardrails",
            },
        ],
        "limitations": contract["guardrails"],
        "snapshot": {
            "status": "portfolio_demo",
            "grain": "agent_stage",
            "population": {
                "agents": len(grouped),
                "calls": len(calls),
                "memory_rows": len(memories),
                "end_stage_calls": sum(row["calls_analyzed"] for row in end_rows),
            },
            "datasets": {"agent_memories": memories},
        },
    }


class AgentMemoryRepository:
    """Read-only access to the checked-in Agent Memory artifact."""

    def __init__(self, artifact_path: Path = DEFAULT_ARTIFACT):
        self.artifact_path = artifact_path
        self.artifact = read_json(artifact_path)
        rows = self.artifact.get("snapshot", {}).get("datasets", {}).get(
            "agent_memories", []
        )
        self._rows = {
            (row["agent_id"], row["stage_id"]): row
            for row in rows
        }
        if len(self._rows) != len(rows):
            raise ValueError("Agent Memory artifact contains duplicate agent-stage rows")

    def summary(self, agent_id: str, stage_id: str) -> dict[str, Any]:
        try:
            return self._rows[(agent_id, stage_id)]
        except KeyError as exc:
            raise ValueError(
                f"Agent Memory is unavailable for {agent_id} in stage {stage_id}"
            ) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calls", type=Path, default=DEFAULT_CALLS)
    parser.add_argument("--stages", type=Path, default=DEFAULT_STAGE_CONFIG)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--generated-at")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifact = build_artifact(
        read_calls(args.calls),
        read_json(args.stages),
        read_json(args.contract),
        generated_at=args.generated_at,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    population = artifact["snapshot"]["population"]
    print(
        "Agent Memory v1: "
        f"{population['agents']} agents, {population['calls']} calls, "
        f"{population['memory_rows']} cumulative memory rows"
    )
    print(f"Artifact: {args.output.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
