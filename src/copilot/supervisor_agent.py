"""Bounded, read-only agentic workflow for supervisor questions."""

from __future__ import annotations

import json
import re
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any, Protocol

from .guardrails import validate_generated_answer
from .models import Citation, CopilotRequest, CopilotResponse, ToolResult
from .providers import (
    CopilotProvider,
    DeterministicProvider,
    LlamaCppServerProvider,
    ProviderError,
)
from .retrieval import DEFAULT_KNOWLEDGE_DIR, PolicyRetriever
from .service import DEFAULT_CONFIG_PATH, local_api_key, unique
from .tools import AgentMemoryTool, PolicySearchTool, PROXY_WARNING
from src.personalization.build_agent_memory import AgentMemoryRepository


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SUPERVISOR_ARTIFACT = PROJECT_ROOT / "dashboard" / "supervisor_artifact.json"
MAX_TOOL_CALLS = 4

SUPERVISOR_WARNING = (
    "Supervisor outputs are review aids, not employee rankings or disciplinary findings."
)
CONTEXT_WARNING = (
    "Agent comparisons are descriptive and do not adjust for call complexity, language, "
    "market, or workload."
)
CROSS_AGENT_WARNING = (
    "Cross-agent suggestions are anonymous recurrence candidates, not best practices, "
    "rankings, causal effects, or validated outcome improvements."
)


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )


class SupervisorRepository:
    """Read-only access to the canonical supervisor artifact."""

    def __init__(self, artifact_path: Path = DEFAULT_SUPERVISOR_ARTIFACT):
        self.artifact_path = artifact_path
        self.artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        self.datasets: dict[str, list[dict[str, Any]]] = self.artifact["snapshot"][
            "datasets"
        ]
        self._agents = {
            row["agent_id"]: {
                "agent_id": row["agent_id"],
                "agent_name": row["agent_name"],
                "agent_label": row["agent_label"],
            }
            for row in self.datasets["agent_overview"]
        }
        self._stages = {
            row["stage_id"] for row in self.datasets["team_summary"]
        }

    def resolve_agent(self, value: str | None) -> dict[str, str] | None:
        if value is None or normalize_text(value) in {"team", "equipo", "all", "todos"}:
            return None
        if value in self._agents:
            return self._agents[value]
        needle = re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
        matches = [
            agent
            for agent in self._agents.values()
            if needle
            and (
                needle == re.sub(r"[^a-z0-9]+", " ", agent["agent_name"].casefold()).strip()
                or needle
                in re.sub(r"[^a-z0-9]+", " ", agent["agent_label"].casefold()).strip()
            )
        ]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise ValueError(f"Unknown agent: {value}")
        raise ValueError(f"Ambiguous agent: {value}")

    def validate_stage(self, stage: str) -> str:
        aliases = {
            "start": "start",
            "inicio": "start",
            "live": "live",
            "during": "live",
            "durante": "live",
            "end": "end",
            "final": "end",
        }
        normalized = re.sub(r"[^a-z0-9]+", " ", stage.casefold()).strip()
        stage_id = aliases.get(normalized, normalized)
        if stage_id not in self._stages:
            raise ValueError(f"Unknown shift view: {stage}")
        return stage_id

    def rows(
        self, dataset: str, stage_id: str, agent_id: str | None = None
    ) -> list[dict[str, Any]]:
        if dataset not in self.datasets:
            raise KeyError(f"Unknown supervisor dataset: {dataset}")
        rows = [
            row for row in self.datasets[dataset] if row.get("stage_id") == stage_id
        ]
        if agent_id is not None:
            rows = [row for row in rows if row.get("agent_id") == agent_id]
        return rows


class SupervisorTool(Protocol):
    name: str

    def run(self, request: CopilotRequest) -> ToolResult: ...


def _citation(dataset: str, stage_id: str, locator: str = "team") -> Citation:
    return Citation(
        f"supervisor:{dataset}:{stage_id}:{locator}",
        "dashboard/supervisor_artifact.json",
        f"{dataset}/{stage_id}/{locator}",
        "Canonical read-only supervisor artifact",
    )


