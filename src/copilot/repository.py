"""Read-only access to dashboard artifacts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_PATH = PROJECT_ROOT / "dashboard" / "artifact.json"


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


class DashboardRepository:
    def __init__(self, artifact_path: Path = DEFAULT_ARTIFACT_PATH):
        self.artifact_path = artifact_path
        self.artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        self.datasets: dict[str, list[dict[str, Any]]] = self.artifact["snapshot"][
            "datasets"
        ]
        summary = self.datasets["kpi_summary"]
        self._agents: dict[str, dict[str, str]] = {}
        for row in summary:
            self._agents[row["agent_id"]] = {
                "agent_id": row["agent_id"],
                "agent_name": row["agent_name"],
                "agent_label": row["agent_label"],
            }
        self._stage_labels = {
            row["stage_id"]: row["stage"] for row in summary if row["agent_id"] == "Agent_001"
        }

    @property
    def snapshot_generated_at(self) -> str:
        return self.artifact["snapshot"]["generatedAt"]

    def list_agents(self) -> list[dict[str, str]]:
        return [self._agents[key] for key in sorted(self._agents)]

    def resolve_agent(self, value: str) -> dict[str, str]:
        if value in self._agents:
            return self._agents[value]
        needle = normalize(value)
        matches = [
            agent
            for agent in self._agents.values()
            if needle
            and (
                needle == normalize(agent["agent_name"])
                or needle == normalize(agent["agent_label"])
                or needle in normalize(agent["agent_label"])
            )
        ]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise ValueError(f"Unknown agent: {value}")
        raise ValueError(f"Ambiguous agent: {value}")

    def validate_stage(self, stage_id: str) -> str:
        aliases = {
            "start": "start",
            "inicio": "start",
            "live": "live",
            "during": "live",
            "durante": "live",
            "end": "end",
            "final": "end",
        }
        canonical = aliases.get(normalize(stage_id), normalize(stage_id))
        if canonical not in self._stage_labels:
            raise ValueError(f"Unknown shift view: {stage_id}")
        return canonical

    def rows(self, dataset: str, agent_id: str, stage_id: str) -> list[dict[str, Any]]:
        if dataset not in self.datasets:
            raise KeyError(f"Unknown dashboard dataset: {dataset}")
        return [
            row
            for row in self.datasets[dataset]
            if row.get("agent_id") == agent_id and row.get("stage_id") == stage_id
        ]
