"""Controlled read-only tools available to the copilot."""

from __future__ import annotations

import re
from typing import Protocol

from .models import Citation, CopilotRequest, ToolResult
from .repository import DashboardRepository
from .retrieval import PolicyRetriever
from src.outcomes.survey_representativeness import SurveyRepresentativenessRepository
from src.personalization.build_agent_memory import AgentMemoryRepository


SYNTHETIC_WARNING = (
    "CSAT, QA, NPS, and Five Stars are synthetic portfolio fixtures, not official outcomes."
)
PROXY_WARNING = (
    "Estimated AHT is an audio-duration proxy and conversation risk is an uncalibrated heuristic."
)


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


class CopilotTool(Protocol):
    name: str

    def run(self, request: CopilotRequest) -> ToolResult: ...


class KpiLookupTool:
    name = "kpi_lookup"

    def __init__(self, repository: DashboardRepository):
        self.repository = repository

    @staticmethod
    def _select_rows(question: str, rows: list[dict]) -> list[dict]:
        normalized = question.casefold()
        recap_terms = ("recap", "summary", "resumen", "day", "dia", "turno")
        if any(term in normalized for term in recap_terms):
            recap_metrics = ("estimated aht", "csat", "qa")
            selected = [
                row
                for row in rows
                if any(label in row["metric"].casefold() for label in recap_metrics)
            ]
            return selected[:3] or rows[:3]
        terms = {
            "aht": "estimated aht",
            "risk": "heuristic risk",
            "riesgo": "heuristic risk",
            "csat": "csat",
            "qa": "qa",
            "nps": "nps",
            "five star": "five stars",
            "cinco estrellas": "five stars",
        }
        labels = {label for term, label in terms.items() if term in normalized}
        if not labels:
            return rows
        selected = [
            row for row in rows if any(label in row["metric"].casefold() for label in labels)
        ]
        return selected or rows

    def run(self, request: CopilotRequest) -> ToolResult:
        rows = self._select_rows(
            request.question,
            self.repository.rows("kpi_status", request.agent_id, request.stage_id),
        )
        citations: list[Citation] = []
        content: list[str] = []
        normalized_question = request.question.casefold()
        asks_for_official = any(term in normalized_question for term in ("official", "oficial"))
        for row in rows:
            citation_id = f"kpi:{request.agent_id}:{request.stage_id}:{slug(row['metric'])}"
            citations.append(
                Citation(
                    citation_id,
                    "dashboard/artifact.json",
                    f"kpi_status/{request.agent_id}/{request.stage_id}/{row['metric']}",
                    row["source_type"],
                )
            )
            if asks_for_official and row["source_type"] == "synthetic_demo":
                official_name = row["metric"].split(" - ", 1)[0]
                content.append(
                    f"Official {official_name} is unavailable. A synthetic demo fixture exists, "
                    f"but its value is withheld from official-KPI answers [{citation_id}]"
                )
            else:
                content.append(
                    f"{row['metric']}: current {row['current']}; goal {row['goal']}; "
                    f"trend {row['trend']}; projection {row['projection']}; status {row['status']} "
                    f"[{citation_id}]"
                )
        warnings = [PROXY_WARNING]
        if any(row["source_type"] == "synthetic_demo" for row in rows):
            warnings.append(SYNTHETIC_WARNING)
        return ToolResult(self.name, content, rows, citations, warnings)


class DailyRecapTool:
    name = "daily_recap"

    def __init__(self, repository: DashboardRepository):
        self.repository = repository

    def run(self, request: CopilotRequest) -> ToolResult:
        focus = self.repository.rows("todays_focus", request.agent_id, request.stage_id)[0]
        citation_id = f"recap:{request.agent_id}:{request.stage_id}"
        content = [
            f"{focus['recap']} {focus['why']}",
            f"Today's Focus: {focus['focus_area']}. Action: {focus['recommended_action']}",
            f"Guardrail: {focus['guardrail']} [{citation_id}]",
        ]
        citation = Citation(
            citation_id,
            "dashboard/artifact.json",
            f"todays_focus/{request.agent_id}/{request.stage_id}",
            focus["evidence_type"],
        )
        return ToolResult(self.name, content, focus, [citation], [PROXY_WARNING])