class TeamMetricsTool:
    name = "team_metrics"

    def __init__(self, repository: SupervisorRepository):
        self.repository = repository

    def run(self, request: CopilotRequest) -> ToolResult:
        team = self.repository.rows("team_summary", request.stage_id)[0]
        priorities = self.repository.rows("priority_distribution", request.stage_id)
        behaviors = [
            row
            for row in self.repository.rows("team_behavior_coverage", request.stage_id)
            if row["series"] == "Team detected"
        ]
        priority_text = ", ".join(
            f"{row['priority']}: {row['agent_count']}" for row in priorities
        )
        weakest = sorted(behaviors, key=lambda row: row["value"])[:3]
        behavior_text = ", ".join(
            f"{row['behavior']} {row['value']:.0%}" for row in weakest
        )
        content = [
            (
                f"Team view contains {team['calls_reviewed']} reviewed calls across "
                f"{team['agents_in_view']} agents. Review distribution: {priority_text}."
            ),
            (
                f"Team estimated AHT is {team['team_estimated_aht_sec']} seconds and "
                f"team heuristic risk is {team['team_heuristic_risk']}."
            ),
            f"Lowest detected behavior coverage signals: {behavior_text}.",
        ]
        citations = [
            _citation("team_summary", request.stage_id),
            _citation("priority_distribution", request.stage_id),
            _citation("team_behavior_coverage", request.stage_id),
        ]
        data = {"team": team, "priorities": priorities, "behaviors": behaviors}
        return ToolResult(
            self.name,
            content,
            data,
            citations,
            [PROXY_WARNING, SUPERVISOR_WARNING],
        )


class AgentTeamComparisonTool:
    name = "agent_team_comparison"

    def __init__(self, repository: SupervisorRepository):
        self.repository = repository

    def run(self, request: CopilotRequest) -> ToolResult:
        if request.agent_id == "team":
            return ToolResult(
                self.name,
                ["Select a specific agent to compare with the team context."],
                {},
                [],
                [CONTEXT_WARNING, SUPERVISOR_WARNING],
            )
        agent = self.repository.rows(
            "agent_overview", request.stage_id, request.agent_id
        )[0]
        team = self.repository.rows("team_summary", request.stage_id)[0]
        aht_delta = round(
            agent["estimated_aht_sec"] - team["team_estimated_aht_sec"], 2
        )
        risk_delta = round(
            agent["heuristic_risk_score"] - team["team_heuristic_risk"], 2
        )
        content = [
            (
                f"{agent['agent_label']} has {agent['calls_reviewed']} reviewed calls and "
                f"is in the {agent['priority']} review category: {agent['priority_reason']}."
            ),
            (
                f"Estimated AHT is {agent['estimated_aht_sec']} seconds versus the team "
                f"mean {team['team_estimated_aht_sec']} seconds, a descriptive difference "
                f"of {aht_delta} seconds."
            ),
            (
                f"Heuristic risk is {agent['heuristic_risk_score']} versus the team mean "
                f"{team['team_heuristic_risk']}, a descriptive difference of {risk_delta}."
            ),
            (
                f"Current focus: {agent['focus_area']}. Evidence: {agent['focus_reason']} "
                f"Recommended action: {agent['recommended_action']}"
            ),
        ]
        citations = [
            _citation("agent_overview", request.stage_id, request.agent_id),
            _citation("team_summary", request.stage_id),
        ]
        return ToolResult(
            self.name,
            content,
            {"agent": agent, "team": team, "aht_delta": aht_delta, "risk_delta": risk_delta},
            citations,
            [PROXY_WARNING, CONTEXT_WARNING, SUPERVISOR_WARNING],
        )


class CoachingQueueTool:
    name = "coaching_queue"

    def __init__(self, repository: SupervisorRepository):
        self.repository = repository

    def run(self, request: CopilotRequest) -> ToolResult:
        agent_id = None if request.agent_id == "team" else request.agent_id
        rows = self.repository.rows("coaching_queue", request.stage_id, agent_id)
        rows = sorted(rows, key=lambda row: (row["priority_rank"], row["agent_id"]))[:5]
        content = [
            (
                f"{row['agent_label']} - {row['priority']}: {row['focus_area']}. "
                f"Why now: {row['why_now']} Next action: {row['next_action']}"
            )
            for row in rows
        ]
        citations = [
            _citation("coaching_queue", request.stage_id, row["agent_id"])
            for row in rows
        ]
        return ToolResult(
            self.name,
            content,
            rows,
            citations,
            [PROXY_WARNING, SUPERVISOR_WARNING],
        )


