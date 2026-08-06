#!/usr/bin/env python3
"""Build a synthetic-only survey representativeness artifact.

This module compares the risk-proxy mix of all analyzed calls with the subset
that received synthetic survey fixtures. It does not train a model, estimate a
real survey outcome, or convert the heuristic risk proxy into an agent score.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CALLS = PROJECT_ROOT / "data" / "final_outputs" / "all_calls_summary.csv"
DEFAULT_SURVEYS = (
    PROJECT_ROOT / "data" / "outcomes" / "fixtures" / "synthetic_surveys_normalized.csv"
)
DEFAULT_STAGE_CONFIG = PROJECT_ROOT / "config" / "demo_kpi_targets.json"
DEFAULT_ARTIFACT = PROJECT_ROOT / "dashboard" / "survey_representativeness_artifact.json"

RISK_LEVELS = ("low", "medium", "high")
ELEVATED_LEVELS = {"medium", "high"}
MIX_GAP_THRESHOLD = 0.20
AVERAGE_RISK_GAP_THRESHOLD = 5.0
MIN_SURVEYS_FOR_NON_LOW_CONFIDENCE = 5

REQUIRED_CALL_COLUMNS = {
    "call_id",
    "agent_id",
    "agent_name",
    "agent_call_number",
    "conversation_risk_score",
    "conversation_risk_level",
    "risk_score_type",
    "risk_score_calibrated",
}
REQUIRED_SURVEY_COLUMNS = {
    "call_id",
    "survey_received",
    "survey_positive",
    "survey_type",
    "is_synthetic",
    "source_system",
}


def _require_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {', '.join(missing)}")


def _is_true(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.casefold().isin({"1", "true", "yes"})


def _share(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def _mix_signal(
    surveys_received: int,
    elevated_share_gap: float | None,
    average_risk_gap: float | None,
) -> str:
    if not surveys_received:
        return "No synthetic surveys in this view"
    if elevated_share_gap is not None and elevated_share_gap >= MIX_GAP_THRESHOLD:
        return "Skewed toward higher review-priority calls"
    if elevated_share_gap is not None and elevated_share_gap <= -MIX_GAP_THRESHOLD:
        return "Skewed toward lower review-priority calls"
    if average_risk_gap is not None and average_risk_gap >= AVERAGE_RISK_GAP_THRESHOLD:
        return "Skewed toward higher review-priority calls"
    if average_risk_gap is not None and average_risk_gap <= -AVERAGE_RISK_GAP_THRESHOLD:
        return "Skewed toward lower review-priority calls"
    return "No large risk-mix gap detected"


def _confidence(surveys_received: int, synthetic_only: bool) -> tuple[str, str]:
    if synthetic_only:
        return (
            "Low",
            "The linked surveys are synthetic fixtures and cannot establish real customer experience.",
        )
    if surveys_received < MIN_SURVEYS_FOR_NON_LOW_CONFIDENCE:
        return "Low", f"Only {surveys_received} surveyed calls are available in this view."
    return "Exploratory", "Interpret with the call-mix and outcome-governance guardrails."


def _interpretation(row: dict[str, Any]) -> str:
    base = (
        f"{row['low_calls']} of {row['calls_analyzed']} analyzed calls "
        f"({row['low_share']:.0%}) have low heuristic review priority. "
    )
    if not row["surveys_received"]:
        return base + "No synthetic survey fixture is linked in this analysis window."
    survey_mix = (
        f"{row['surveyed_elevated_calls']} of {row['surveys_received']} surveyed fixture calls "
        f"({row['surveyed_elevated_share']:.0%}) are medium/high priority, compared with "
        f"{row['elevated_share']:.0%} across all calls. "
    )
    if row["representativeness_signal"].startswith("Skewed toward higher"):
        conclusion = (
            "The surveyed subset overrepresents calls with more review signals; do not "
            "generalize its survey results to the agent's full call profile."
        )
    elif row["representativeness_signal"].startswith("Skewed toward lower"):
        conclusion = (
            "The surveyed subset underrepresents calls with more review signals; it may "
            "present a more favorable mix than the agent's full call profile."
        )
    else:
        conclusion = (
            "No large risk-mix difference is detected, but the synthetic sample remains "
            "too small and artificial for a real performance conclusion."
        )
    return base + survey_mix + conclusion


def build_artifact(
    calls: pd.DataFrame,
    surveys: pd.DataFrame,
    stages: list[dict[str, Any]],
    generated_at: str | None = None,
) -> dict[str, Any]:
    _require_columns(calls, REQUIRED_CALL_COLUMNS, "Call summary")
    _require_columns(surveys, REQUIRED_SURVEY_COLUMNS, "Survey fixture")
    if calls["call_id"].duplicated().any():
        raise ValueError("Call summary contains duplicate call_id values")
    if surveys["call_id"].duplicated().any():
        raise ValueError("Survey fixture contains duplicate call_id values")
    unknown = sorted(set(surveys["call_id"]) - set(calls["call_id"]))
    if unknown:
        raise ValueError(f"Survey fixture contains {len(unknown)} unknown call_id values")
    if not _is_true(surveys["is_synthetic"]).all():
        raise ValueError("This artifact accepts only explicitly synthetic survey rows")

    calls = calls.copy()
    surveys = surveys.copy()
    calls["agent_call_number"] = pd.to_numeric(calls["agent_call_number"], errors="raise").astype(int)
    calls["conversation_risk_score"] = pd.to_numeric(
        calls["conversation_risk_score"], errors="raise"
    )
    calls["conversation_risk_level"] = (
        calls["conversation_risk_level"].astype(str).str.strip().str.casefold()
    )
    invalid_levels = sorted(set(calls["conversation_risk_level"]) - set(RISK_LEVELS))
    if invalid_levels:
        raise ValueError(f"Unexpected conversation risk levels: {invalid_levels}")
    surveys["survey_positive"] = pd.to_numeric(surveys["survey_positive"], errors="raise").astype(int)

    survey_fields = [
        "call_id",
        "survey_positive",
        "survey_type",
        "survey_score",
        "survey_completed_at",
        "is_synthetic",
        "source_system",
    ]
    joined = calls.merge(surveys[survey_fields], on="call_id", how="left", validate="one_to_one")
    joined["survey_linked"] = joined["survey_positive"].notna()

    agent_summary: list[dict[str, Any]] = []
    risk_mix: list[dict[str, Any]] = []
    surveyed_calls: list[dict[str, Any]] = []

    for stage in stages:
        stage_id = str(stage["id"])
        stage_label = str(stage["label"])
        call_limit = int(stage["calls"])
        stage_calls = joined.loc[joined["agent_call_number"] <= call_limit].copy()
        for (agent_id, agent_name), agent_calls in stage_calls.groupby(
            ["agent_id", "agent_name"], sort=True
        ):
            agent_calls = agent_calls.sort_values("agent_call_number")
            selected = agent_calls.loc[agent_calls["survey_linked"]].copy()
            total = len(agent_calls)
            survey_count = len(selected)
            counts = agent_calls["conversation_risk_level"].value_counts().to_dict()
            selected_counts = selected["conversation_risk_level"].value_counts().to_dict()
            low_calls = int(counts.get("low", 0))
            elevated_calls = int(counts.get("medium", 0) + counts.get("high", 0))
            surveyed_elevated = int(
                selected_counts.get("medium", 0) + selected_counts.get("high", 0)
            )
            elevated_share = _share(elevated_calls, total)
            surveyed_elevated_share = (
                _share(surveyed_elevated, survey_count) if survey_count else None
            )
            average_risk = round(float(agent_calls["conversation_risk_score"].mean()), 2)
            surveyed_average_risk = (
                round(float(selected["conversation_risk_score"].mean()), 2)
                if survey_count
                else None
            )
            elevated_gap = (
                round(surveyed_elevated_share - elevated_share, 4)
                if surveyed_elevated_share is not None
                else None
            )
            average_gap = (
                round(surveyed_average_risk - average_risk, 2)
                if surveyed_average_risk is not None
                else None
            )
            signal = _mix_signal(survey_count, elevated_gap, average_gap)
            confidence, confidence_reason = _confidence(survey_count, synthetic_only=True)
            positive = int(selected["survey_positive"].sum()) if survey_count else 0
            summary = {
                "agent_id": agent_id,
                "agent_name": agent_name,
                "agent_label": f"{agent_name} - {agent_id}",
                "stage_id": stage_id,
                "stage": stage_label,
                "calls_analyzed": total,
                "low_calls": low_calls,
                "medium_calls": int(counts.get("medium", 0)),
                "high_calls": int(counts.get("high", 0)),
                "low_share": _share(low_calls, total),
                "elevated_calls": elevated_calls,
                "elevated_share": elevated_share,
                "average_risk_proxy": average_risk,
                "surveys_received": survey_count,
                "survey_coverage": _share(survey_count, total),
                "synthetic_positive_surveys": positive,
                "synthetic_negative_surveys": survey_count - positive,
                "synthetic_positive_rate": _share(positive, survey_count),
                "surveyed_elevated_calls": surveyed_elevated,
                "surveyed_elevated_share": surveyed_elevated_share,
                "surveyed_average_risk_proxy": surveyed_average_risk,
                "elevated_share_gap": elevated_gap,
                "average_risk_gap_points": average_gap,
                "representativeness_signal": signal,
                "confidence": confidence,
                "confidence_reason": confidence_reason,
                "training_eligible": False,
                "real_survey_labels": 0,
            }
            summary["interpretation"] = _interpretation(summary)
            agent_summary.append(summary)

            for population, frame in (
                ("All analyzed calls", agent_calls),
                ("Synthetic surveyed calls", selected),
            ):
                population_total = len(frame)
                population_counts = frame["conversation_risk_level"].value_counts().to_dict()
                for level in RISK_LEVELS:
                    count = int(population_counts.get(level, 0))
                    risk_mix.append(
                        {
                            "agent_id": agent_id,
                            "agent_name": agent_name,
                            "stage_id": stage_id,
                            "stage": stage_label,
                            "population": population,
                            "risk_level": level,
                            "call_count": count,
                            "share": _share(count, population_total),
                            "population_calls": population_total,
                        }
                    )

            for _, survey_call in selected.iterrows():
                surveyed_calls.append(
                    {
                        "agent_id": agent_id,
                        "agent_name": agent_name,
                        "stage_id": stage_id,
                        "stage": stage_label,
                        "call_id": survey_call["call_id"],
                        "agent_call_number": int(survey_call["agent_call_number"]),
                        "heuristic_risk_score": float(survey_call["conversation_risk_score"]),
                        "heuristic_risk_level": survey_call["conversation_risk_level"],
                        "synthetic_survey_positive": int(survey_call["survey_positive"]),
                        "survey_type": survey_call["survey_type"],
                        "is_synthetic": True,
                        "training_eligible": False,
                    }
                )

    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return {
        "surface": "survey_representativeness_demo",
        "version": 1,
        "generatedAt": generated_at,
        "status": "synthetic_fixture_only",
        "purpose": (
            "Demonstrate whether surveyed calls resemble an agent's complete analyzed call mix."
        ),
        "metric_definitions": {
            "survey_coverage": "Synthetic surveyed calls divided by all analyzed calls in view.",
            "elevated_share": "Share of calls with medium/high heuristic review priority.",
            "elevated_share_gap": "Surveyed elevated share minus all-call elevated share.",
            "representativeness_signal": (
                "Directional flag using a 20 percentage-point elevated-mix gap or a "
                "5-point average heuristic-risk gap. It is not a statistical proof."
            ),
        },
        "guardrails": [
            "All linked surveys are synthetic fixtures and are ineligible for training.",
            "Heuristic risk is an uncalibrated review proxy, not call quality or survey probability.",
            "Describe the surveyed subset as more or less representative; do not label the agent good or bad.",
            "Real survey response propensity remains a separate future target.",
        ],
        "snapshot": {
            "generatedAt": generated_at,
            "status": "fixture",
            "datasets": {
                "agent_summary": agent_summary,
                "risk_mix": risk_mix,
                "surveyed_calls": surveyed_calls,
            },
        },
        "sources": [
            {
                "id": "canonical_calls",
                "label": "Canonical analyzed call summaries",
                "path": "data/final_outputs/all_calls_summary.csv",
            },
            {
                "id": "synthetic_surveys",
                "label": "Normalized synthetic survey fixture",
                "path": "data/outcomes/fixtures/synthetic_surveys_normalized.csv",
            },
        ],
    }


class SurveyRepresentativenessRepository:
    """Read-only access for the Copilot's controlled survey tool."""

    def __init__(self, artifact_path: Path = DEFAULT_ARTIFACT):
        self.artifact_path = artifact_path
        self.artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        self.datasets = self.artifact["snapshot"]["datasets"]

    def summary(self, agent_id: str, stage_id: str) -> dict[str, Any]:
        matches = [
            row
            for row in self.datasets["agent_summary"]
            if row["agent_id"] == agent_id and row["stage_id"] == stage_id
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Survey representativeness summary not found for {agent_id}/{stage_id}"
            )
        return matches[0]


