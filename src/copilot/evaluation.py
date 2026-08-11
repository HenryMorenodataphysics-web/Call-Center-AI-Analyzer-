"""Evaluate agent and supervisor copilots with deterministic, auditable gates."""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .providers import DeterministicProvider, LlamaCppServerProvider
from .service import CopilotService, local_api_key
from .supervisor_agent import SupervisorAgentService


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES = PROJECT_ROOT / "config" / "copilot_evaluation_prompts_v1.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "validation" / "copilot_evaluation_results.json"
DEFAULT_REPORT = PROJECT_ROOT / "reports" / "copilot_evaluation_report.md"
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "copilot_config.json"
PID_PATH = PROJECT_ROOT / ".runtime" / "llama_server.pid"


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--providers",
        default="deterministic,llama_cpp_server",
        help="Comma-separated providers to evaluate.",
    )
    return parser.parse_args()


def provider_for(name: str):
    if name == "deterministic":
        return DeterministicProvider()
    if name != "llama_cpp_server":
        raise ValueError(f"Unsupported evaluation provider: {name}")
    config = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    server = config["llama_cpp_server"]
    generation = config["generation"]
    return LlamaCppServerProvider(
        base_url=os.environ.get("COPILOT_BASE_URL", server["base_url"]),
        model=server["model"],
        temperature=generation["temperature"],
        max_tokens=generation["max_tokens"],
        timeout_sec=generation["timeout_sec"],
        api_key=local_api_key(),
    )


def memory_snapshot() -> dict[str, float | None]:
    server_mib: float | None = None
    if PID_PATH.exists():
        raw_pid = PID_PATH.read_text(encoding="ascii").strip()
        if raw_pid.isdigit():
            command = (
                f"$p=Get-Process -Id {raw_pid} -ErrorAction SilentlyContinue; "
                "if($p){[math]::Round($p.WorkingSet64/1MB,2)}"
            )
            completed = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", command],
                capture_output=True,
                text=True,
                check=False,
            )
            try:
                server_mib = float(completed.stdout.strip())
            except ValueError:
                server_mib = None

    gpu_used_mib: float | None = None
    completed = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=memory.used",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode == 0:
        try:
            gpu_used_mib = float(completed.stdout.splitlines()[0].strip())
        except (ValueError, IndexError):
            gpu_used_mib = None
    return {"server_working_set_mib": server_mib, "gpu_used_mib": gpu_used_mib}


def required_terms_pass(answer: str, groups: list[list[str]]) -> bool:
    normalized = normalize_text(answer)
    return all(
        any(normalize_text(term) in normalized for term in alternatives)
        for alternatives in groups
    )


def score_response(case: dict[str, Any], response, latency_ms: float) -> dict[str, Any]:
    answer = response.answer
    expected_tools = set(case.get("expected_tools", []))
    expected_tools_any = set(case.get("expected_tools_any", []))
    tools_used = set(response.tool_calls)
    citation_markers = [f"[{citation.id}]" for citation in response.citations]
    checks = {
        "grounded": bool(response.grounded),
        "tool_routing": expected_tools.issubset(tools_used)
        and (not expected_tools_any or bool(expected_tools_any & tools_used)),
        "citation_count": len(response.citations) >= int(case.get("min_citations", 1)),
        "citation_markers": all(marker in answer for marker in citation_markers),
        "required_concepts": required_terms_pass(
            answer, case.get("required_any", [])
        ),
        "forbidden_claims": not any(
            re.search(pattern, answer, flags=re.IGNORECASE)
            for pattern in case.get("forbidden_regex", [])
        ),
        "numeric_grounding": not (
            response.fallback_reason
            and "unsupported numeric values" in response.fallback_reason
        ),
        "context": response.agent_id == case.get("expected_context", response.agent_id),
    }
    if "actionable" in case.get("tags", []):
        action_terms = (
            "action",
            "focus",
            "practice",
            "review",
            "recommend",
            "priorit",
            "next step",
        )
        normalized = normalize_text(answer)
        checks["actionability"] = any(term in normalized for term in action_terms)
    if "personalized" in case.get("tags", []):
        expected = case["expected_context"]
        agent_scoped_tools = {
            "kpi_lookup",
            "daily_recap",
            "call_evidence",
            "coaching_context",
            "survey_representativeness",
            "agent_memory",
            "agent_team_comparison",
            "coaching_queue",
            "review_calls",
        }
        checks["personalization"] = (
            expected != "team"
            and response.agent_id == expected
            and bool(agent_scoped_tools & tools_used)
        )

    critical_checks = (
        "grounded",
        "citation_count",
        "citation_markers",
        "forbidden_claims",
        "context",
    )
    safe_pass = all(checks[name] for name in critical_checks)
    return {
        **case,
        "provider": response.provider,
        "direct_provider": response.provider == "llama_cpp_server",
        "fallback_reason": response.fallback_reason,
        "tool_calls": response.tool_calls,
        "citation_count": len(response.citations),
        "warning_count": len(response.warnings),
        "latency_ms": latency_ms,
        "checks": checks,
        "safe_pass": safe_pass,
        "answer": answer,
    }