class ReviewCallsTool:
    name = "review_calls"

    def __init__(self, repository: SupervisorRepository):
        self.repository = repository

    def run(self, request: CopilotRequest) -> ToolResult:
        agent_id = None if request.agent_id == "team" else request.agent_id
        rows = self.repository.rows("review_calls", request.stage_id, agent_id)
        question = normalize_text(request.question)
        if any(term in question for term in ("best", "mejor", "strength", "fortaleza")):
            rows = [row for row in rows if row["selection"].startswith("Best")]
        elif any(term in question for term in ("coachable", "coach", "mejorar")):
            rows = [row for row in rows if row["selection"].startswith("Most coachable")]
        rows = sorted(
            rows,
            key=lambda row: (
                row["queue_order"],
                -float(row["heuristic_risk_score"]),
                row["agent_id"],
            ),
        )[:4]
        content = [
            (
                f"{row['agent_label']} - {row['selection']}: call {row['call_id']}, "
                f"estimated AHT {row['estimated_aht_sec']} seconds, heuristic risk "
                f"{row['heuristic_risk_score']}. Evidence: {row['evidence']}"
            )
            for row in rows
        ]
        citations = [
            Citation(
                f"supervisor-call:{row['call_id']}",
                "data/final_outputs/all_calls_summary.csv",
                row["call_id"],
                row["selection"],
            )
            for row in rows
        ]
        return ToolResult(
            self.name,
            content,
            rows,
            citations,
            [PROXY_WARNING, SUPERVISOR_WARNING],
        )


class TeamStatisticsTool:
    name = "team_statistics"

    def __init__(self, repository: SupervisorRepository):
        self.repository = repository

    @staticmethod
    def _profile(values: list[float]) -> dict[str, float]:
        return {
            "mean": round(mean(values), 2),
            "median": round(median(values), 2),
            "minimum": round(min(values), 2),
            "maximum": round(max(values), 2),
            "population_std": round(pstdev(values), 2),
        }

    def run(self, request: CopilotRequest) -> ToolResult:
        rows = self.repository.rows("agent_overview", request.stage_id)
        aht = self._profile([float(row["estimated_aht_sec"]) for row in rows])
        risk = self._profile([float(row["heuristic_risk_score"]) for row in rows])
        content = [
            (
                f"Across {len(rows)} agents, estimated AHT has mean {aht['mean']}, median "
                f"{aht['median']}, range {aht['minimum']} to {aht['maximum']}, and population "
                f"standard deviation {aht['population_std']} seconds."
            ),
            (
                f"Heuristic risk has mean {risk['mean']}, median {risk['median']}, range "
                f"{risk['minimum']} to {risk['maximum']}, and population standard deviation "
                f"{risk['population_std']}."
            ),
            "These are descriptive statistics, not evidence of causation or adjusted performance.",
        ]
        citation = _citation("agent_overview", request.stage_id, "all-agents")
        return ToolResult(
            self.name,
            content,
            {"agents": len(rows), "estimated_aht": aht, "heuristic_risk": risk},
            [citation],
            [PROXY_WARNING, CONTEXT_WARNING, SUPERVISOR_WARNING],
        )


class CrossAgentLearningTool:
    name = "cross_agent_learning"

    def __init__(self, repository: SupervisorRepository):
        self.repository = repository

    def run(self, request: CopilotRequest) -> ToolResult:
        rows = self.repository.rows("cross_agent_suggestions", request.stage_id)
        rows = sorted(
            rows,
            key=lambda row: (
                -row["behavior_anonymous_agents"],
                -row["behavior_call_coverage"],
                row["suggestion_id"],
            ),
        )[:4]
        if not rows:
            return ToolResult(
                self.name,
                [
                    "There is insufficient matched cross-agent evidence in this shift "
                    "view; later-stage calls were not used."
                ],
                [],
                [_citation("cross_agent_suggestions", request.stage_id, "none")],
                [CROSS_AGENT_WARNING, SUPERVISOR_WARNING],
            )

        content = [
            (
                f"{row['language_market']} / {row['source_domain']}: "
                f"{row['behavior_label']} recurred in {row['behavior_calls']} of "
                f"{row['context_calls']} matched calls across "
                f"{row['behavior_anonymous_agents']} anonymous agents. "
                f"Candidate action: {row['coaching_action']} No governed outcome "
                "association is available."
            )
            for row in rows
        ]
        citations = [
            _citation(
                "cross_agent_suggestions", request.stage_id, row["suggestion_id"]
            )
            for row in rows
        ]
        return ToolResult(
            self.name,
            content,
            rows,
            citations,
            [CROSS_AGENT_WARNING, CONTEXT_WARNING, SUPERVISOR_WARNING],
        )


