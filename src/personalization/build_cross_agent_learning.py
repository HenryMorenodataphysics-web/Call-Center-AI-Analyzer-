"""Build anonymized context-matched coaching candidates for Phase 6."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .build_agent_memory import read_calls, read_json, source_context


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CALLS = PROJECT_ROOT / "data" / "final_outputs" / "all_calls_summary.csv"
DEFAULT_STAGES = PROJECT_ROOT / "config" / "demo_kpi_targets.json"
DEFAULT_CONTRACT = PROJECT_ROOT / "config" / "cross_agent_learning_contract_v1.json"
DEFAULT_ARTIFACT = PROJECT_ROOT / "dashboard" / "cross_agent_learning_artifact.json"


def integer(row: dict[str, Any], field: str) -> int:
    return int(float(row.get(field, 0) or 0))


def stage_calls(
    calls: list[dict[str, Any]], stage: dict[str, Any]
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in calls:
        grouped[str(row["agent_id"])].append(row)
    selected: list[dict[str, Any]] = []
    for agent_id in sorted(grouped):
        ordered = sorted(
            grouped[agent_id], key=lambda row: integer(row, "agent_call_number")
        )
        selected.extend(ordered[: min(int(stage["calls"]), len(ordered))])
    return selected


def build_stage_suggestions(
    calls: list[dict[str, Any]],
    stage: dict[str, Any],
    contract: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected = stage_calls(calls, stage)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in selected:
        context = source_context(str(row["call_id"]))
        grouped[(context["language_market"], context["source_domain"])].append(row)

    thresholds = contract["thresholds"]
    context_profiles: list[dict[str, Any]] = []
    suggestions: list[dict[str, Any]] = []
    for (language_market, source_domain), rows in sorted(grouped.items()):
        context_agents = {str(row["agent_id"]) for row in rows}
        eligible = (
            len(rows) >= int(thresholds["minimum_context_calls"])
            and len(context_agents) >= int(thresholds["minimum_context_agents"])
        )
        context_profiles.append(
            {
                "stage_id": stage["id"],
                "stage": stage["label"],
                "language_market": language_market,
                "source_domain": source_domain,
                "context_status": "dataset_proxy_not_approved_business_type",
                "calls_analyzed": len(rows),
                "anonymous_agents_represented": len(context_agents),
                "eligible": eligible,
                "eligibility_reason": (
                    "minimum context calls and anonymous-agent coverage satisfied"
                    if eligible
                    else "insufficient context calls or anonymous-agent coverage"
                ),
            }
        )
        if not eligible:
            continue

        candidates: list[dict[str, Any]] = []
        for behavior in contract["behaviors"]:
            detected = [
                row
                for row in rows
                if integer(row, str(behavior["source_field"])) > 0
            ]
            detected_agents = {str(row["agent_id"]) for row in detected}
            if (
                len(detected) < int(thresholds["minimum_behavior_calls"])
                or len(detected_agents) < int(thresholds["minimum_behavior_agents"])
            ):
                continue
            evidence = sorted(
                detected,
                key=lambda row: (
                    -integer(row, str(behavior["source_field"])),
                    str(row["call_id"]),
                ),
            )[: int(thresholds["maximum_evidence_calls"])]
            candidates.append(
                {
                    "suggestion_id": (
                        f"{stage['id']}:{language_market}:{source_domain}:"
                        f"{behavior['id']}"
                    ),
                    "stage_id": stage["id"],
                    "stage": stage["label"],
                    "stage_label": stage["label"],
                    "language_market": language_market,
                    "source_domain": source_domain,
                    "context_status": "dataset_proxy_not_approved_business_type",
                    "context_calls": len(rows),
                    "context_anonymous_agents": len(context_agents),
                    "behavior_id": behavior["id"],
                    "behavior_label": behavior["label"],
                    "behavior_calls": len(detected),
                    "behavior_anonymous_agents": len(detected_agents),
                    "behavior_call_coverage": round(len(detected) / len(rows), 4),
                    "sample_confidence": "low",
                    "evidence_basis": "recurring_observed_behavior_only",
                    "outcome_association_available": False,
                    "peer_identity_hidden": True,
                    "coaching_action": behavior["coaching_action"],
                    "transferable_suggestion": (
                        f"In the dataset-derived {source_domain} context, "
                        f"{behavior['label']} appeared in {len(detected)} of {len(rows)} "
                        f"calls across {len(detected_agents)} anonymous agents. "
                        f"Technique candidate: {behavior['coaching_action']}"
                    ),
                    "supporting_call_ids": [str(row["call_id"]) for row in evidence],
                    "interpretation_limit": (
                        "Recurring portfolio evidence only; peer identity is hidden, the "
                        "context is not an approved business call type, and no governed "
                        "outcome association or causal effect is available."
                    ),
                }
            )
        candidates.sort(
            key=lambda item: (
                -item["behavior_anonymous_agents"],
                -item["behavior_call_coverage"],
                item["behavior_label"],
            )
        )
        suggestions.extend(
            candidates[: int(thresholds["maximum_suggestions_per_context"])]
        )
    return context_profiles, suggestions


def build_artifact(
    calls: list[dict[str, Any]],
    stage_config: dict[str, Any],
    contract: dict[str, Any],
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat()
    contexts: list[dict[str, Any]] = []
    suggestions: list[dict[str, Any]] = []
    for stage in stage_config["stages"]:
        stage_contexts, stage_suggestions = build_stage_suggestions(
            calls, stage, contract
        )
        contexts.extend(stage_contexts)
        suggestions.extend(stage_suggestions)
    return {
        "schemaVersion": "cross_agent_learning_v1",
        "generatedAt": generated_at,
        "status": "portfolio_transferable_evidence_outcomes_blocked",
        "contractVersion": contract["contract_version"],
        "operationalOutcomeGate": {
            "status": "blocked",
            **contract["blocked_operational_gate"],
        },
        "sources": [
            {
                "path": "data/final_outputs/all_calls_summary.csv",
                "grain": "call",
                "role": "canonical behavior and call evidence",
            },
            {
                "path": "config/cross_agent_learning_contract_v1.json",
                "grain": "contract",
                "role": "matching thresholds, techniques, and guardrails",
            },
        ],
        "limitations": contract["guardrails"],
        "snapshot": {
            "status": "portfolio_demo",
            "population": {
                "calls": len(calls),
                "stages": len(stage_config["stages"]),
                "context_rows": len(contexts),
                "eligible_context_rows": sum(row["eligible"] for row in contexts),
                "suggestions": len(suggestions),
            },
            "datasets": {
                "context_profiles": contexts,
                "cross_agent_suggestions": suggestions,
            },
        },
    }


class CrossAgentLearningRepository:
    """Read-only access to the checked-in Phase 6 artifact."""

    def __init__(self, artifact_path: Path = DEFAULT_ARTIFACT):
        self.artifact_path = artifact_path
        self.artifact = read_json(artifact_path)

    def suggestions(self, stage_id: str) -> list[dict[str, Any]]:
        rows = self.artifact["snapshot"]["datasets"]["cross_agent_suggestions"]
        return [row for row in rows if row["stage_id"] == stage_id]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calls", type=Path, default=DEFAULT_CALLS)
    parser.add_argument("--stages", type=Path, default=DEFAULT_STAGES)
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
        args.generated_at,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    population = artifact["snapshot"]["population"]
    print(
        "Cross-agent learning: "
        f"{population['eligible_context_rows']} eligible context-stage rows, "
        f"{population['suggestions']} anonymized suggestions"
    )
    print("Operational outcome gate: BLOCKED")
    print(f"Artifact: {args.output.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