def rate(results: list[dict[str, Any]], check: str) -> float | None:
    relevant = [row["checks"][check] for row in results if check in row["checks"]]
    if not relevant:
        return None
    return round(sum(relevant) / len(relevant), 4)


def summarize_provider(
    configured_name: str,
    results: list[dict[str, Any]],
    memory_samples: list[dict[str, float | None]],
) -> dict[str, Any]:
    latencies = [row["latency_ms"] for row in results]
    critical = [row for row in results if row.get("critical")]
    fallbacks = [row for row in results if row["fallback_reason"]]
    summary = {
        "configured_provider": configured_name,
        "prompt_count": len(results),
        "safe_pass_rate": round(sum(row["safe_pass"] for row in results) / len(results), 4),
        "critical_safe_pass_rate": round(
            sum(row["safe_pass"] for row in critical) / len(critical), 4
        ),
        "direct_provider_rate": round(
            sum(row["direct_provider"] for row in results) / len(results), 4
        ),
        "fallback_count": len(fallbacks),
        "rates": {
            check: rate(results, check)
            for check in (
                "grounded",
                "tool_routing",
                "citation_count",
                "citation_markers",
                "required_concepts",
                "forbidden_claims",
                "numeric_grounding",
                "context",
                "actionability",
                "personalization",
            )
        },
        "latency_ms": {
            "average": round(statistics.mean(latencies), 2),
            "median": round(statistics.median(latencies), 2),
            "p95": round(statistics.quantiles(latencies, n=20)[18], 2),
            "maximum": round(max(latencies), 2),
        },
        "memory_mib": {
            "maximum_server_working_set": max(
                (
                    sample["server_working_set_mib"]
                    for sample in memory_samples
                    if sample["server_working_set_mib"] is not None
                ),
                default=None,
            ),
            "maximum_total_gpu_used": max(
                (
                    sample["gpu_used_mib"]
                    for sample in memory_samples
                    if sample["gpu_used_mib"] is not None
                ),
                default=None,
            ),
        },
        "results": results,
    }
    return summary


def evaluate_provider(
    configured_name: str, cases: list[dict[str, Any]]
) -> dict[str, Any]:
    provider = provider_for(configured_name)
    agent_service = CopilotService(provider=provider)
    supervisor_service = SupervisorAgentService(provider=provider)
    results: list[dict[str, Any]] = []
    memory_samples: list[dict[str, float | None]] = []
    for index, case in enumerate(cases, start=1):
        started = time.perf_counter()
        if case["surface"] == "agent":
            response = agent_service.ask(
                case["question"], case["agent"], case["stage"]
            )
        else:
            response = supervisor_service.ask(
                case["question"], case["stage"], case.get("agent")
            )
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        results.append(score_response(case, response, latency_ms))
        memory_samples.append(memory_snapshot())
        print(
            f"[{configured_name}] {index:02d}/{len(cases)} {case['id']}: "
            f"{latency_ms:.0f} ms, provider={response.provider}"
        )
    return summarize_provider(configured_name, results, memory_samples)


def gate_results(
    qwen: dict[str, Any], thresholds: dict[str, float]
) -> dict[str, Any]:
    metrics = {
        "safe_pass_rate": qwen["safe_pass_rate"],
        "critical_safe_pass_rate": qwen["critical_safe_pass_rate"],
        "tool_routing_rate": qwen["rates"]["tool_routing"],
        "citation_count_rate": qwen["rates"]["citation_count"],
        "citation_marker_rate": qwen["rates"]["citation_markers"],
        "required_concept_rate": qwen["rates"]["required_concepts"],
        "forbidden_claim_pass_rate": qwen["rates"]["forbidden_claims"],
        "numeric_grounding_rate": qwen["rates"]["numeric_grounding"],
        "actionability_rate": qwen["rates"]["actionability"],
        "personalization_rate": qwen["rates"]["personalization"],
    }
    checks = {
        name: {
            "actual": metrics[name],
            "required": required,
            "pass": metrics[name] is not None and metrics[name] >= required,
        }
        for name, required in thresholds.items()
    }
    return {
        "status": "pass" if all(item["pass"] for item in checks.values()) else "fail",
        "checks": checks,
    }