def build_from_paths(
    calls_path: Path = DEFAULT_CALLS,
    surveys_path: Path = DEFAULT_SURVEYS,
    stage_config_path: Path = DEFAULT_STAGE_CONFIG,
    artifact_path: Path = DEFAULT_ARTIFACT,
) -> dict[str, Any]:
    calls = pd.read_csv(calls_path)
    surveys = pd.read_csv(surveys_path)
    config = json.loads(stage_config_path.read_text(encoding="utf-8"))
    artifact = build_artifact(calls, surveys, config["stages"])
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return artifact


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calls", type=Path, default=DEFAULT_CALLS)
    parser.add_argument("--surveys", type=Path, default=DEFAULT_SURVEYS)
    parser.add_argument("--stage-config", type=Path, default=DEFAULT_STAGE_CONFIG)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifact = build_from_paths(args.calls, args.surveys, args.stage_config, args.artifact)
    end_rows = [
        row for row in artifact["snapshot"]["datasets"]["agent_summary"] if row["stage_id"] == "end"
    ]
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "agents": len(end_rows),
                "calls": sum(row["calls_analyzed"] for row in end_rows),
                "synthetic_surveys": sum(row["surveys_received"] for row in end_rows),
                "real_labels": sum(row["real_survey_labels"] for row in end_rows),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