class CallEvidenceTool:
    name = "call_evidence"

    def __init__(self, repository: DashboardRepository):
        self.repository = repository

    def run(self, request: CopilotRequest) -> ToolResult:
        rows = self.repository.rows("call_highlights", request.agent_id, request.stage_id)
        content: list[str] = []
        citations: list[Citation] = []
        for row in rows:
            citation_id = f"call:{row['call_id']}"
            content.append(
                f"{row['highlight']}: call #{row['call_number']} ({row['call_id']}), "
                f"risk proxy {row['heuristic_risk_score']}, estimated AHT "
                f"{row['estimated_aht_sec']} sec. Evidence: {row['evidence']} [{citation_id}]"
            )
            citations.append(
                Citation(
                    citation_id,
                    "data/final_outputs/all_calls_summary.csv",
                    row["call_id"],
                    row["evidence"],
                )
            )
        return ToolResult(self.name, content, rows, citations, [PROXY_WARNING])


class CoachingContextTool:
    name = "coaching_context"

    def __init__(self, repository: DashboardRepository):
        self.repository = repository

    def run(self, request: CopilotRequest) -> ToolResult:
        row = self.repository.rows("todays_focus", request.agent_id, request.stage_id)[0]
        citation_id = f"coaching:{request.agent_id}:{request.stage_id}:{slug(row['focus_area'])}"
        content = [
            f"Focus area: {row['focus_area']}. Observed fact (do not invert): {row['why']}",
            f"Recommended action: {row['recommended_action']}",
            f"Guardrail: {row['guardrail']} [{citation_id}]",
        ]
        citation = Citation(
            citation_id,
            "src/dashboard/build_kpi_dashboard.py",
            f"focus_recommendation/{request.agent_id}/{request.stage_id}",
            row["evidence_type"],
        )
        return ToolResult(self.name, content, row, [citation], [PROXY_WARNING])


class PolicySearchTool:
    name = "policy_search"

    def __init__(self, retriever: PolicyRetriever, query: str):
        self.retriever = retriever
        self.query = query

    def run(self, request: CopilotRequest) -> ToolResult:
        del request
        chunks = self.retriever.search(self.query)
        content: list[str] = []
        citations: list[Citation] = []
        for chunk in chunks:
            citation_key = chunk.chunk_id or f"{slug(chunk.document)}:{slug(chunk.heading)}"
            citation_id = f"policy:{citation_key}"
            provenance = ""
            if chunk.source_type == "approved_uploaded_policy":
                page = f", page {chunk.page}" if chunk.page is not None else ""
                provenance = f" (version {chunk.version}{page})"
            content.append(
                f"{chunk.heading}{provenance}: {chunk.text} [{citation_id}]"
            )
            note = (
                f"Approved uploaded policy; business={chunk.business_id}; "
                f"version={chunk.version}"
                if chunk.source_type == "approved_uploaded_policy"
                else "Portfolio demo policy"
            )
            citations.append(
                Citation(
                    citation_id,
                    chunk.document,
                    chunk.locator,
                    note,
                )
            )
        warnings = [
            "Retrieved policy passages require human review before operational action."
        ]
        if any(chunk.source_type == "portfolio_demo_policy" for chunk in chunks):
            warnings.append(
                "Checked-in portfolio policies are examples, not employer-approved procedures."
            )
        if any(chunk.source_type == "approved_uploaded_policy" for chunk in chunks):
            warnings.append(
                "Uploaded policies are approved only for this local retrieval workspace; verify ownership and currency."
            )
        return ToolResult(
            self.name,
            content,
            [chunk.__dict__ for chunk in chunks],
            citations,
            warnings,
        )


