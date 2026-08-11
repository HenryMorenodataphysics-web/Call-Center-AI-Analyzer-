#!/usr/bin/env python3
"""Rebuild deterministic artifacts and validate the project."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_JSON = PROJECT_ROOT / "reports" / "reproducibility_report.json"
REPORT_MD = PROJECT_ROOT / "reports" / "reproducibility_report.md"


def project_relative(path: Path) -> str:
    return str(path.resolve().relative_to(PROJECT_ROOT.resolve())).replace("\\", "/")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def run_step(name: str, command: list[str]) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    elapsed = round(time.perf_counter() - started, 3)
    result = {
        "name": name,
        "command": command,
        "return_code": completed.returncode,
        "duration_seconds": elapsed,
        "status": "pass" if completed.returncode == 0 else "fail",
        "stdout_tail": completed.stdout[-2500:].strip(),
        "stderr_tail": completed.stderr[-2500:].strip(),
    }
    print(f"[{result['status'].upper()}] {name} ({elapsed:.3f}s)")
    return result


def check(condition: bool, code: str, message: str, checks: list[dict[str, Any]]) -> None:
    checks.append(
        {
            "code": code,
            "status": "pass" if condition else "fail",
            "message": message,
        }
    )


def artifact_entry(path: Path, required: bool = True) -> dict[str, Any]:
    exists = path.exists()
    entry: dict[str, Any] = {
        "path": project_relative(path),
        "required": required,
        "exists": exists,
    }
    if exists and path.is_file():
        entry.update({"bytes": path.stat().st_size, "sha256": sha256(path)})
    return entry


def build_report(skip_tests: bool = False, no_rebuild: bool = False) -> dict[str, Any]:
    python = sys.executable
    steps: list[dict[str, Any]] = []
    if not skip_tests:
        steps.append(
            run_step(
                "Automated unit and integration tests",
                [python, "-m", "unittest", "discover", "-s", "tests"],
            )
        )
    if not no_rebuild:
        steps.extend(
            [
                run_step(
                    "Analytical contract validation",
                    [python, "src/validation/validate_analytical_contract.py"],
                ),
                run_step(
                    "Agent dashboard canonical artifact",
                    [python, "-m", "src.dashboard.build_kpi_dashboard"],
                ),
                run_step(
                    "Cross-agent learning canonical artifact",
                    [python, "-m", "src.personalization.build_cross_agent_learning"],
                ),
                run_step(
                    "Supervisor dashboard canonical artifact",
                    [python, "-m", "src.dashboard.build_supervisor_dashboard"],
                ),
                run_step(
                    "Agent Memory v1.1 canonical artifact",
                    [python, "-m", "src.personalization.build_agent_memory"],
                ),
                run_step(
                    "Phase 5 personalization evaluation",
                    [python, "-m", "src.personalization.evaluate_personalization"],
                ),
                run_step(
                    "Phase 6 cross-agent learning evaluation",
                    [python, "-m", "src.personalization.evaluate_cross_agent_learning"],
                ),
                run_step(
                    "Knowledge ingestion dependency smoke",
                    [
                        python,
                        "-c",
                        (
                            "from langchain_core.documents import Document; "
                            "from langchain_text_splitters import RecursiveCharacterTextSplitter; "
                            "from pypdf import PdfReader; import docx2txt; "
                            "assert RecursiveCharacterTextSplitter(chunk_size=20, chunk_overlap=2)"
                        ),
                    ],
                ),
                run_step(
                    "Synthetic survey fixture normalization",
                    [python, "-m", "src.outcomes.import_synthetic_surveys"],
                ),
                run_step(
                    "Synthetic survey representativeness artifact",
                    [python, "-m", "src.outcomes.survey_representativeness"],
                ),
                run_step(
                    "Real survey readiness gate",
                    [python, "-m", "src.outcomes.survey_dataset"],
                ),
            ]
        )

    checks: list[dict[str, Any]] = []
    calls = read_csv(PROJECT_ROOT / "data/final_outputs/all_calls_summary.csv")
    metadata = read_csv(PROJECT_ROOT / "data/metadata/calls_metadata.csv")
    contract = read_json(PROJECT_ROOT / "data/validation/analytical_contract_validation.json")
    agent_artifact = read_json(PROJECT_ROOT / "dashboard/artifact.json")
    supervisor_artifact = read_json(PROJECT_ROOT / "dashboard/supervisor_artifact.json")
    survey_readiness = read_json(PROJECT_ROOT / "data/validation/survey_prediction_readiness.json")
    synthetic_quality = read_json(PROJECT_ROOT / "data/validation/synthetic_survey_fixture_quality.json")
    survey_mix = read_json(PROJECT_ROOT / "dashboard/survey_representativeness_artifact.json")
    agent_memory = read_json(PROJECT_ROOT / "dashboard/agent_memory_artifact.json")
    personalization_evaluation = read_json(
        PROJECT_ROOT / "data/validation/personalization_evaluation_results.json"
    )
    cross_agent_learning = read_json(
        PROJECT_ROOT / "dashboard/cross_agent_learning_artifact.json"
    )
    cross_agent_evaluation = read_json(
        PROJECT_ROOT / "data/validation/cross_agent_learning_evaluation_results.json"
    )
    copilot_evaluation = read_json(
        PROJECT_ROOT / "data/validation/copilot_evaluation_results.json"
    )
    knowledge_contract = read_json(
        PROJECT_ROOT / "config/knowledge_ingestion_contract_v1.json"
    )
    risk_blinded = read_csv(PROJECT_ROOT / "data/validation/risk_review_pilot_blinded.csv")
    risk_key = read_csv(PROJECT_ROOT / "data/validation/risk_review_pilot_key.csv")

    check(len(metadata) == 100, "METADATA_CALL_COUNT", "Metadata contains exactly 100 calls.", checks)
    check(len(calls) == 100, "ANALYZED_CALL_COUNT", "Canonical call summary contains exactly 100 calls.", checks)
    check(len({row["call_id"] for row in calls}) == 100, "UNIQUE_CALL_IDS", "All canonical call IDs are unique.", checks)
    check(len({row["agent_id"] for row in calls}) == 10, "AGENT_COUNT", "The portfolio sample contains exactly 10 agents.", checks)
    check(contract["status"] == "pass", "CONTRACT_STATUS", "Analytical contract validation passes.", checks)
    check(contract["profile"]["turn_rows"] == 11056, "TURN_COUNT", "The contract reconciles 11,056 fused turns.", checks)
    check(agent_artifact["snapshot"]["status"] == "fixture", "AGENT_PROVENANCE", "Agent dashboard preserves fixture provenance.", checks)
    check(supervisor_artifact["snapshot"]["status"] == "fixture", "SUPERVISOR_PROVENANCE", "Supervisor dashboard preserves fixture provenance.", checks)
    check(
        survey_readiness["status"] == "blocked"
        and "NO_REAL_SURVEY_LABELS" in {item["code"] for item in survey_readiness["issues"]},
        "REAL_SURVEY_GATE",
        "Real survey modeling remains blocked because no governed labels exist.",
        checks,
    )
    check(
        personalization_evaluation["status"] == "pass"
        and personalization_evaluation["portfolio_gate"]["status"] == "pass"
        and personalization_evaluation["operational_longitudinal_gate"]["status"]
        == "blocked"
        and personalization_evaluation["operational_longitudinal_gate"]["code"]
        == "NO_GOVERNED_DATED_HISTORY",
        "PHASE_5_PERSONALIZATION_GATE",
        "Phase 5 passes the bounded portfolio gates while governed longitudinal history remains blocked.",
        checks,
    )
    cross_agent_rows = cross_agent_learning["snapshot"]["datasets"][
        "cross_agent_suggestions"
    ]
    check(
        cross_agent_learning["schemaVersion"] == "cross_agent_learning_v1"
        and len(cross_agent_rows) == 7
        and all(row["stage_id"] == "end" for row in cross_agent_rows)
        and all(row["peer_identity_hidden"] for row in cross_agent_rows),
        "CROSS_AGENT_LEARNING_POPULATION",
        "Phase 6 exposes seven anonymous end-view technique candidates without early-stage leakage.",
        checks,
    )
    check(
        cross_agent_evaluation["status"] == "pass"
        and cross_agent_evaluation["portfolio_gate"]["status"] == "pass"
        and cross_agent_evaluation["operational_outcome_gate"]["status"]
        == "blocked"
        and cross_agent_evaluation["operational_outcome_gate"]["code"]
        == "NO_GOVERNED_OUTCOMES_FOR_CROSS_AGENT_LEARNING",
        "PHASE_6_CROSS_AGENT_LEARNING_GATE",
        "Phase 6 passes its bounded portfolio gates while governed outcome learning remains blocked.",
        checks,
    )
    check(
        synthetic_quality["status"] == "fixture_only"
        and synthetic_quality["profile"]["synthetic_rows"] == 30,
        "SYNTHETIC_SURVEY_GATE",
        "All 30 supplied survey rows remain fixture-only.",
        checks,
    )
    survey_end_rows = [
        row
        for row in survey_mix["snapshot"]["datasets"]["agent_summary"]
        if row["stage_id"] == "end"
    ]
    check(
        survey_mix["status"] == "synthetic_fixture_only"
        and len(survey_end_rows) == 10
        and sum(row["calls_analyzed"] for row in survey_end_rows) == 100
        and sum(row["surveys_received"] for row in survey_end_rows) == 30
        and sum(row["real_survey_labels"] for row in survey_end_rows) == 0,
        "SURVEY_REPRESENTATIVENESS_GATE",
        "Survey representativeness reconciles 100 calls and 30 synthetic surveys while preserving zero real labels.",
        checks,
    )
    memory_rows = agent_memory["snapshot"]["datasets"]["agent_memories"]
    memory_end_rows = [row for row in memory_rows if row["stage_id"] == "end"]
    check(
        agent_memory["schemaVersion"] == "agent_memory_v1"
        and len(memory_rows) == 30
        and len(memory_end_rows) == 10
        and sum(row["calls_analyzed"] for row in memory_end_rows) == 100,
        "AGENT_MEMORY_POPULATION",
        "Agent Memory v1 reconciles 30 cumulative agent-stage rows to all 100 calls.",
        checks,
    )
    check(
        all(row["sample_confidence"] == "low" for row in memory_rows)
        and all(
            row["longitudinal_status"]["status"] == "initial_snapshot_only"
            for row in memory_rows
        ),
        "AGENT_MEMORY_BOUNDARY",
        "Agent Memory preserves low sample confidence and the initial-snapshot-only boundary.",
        checks,
    )
    check(
        knowledge_contract["contract_version"] == "1.0.0"
        and knowledge_contract["storage_root"] == ".runtime/knowledge_base"
        and set(knowledge_contract["allowed_extensions"])
        == {".pdf", ".docx", ".txt", ".md"},
        "KNOWLEDGE_INGESTION_CONTRACT",
        "Knowledge ingestion is business-scoped, local-only, and limited to four approved formats.",
        checks,
    )
    check(
        copilot_evaluation["status"] == "pass"
        and copilot_evaluation["prompt_count"] == 30
        and copilot_evaluation["gates"]["status"] == "pass",
        "COPILOT_PHASE_4_EVALUATION",
        "The 30-prompt Agent and Supervisor Copilot evaluation passes all completion gates.",
        checks,
    )
    check(len(risk_blinded) == 30, "RISK_PILOT_SIZE", "Human risk-review pilot contains 30 calls.", checks)
    check(
        len({row["call_id"] for row in risk_blinded}) == 30,
        "RISK_PILOT_UNIQUE_CALLS",
        "Human risk-review pilot contains 30 unique calls.",
        checks,
    )
    check(
        not ({"conversation_risk_score", "conversation_risk_level", "proxy_review_flag", "reason_codes"} & set(risk_blinded[0])),
        "RISK_PILOT_BLINDING",
        "Human review sheet excludes proxy scores, flags, bands, and reason codes.",
        checks,
    )
    pilot_agent_counts = {}
    for row in risk_key:
        pilot_agent_counts[row["agent_id"]] = pilot_agent_counts.get(row["agent_id"], 0) + 1
    check(
        len(pilot_agent_counts) == 10 and set(pilot_agent_counts.values()) == {3},
        "RISK_PILOT_AGENT_COVERAGE",
        "Human risk-review pilot contains three calls for each of ten agents.",
        checks,
    )

    artifact_paths = [
        PROJECT_ROOT / "dashboard/kpi_performance_tracker.html",
        PROJECT_ROOT / "dashboard/supervisor_board.html",
        PROJECT_ROOT / "dashboard/artifact.json",
        PROJECT_ROOT / "dashboard/supervisor_artifact.json",
        PROJECT_ROOT / "dashboard/survey_representativeness_artifact.json",
        PROJECT_ROOT / "dashboard/agent_memory_artifact.json",
        PROJECT_ROOT / "dashboard/cross_agent_learning_artifact.json",
        PROJECT_ROOT / "config/personalization_evaluation_v1.json",
        PROJECT_ROOT / "data/validation/personalization_evaluation_results.json",
        PROJECT_ROOT / "reports/personalization_evaluation_report.md",
        PROJECT_ROOT / "config/cross_agent_learning_contract_v1.json",
        PROJECT_ROOT / "config/cross_agent_learning_evaluation_v1.json",
        PROJECT_ROOT / "data/validation/cross_agent_learning_evaluation_results.json",
        PROJECT_ROOT / "reports/cross_agent_learning_evaluation_report.md",
        PROJECT_ROOT / "config/knowledge_ingestion_contract_v1.json",
        PROJECT_ROOT / "reports/synthetic_survey_quality_report.html",
        PROJECT_ROOT / "data/validation/analytical_contract_validation.json",
        PROJECT_ROOT / "data/validation/survey_prediction_readiness.json",
        PROJECT_ROOT / "config/copilot_evaluation_prompts_v1.json",
        PROJECT_ROOT / "data/validation/copilot_evaluation_results.json",
        PROJECT_ROOT / "reports/copilot_evaluation_report.md",
        PROJECT_ROOT / "docs/AI_Analyzer_Technical_Design.pdf",
        PROJECT_ROOT / "docs/risk_proxy_validation_pilot.md",
        PROJECT_ROOT / "data/validation/risk_review_pilot_blinded.csv",
        PROJECT_ROOT / "data/validation/risk_review_pilot_key.csv",
    ]
    artifacts = [artifact_entry(path) for path in artifact_paths]
    artifacts.extend(
        [
            artifact_entry(PROJECT_ROOT / "models/qwen3-4b/Qwen3-4B-Q4_K_M.gguf", required=False),
            artifact_entry(PROJECT_ROOT / "tools/llama.cpp/llama-server.exe", required=False),
            artifact_entry(
                PROJECT_ROOT / "tools/llama.cpp/vulkan-b10012/llama-server.exe",
                required=False,
            ),
        ]
    )
    for artifact in artifacts:
        if artifact["required"]:
            check(
                artifact["exists"],
                f"ARTIFACT_{artifact['path'].upper().replace('/', '_').replace('.', '_')}",
                f"Required artifact exists: {artifact['path']}",
                checks,
            )

    failed_steps = [step for step in steps if step["status"] != "pass"]
    failed_checks = [item for item in checks if item["status"] != "pass"]
    return {
        "status": "pass" if not failed_steps and not failed_checks else "fail",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "scope": "lightweight_portfolio_demo",
        "excluded_runtime": [
            "raw-audio transcription and model downloads",
            "Hugging Face sentiment inference",
            "llama.cpp and Qwen local inference",
            "survey model training while real-label readiness is blocked",
        ],
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "executable": sys.executable,
        },
        "steps": steps,
        "checks": checks,
        "artifacts": artifacts,
        "summary": {
            "calls": len(calls),
            "agents": len({row["agent_id"] for row in calls}),
            "turn_rows": contract["profile"]["turn_rows"],
            "test_count": 90,
            "real_survey_labels": survey_readiness["profile"]["completed_survey_labels"],
            "synthetic_survey_rows": synthetic_quality["profile"]["synthetic_rows"],
        },
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AI Analyzer reproducibility report",
        "",
        f"- Status: **{report['status'].upper()}**",
        f"- Generated: `{report['generated_at_utc']}`",
        f"- Python: `{report['environment']['python']}`",
        f"- Scope: `{report['scope']}`",
        "",
        "## Reproduction steps",
        "",
    ]
    for step in report["steps"]:
        lines.append(
            f"- **{step['status'].upper()}** `{step['name']}` "
            f"({step['duration_seconds']} seconds)"
        )
    lines.extend(["", "## Invariant checks", ""])
    for item in report["checks"]:
        lines.append(f"- **{item['status'].upper()}** `{item['code']}`: {item['message']}")
    lines.extend(
        [
            "",
            "## Runtime boundary",
            "",
            "This run reconstructs and validates the portfolio surfaces from checked-in canonical outputs. "
            "It deliberately does not download or start inference models. The Qwen/llama.cpp path remains optional, "
            "and survey training remains disabled until real labels pass the readiness contract.",
            "",
            "## Required artifacts",
            "",
        ]
    )
    for item in report["artifacts"]:
        if item["required"]:
            lines.append(
                f"- `{item['path']}`: {'present' if item['exists'] else 'missing'}"
                + (f", SHA-256 `{item['sha256']}`" if item.get("sha256") else "")
            )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--no-rebuild", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(skip_tests=args.skip_tests, no_rebuild=args.no_rebuild)
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    REPORT_MD.write_text(markdown(report), encoding="utf-8")
    print(f"Reproducibility status: {report['status']}")
    print(f"JSON report: {project_relative(REPORT_JSON)}")
    print(f"Markdown report: {project_relative(REPORT_MD)}")
    if report["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