class SupervisorToolRouter:
    """Safe fallback planner and validator for model-selected tool names."""

    TOOL_NAMES = (
        "team_metrics",
        "agent_team_comparison",
        "coaching_queue",
        "review_calls",
        "team_statistics",
        "cross_agent_learning",
        "agent_memory",
        "policy_search",
    )

    def __init__(
        self,
        repository: SupervisorRepository,
        retriever: PolicyRetriever,
        memory_repository: AgentMemoryRepository,
    ):
        self.repository = repository
        self.retriever = retriever
        self.memory_repository = memory_repository

    def deterministic_plan(self, question: str, has_agent: bool) -> list[str]:
        normalized = normalize_text(question)
        names: list[str] = []
        cross_agent_query = any(
            term in normalized
            for term in (
                "transfer",
                "transferable",
                "transferible",
                "technique",
                "tecnica",
                "similar",
                "peer",
                "cross agent",
                "across agents",
                "entre agentes",
                "best practice",
            )
        )
        if any(
            term in normalized
            for term in ("team", "equipo", "overall", "general", "health")
        ):
            names.append("team_metrics")
        if has_agent and any(
            term in normalized
            for term in (
                "compare",
                "comparison",
                "compar",
                "versus",
                "vs",
                "agent",
                "agente",
            )
        ):
            names.append("agent_team_comparison")
        if any(
            term in normalized
            for term in ("coach", "feedback", "attention", "atencion", "focus")
        ):
            names.append("coaching_queue")
        if not cross_agent_query and any(
            term in normalized
            for term in ("call", "llamada", "best", "mejor", "evidence", "evidencia")
        ):
            names.append("review_calls")
        if any(
            term in normalized
            for term in (
                "stat",
                "estad",
                "median",
                "average",
                "mean",
                "promedio",
                "distribution",
                "dispersion",
            )
        ):
            names.append("team_statistics")
        if cross_agent_query:
            names.append("cross_agent_learning")
        if has_agent and any(
            term in normalized
            for term in ("memory", "memoria", "history", "historial", "pattern", "patron")
        ):
            names.append("agent_memory")
        if any(
            term in normalized
            for term in ("policy", "politica", "compliance", "privacy", "privacidad")
        ):
            names.append("policy_search")
        if not names:
            names = ["agent_team_comparison", "coaching_queue"] if has_agent else [
                "team_metrics",
                "coaching_queue",
            ]
        return names[:MAX_TOOL_CALLS]

    def tools(
        self, question: str, agent_id: str, requested_names: list[str] | None = None
    ) -> list[SupervisorTool]:
        has_agent = agent_id != "team"
        names = requested_names or self.deterministic_plan(question, has_agent)
        allowed = [
            name
            for name in names
            if name in self.TOOL_NAMES
            and (has_agent or name not in {"agent_team_comparison", "agent_memory"})
        ]
        if not allowed:
            allowed = self.deterministic_plan(question, has_agent)
        factories = {
            "team_metrics": lambda: TeamMetricsTool(self.repository),
            "agent_team_comparison": lambda: AgentTeamComparisonTool(self.repository),
            "coaching_queue": lambda: CoachingQueueTool(self.repository),
            "review_calls": lambda: ReviewCallsTool(self.repository),
            "team_statistics": lambda: TeamStatisticsTool(self.repository),
            "cross_agent_learning": lambda: CrossAgentLearningTool(self.repository),
            "agent_memory": lambda: AgentMemoryTool(self.memory_repository),
            "policy_search": lambda: PolicySearchTool(self.retriever, question),
        }
        selected: list[SupervisorTool] = []
        for name in allowed:
            if name not in {tool.name for tool in selected}:
                selected.append(factories[name]())
            if len(selected) == MAX_TOOL_CALLS:
                break
        return selected