class SurveyRepresentativenessTool:
    name = "survey_representativeness"

    def __init__(self, repository: SurveyRepresentativenessRepository):
        self.repository = repository

    def run(self, request: CopilotRequest) -> ToolResult:
        row = self.repository.summary(request.agent_id, request.stage_id)
        citation_id = f"survey-mix:{request.agent_id}:{request.stage_id}"
        content = [
            (
                f"Full call profile: {row['low_calls']} of {row['calls_analyzed']} calls "
                f"({row['low_share']:.0%}) have low heuristic review priority."
            ),
            (
                f"Synthetic survey coverage: {row['surveys_received']} of "
                f"{row['calls_analyzed']} calls ({row['survey_coverage']:.0%})."
            ),
            (
                f"Surveyed-call mix: {row['surveyed_elevated_calls']} of "
                f"{row['surveys_received']} surveyed calls are medium/high priority versus "
                f"{row['elevated_share']:.0%} across all calls. Signal: "
                f"{row['representativeness_signal']}."
            ),
            f"Interpretation: {row['interpretation']} [{citation_id}]",
        ]
        citation = Citation(
            citation_id,
            "dashboard/survey_representativeness_artifact.json",
            f"agent_summary/{request.agent_id}/{request.stage_id}",
            "Synthetic survey representativeness demo",
        )
        warnings = [
            "The surveys are synthetic fixtures, not real customer feedback.",
            "Heuristic risk is an uncalibrated review proxy, not call quality or agent performance.",
            "Survey response propensity is not modeled; describe possible sample skew, not luck or causation.",
        ]
        return ToolResult(self.name, content, row, [citation], warnings)


class AgentMemoryTool:
    name = "agent_memory"

    def __init__(self, repository: AgentMemoryRepository):
        self.repository = repository

    def run(self, request: CopilotRequest) -> ToolResult:
        row = self.repository.summary(request.agent_id, request.stage_id)
        memory_citation_id = f"agent-memory:{request.agent_id}:{request.stage_id}"
        summary = row["structured_summary"]
        content = [
            f"{summary['headline']} [{memory_citation_id}]",
            f"{summary['risk_context']} [{memory_citation_id}]",
            f"Observed strengths: {summary['observed_strengths']} [{memory_citation_id}]",
            (
                "Coaching opportunities: "
                f"{summary['coaching_opportunities']} [{memory_citation_id}]"
            ),
            f"History boundary: {summary['history_limit']} [{memory_citation_id}]",
        ]
        if row["source_domain_profiles"]:
            context_descriptions = [
                (
                    f"{profile['source_domain']}: {profile['calls_analyzed']} "
                    f"call{'s' if profile['calls_analyzed'] != 1 else ''}, "
                    f"{profile['sample_confidence']} sample confidence; strongest observed "
                    f"behavior {profile['strongest_observed_behavior']['label']} at "
                    f"{profile['strongest_observed_behavior']['call_coverage']:.0%} call coverage"
                )
                for profile in row["source_domain_profiles"]
            ]
            content.append(
                "Dataset source-domain context (not approved business call types): "
                + "; ".join(context_descriptions)
                + f" [{memory_citation_id}]"
            )

        citations = [
            Citation(
                memory_citation_id,
                "dashboard/agent_memory_artifact.json",
                f"agent_memories/{request.agent_id}/{request.stage_id}",
                "Deterministic accumulated Agent Memory v1",
            )
        ]
        evidence_ids = list(
            dict.fromkeys(
                call_id
                for pattern in row["observed_strengths"] + row["coaching_opportunities"]
                for call_id in pattern["supporting_call_ids"] + pattern["missing_call_ids"]
            )
        )
        citations.extend(
            Citation(
                f"memory-call:{call_id}",
                "data/final_outputs/all_calls_summary.csv",
                call_id,
                "Supporting call-level evidence for Agent Memory v1",
            )
            for call_id in evidence_ids
        )
        warnings = [
            "Agent Memory is descriptive portfolio evidence, not an employee score.",
            "All current agent-stage memories have low sample confidence.",
            "Source domains are dataset-derived and are not approved business call types.",
            "No governed dated history exists yet; this is an accumulated call-sequence snapshot.",
            PROXY_WARNING,
        ]
        return ToolResult(self.name, content, row, citations, warnings)