def render_report(payload: dict[str, Any]) -> str:
    providers = payload["providers"]
    lines = [
        "# Copilot Phase 4 evaluation",
        "",
        f"- Status: **{payload['status'].upper()}**",
        f"- Generated: `{payload['generated_at']}`",
        f"- Prompt set: `{payload['prompt_set_version']}` ({payload['prompt_count']} prompts)",
        "- Surfaces: Agent Copilot and Supervisor Copilot",
        "",
        "## Provider comparison",
        "",
        "| Provider | Safe pass | Direct provider | Fallbacks | Median latency | P95 latency |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, summary in providers.items():
        lines.append(
            f"| {name} | {summary['safe_pass_rate']:.0%} | "
            f"{summary['direct_provider_rate']:.0%} | {summary['fallback_count']} | "
            f"{summary['latency_ms']['median'] / 1000:.2f} s | "
            f"{summary['latency_ms']['p95'] / 1000:.2f} s |"
        )
    lines.extend(["", "## Qwen completion gates", ""])
    for name, check in payload["gates"]["checks"].items():
        label = "PASS" if check["pass"] else "FAIL"
        lines.append(
            f"- **{label}** `{name}`: {check['actual']:.1%} "
            f"(required {check['required']:.1%})."
        )
    decision = payload["decision"]
    lines.extend(
        [
            "",
            "## Default decision",
            "",
            f"- Portfolio application default: **{decision['application_default']}**",
            f"- Selected optional local model: **{decision['selected_local_model']}**",
            f"- Deployment position: {decision['deployment_position']}",
            "",
            "## Interpretation limits",
            "",
            "- Actionability is a transparent keyword-and-rubric proxy, not human preference scoring.",
            "- Personalization checks context and evidence citations, not coaching effectiveness.",
            "- GPU memory is total device usage and includes Windows applications.",
            "- A safe fallback counts as a safe answer but not as direct model acceptance.",
            "- No result authorizes employee ranking, discipline, compensation, or termination.",
            "",
            "## Failed cases",
            "",
        ]
    )
    failed = [
        row
        for row in providers.get("llama_cpp_server", {}).get("results", [])
        if not all(row["checks"].values())
    ]
    if not failed:
        lines.append("No Qwen rubric failures.")
    else:
        for row in failed:
            failed_checks = [name for name, passed in row["checks"].items() if not passed]
            lines.append(f"- `{row['id']}`: {', '.join(failed_checks)}")
    return "\n".join(lines) + "\n"


def evaluate(
    cases_path: Path = DEFAULT_CASES,
    output_path: Path = DEFAULT_OUTPUT,
    report_path: Path = DEFAULT_REPORT,
    provider_names: list[str] | None = None,
) -> dict[str, Any]:
    specification = json.loads(cases_path.read_text(encoding="utf-8"))
    cases = specification["prompts"]
    names = provider_names or ["deterministic", "llama_cpp_server"]
    providers = {name: evaluate_provider(name, cases) for name in names}
    qwen = providers.get("llama_cpp_server")
    if qwen:
        gates = gate_results(qwen, specification["completion_gates"])
    else:
        gates = {"status": "not_run", "checks": {}}
    qwen_passed = gates["status"] == "pass"
    qwen_median = qwen["latency_ms"]["median"] if qwen else None
    payload = {
        "status": "pass" if qwen_passed else "in_progress",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prompt_set_version": specification["version"],
        "prompt_count": len(cases),
        "providers": providers,
        "gates": gates,
        "decision": {
            "application_default": "deterministic",
            "selected_local_model": "Qwen3-4B-Q4_K_M" if qwen_passed else "not_selected",
            "deployment_position": (
                "Post-call and end-of-day grounded explanation; deterministic mode remains "
                "the zero-resource portfolio default."
                if qwen_passed and qwen_median is not None
                else "Keep local-model use experimental until completion gates pass."
            ),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    report_path.write_text(render_report(payload), encoding="utf-8")
    return payload


def main() -> None:
    args = parse_args()
    names = [name.strip() for name in args.providers.split(",") if name.strip()]
    payload = evaluate(args.cases, args.output, args.report, names)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "prompt_count": payload["prompt_count"],
                "gates": payload["gates"],
                "decision": payload["decision"],
            },
            indent=2,
        )
    )
    print(f"Results: {args.output}")
    print(f"Report: {args.report}")


if __name__ == "__main__":
    main()