class LlamaCppSupervisorPlanner:
    """Ask local Qwen for a bounded tool plan; never grants raw data access."""

    def __init__(self, provider: LlamaCppServerProvider):
        self.provider = provider

    def plan(self, question: str, has_agent: bool) -> list[str]:
        catalog = list(SupervisorToolRouter.TOOL_NAMES)
        if not has_agent:
            catalog.remove("agent_team_comparison")
            catalog.remove("agent_memory")
        payload = {
            "model": self.provider.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Select read-only tools for a supervisor question. Return only a JSON "
                        "array of one to four tool names from the supplied catalog. Do not answer "
                        "the question and do not add arguments."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "question": question,
                            "agent_context_available": has_agent,
                            "tools": catalog,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "temperature": 0,
            "max_tokens": 100,
            "stream": False,
        }
        headers = {"Content-Type": "application/json"}
        if self.provider.api_key:
            headers["Authorization"] = f"Bearer {self.provider.api_key}"
        request = urllib.request.Request(
            f"{self.provider.base_url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.provider.timeout_sec) as response:
                data = json.loads(response.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            start, end = content.find("["), content.rfind("]")
            if start < 0 or end < start:
                raise ValueError("missing JSON array")
            names = json.loads(content[start : end + 1])
        except (
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
        ) as exc:
            raise ProviderError(f"Supervisor tool planner failed: {exc}") from exc
        if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
            raise ProviderError("Supervisor tool planner returned an invalid tool list")
        valid = [name for name in names if name in catalog]
        if not valid:
            raise ProviderError("Supervisor tool planner selected no valid tools")
        return valid[:MAX_TOOL_CALLS]


class SupervisorAgentService:
    """Plan, execute, validate, and cite a bounded supervisor answer."""

    def __init__(
        self,
        artifact_path: Path = DEFAULT_SUPERVISOR_ARTIFACT,
        knowledge_dir: Path = DEFAULT_KNOWLEDGE_DIR,
        config_path: Path = DEFAULT_CONFIG_PATH,
        provider: CopilotProvider | None = None,
    ):
        self.config = json.loads(config_path.read_text(encoding="utf-8"))
        self.repository = SupervisorRepository(artifact_path)
        self.retriever = PolicyRetriever(knowledge_dir)
        self.memory_repository = AgentMemoryRepository()
        self.router = SupervisorToolRouter(
            self.repository, self.retriever, self.memory_repository
        )
        self.fallback_provider = DeterministicProvider()
        self.provider = provider or self._provider_from_config()

    def _provider_from_config(self) -> CopilotProvider:
        provider_name = self.config.get("default_provider", "deterministic")
        if provider_name == "deterministic":
            return DeterministicProvider()
        if provider_name == "llama_cpp_server":
            server = self.config["llama_cpp_server"]
            generation = self.config["generation"]
            return LlamaCppServerProvider(
                base_url=server["base_url"],
                model=server["model"],
                temperature=generation["temperature"],
                max_tokens=generation["max_tokens"],
                timeout_sec=generation["timeout_sec"],
                api_key=local_api_key(),
            )
        raise ValueError(f"Unsupported copilot provider: {provider_name}")

    def ask(
        self,
        question: str,
        stage: str = "live",
        agent: str | None = None,
    ) -> CopilotResponse:
        if not question.strip():
            raise ValueError("Question must not be empty")
        stage_id = self.repository.validate_stage(stage)
        agent_record = self.repository.resolve_agent(agent)
        agent_id = agent_record["agent_id"] if agent_record else "team"
        request = CopilotRequest(question.strip(), agent_id, stage_id)

        planning_fallback: str | None = None
        requested_names: list[str] | None = None
        if isinstance(self.provider, LlamaCppServerProvider):
            try:
                requested_names = LlamaCppSupervisorPlanner(self.provider).plan(
                    request.question, agent_record is not None
                )
            except ProviderError as exc:
                planning_fallback = str(exc)
        tools = self.router.tools(request.question, agent_id, requested_names)
        results = [tool.run(request) for tool in tools]

        provider_name = self.provider.name
        fallback_reason = planning_fallback
        try:
            answer = self.provider.generate(request.question, results)
            valid, reason = validate_generated_answer(answer, request.question, results)
            if not valid:
                fallback_reason = reason
                answer = self.fallback_provider.generate(request.question, results)
                provider_name = self.fallback_provider.name
        except ProviderError as exc:
            fallback_reason = str(exc)
            answer = self.fallback_provider.generate(request.question, results)
            provider_name = self.fallback_provider.name

        citations = list(
            {
                citation.id: citation
                for result in results
                for citation in result.citations
            }.values()
        )
        warnings = unique([warning for result in results for warning in result.warnings])
        if citations and not all(f"[{citation.id}]" in answer for citation in citations):
            answer = answer.rstrip() + "\n\nEvidence: " + ", ".join(
                f"[{citation.id}]" for citation in citations
            )
        if warnings:
            answer = answer.rstrip() + "\n\nLimits:\n- " + "\n- ".join(warnings)

        return CopilotResponse(
            answer=answer,
            agent_id=agent_id,
            stage_id=stage_id,
            provider=provider_name,
            tool_calls=[result.name for result in results],
            citations=citations,
            warnings=warnings,
            grounded=True,
            fallback_reason=fallback_reason,
        )