class ToolRouter:
    KPI_TERMS = {
        "kpi",
        "metric",
        "metrics",
        "metrica",
        "metricas",
        "aht",
        "csat",
        "nps",
        "qa",
        "five stars",
        "goal",
        "meta",
        "projection",
        "proyeccion",
    }
    RECAP_TERMS = {"recap", "summary", "resumen", "day", "dia", "turno"}
    CALL_TERMS = {"call", "llamada", "best", "mejor", "coachable", "evidence", "evidencia"}
    COACHING_TERMS = {"advice", "coach", "coaching", "consejo", "improve", "mejorar", "focus"}
    POLICY_TERMS = {"policy", "politica", "compliance", "privacy", "privacidad", "qa"}
    SURVEY_TERMS = {
        "survey",
        "surveys",
        "encuesta",
        "encuestas",
        "representative",
        "representativa",
        "representativo",
        "luck",
        "suerte",
        "feedback",
    }
    MEMORY_TERMS = {
        "memory",
        "memoria",
        "history",
        "historial",
        "historical",
        "pattern",
        "patterns",
        "patron",
        "patrones",
        "strength",
        "strengths",
        "fortaleza",
        "fortalezas",
        "recurrent",
        "recurrente",
        "accumulated",
        "acumulado",
        "analysis of my performance",
        "analisis de mi desempeno",
        "analyze my performance",
    }

    def __init__(
        self,
        repository: DashboardRepository,
        retriever: PolicyRetriever,
        survey_repository: SurveyRepresentativenessRepository | None = None,
        memory_repository: AgentMemoryRepository | None = None,
    ):
        self.repository = repository
        self.retriever = retriever
        self.survey_repository = survey_repository
        self.memory_repository = memory_repository

    @staticmethod
    def _matches(question: str, terms: set[str]) -> bool:
        normalized = question.casefold()
        return any(term in normalized for term in terms)

    def route(self, question: str) -> list[CopilotTool]:
        tools: list[CopilotTool] = []
        if self._matches(question, self.RECAP_TERMS):
            tools.extend(
                [
                    DailyRecapTool(self.repository),
                    KpiLookupTool(self.repository),
                    CallEvidenceTool(self.repository),
                ]
            )
        else:
            if self._matches(question, self.KPI_TERMS):
                tools.append(KpiLookupTool(self.repository))
            if self._matches(question, self.CALL_TERMS):
                tools.append(CallEvidenceTool(self.repository))
            if self._matches(question, self.COACHING_TERMS):
                tools.append(CoachingContextTool(self.repository))
        if self._matches(question, self.POLICY_TERMS | self.COACHING_TERMS):
            tools.append(PolicySearchTool(self.retriever, question))
        if self.survey_repository and self._matches(question, self.SURVEY_TERMS):
            tools.append(SurveyRepresentativenessTool(self.survey_repository))
        if self.memory_repository and self._matches(question, self.MEMORY_TERMS):
            tools.append(AgentMemoryTool(self.memory_repository))
        if not tools:
            tools = [CoachingContextTool(self.repository), PolicySearchTool(self.retriever, question)]

        deduplicated: list[CopilotTool] = []
        names: set[str] = set()
        for tool in tools:
            if tool.name not in names:
                names.add(tool.name)
                deduplicated.append(tool)
        return deduplicated
