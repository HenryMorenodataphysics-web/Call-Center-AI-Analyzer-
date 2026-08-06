"""Grounded orchestration layer for the local Customer Service copilot."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .guardrails import validate_generated_answer
from .models import Citation, CopilotRequest, CopilotResponse
from .providers import (
    CopilotProvider,
    DeterministicProvider,
    LlamaCppServerProvider,
    ProviderError,
)
from .repository import DEFAULT_ARTIFACT_PATH, DashboardRepository
from .retrieval import DEFAULT_KNOWLEDGE_DIR, PolicyRetriever
from .tools import ToolRouter
from src.outcomes.survey_representativeness import SurveyRepresentativenessRepository
from src.personalization.build_agent_memory import AgentMemoryRepository


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "copilot_config.json"
DEFAULT_LOCAL_API_KEY_PATH = PROJECT_ROOT / ".runtime" / "copilot_api_key.txt"


def unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def local_api_key() -> str | None:
    environment_key = os.environ.get("COPILOT_API_KEY", "").strip()
    if environment_key:
        return environment_key
    if DEFAULT_LOCAL_API_KEY_PATH.exists():
        file_key = DEFAULT_LOCAL_API_KEY_PATH.read_text(encoding="utf-8").strip()
        return file_key or None
    return None


class CopilotService:
    def __init__(
        self,
        artifact_path: Path = DEFAULT_ARTIFACT_PATH,
        knowledge_dir: Path = DEFAULT_KNOWLEDGE_DIR,
        business_id: str = "demo_customer_service",
        knowledge_runtime_root: Path | None = None,
        config_path: Path = DEFAULT_CONFIG_PATH,
        provider: CopilotProvider | None = None,
    ):
        self.config = json.loads(config_path.read_text(encoding="utf-8"))
        self.repository = DashboardRepository(artifact_path)
        self.retriever = PolicyRetriever(
            knowledge_dir,
            business_id=business_id,
            runtime_root=knowledge_runtime_root,
        )
        self.survey_repository = SurveyRepresentativenessRepository()
        self.memory_repository = AgentMemoryRepository()
        self.router = ToolRouter(
            self.repository,
            self.retriever,
            self.survey_repository,
            self.memory_repository,
        )
        self.fallback_provider = DeterministicProvider()
        self.provider = provider or self._provider_from_config()

    def _provider_from_config(self) -> CopilotProvider:
        provider_name = os.environ.get(
            "COPILOT_PROVIDER", self.config.get("default_provider", "deterministic")
        )
        if provider_name == "deterministic":
            return DeterministicProvider()
        if provider_name == "llama_cpp_server":
            server = self.config["llama_cpp_server"]
            generation = self.config["generation"]
            return LlamaCppServerProvider(
                base_url=os.environ.get("COPILOT_BASE_URL", server["base_url"]),
                model=server["model"],
                temperature=generation["temperature"],
                max_tokens=generation["max_tokens"],
                timeout_sec=generation["timeout_sec"],
                api_key=local_api_key(),
            )
        raise ValueError(f"Unsupported copilot provider: {provider_name}")

    def ask(self, question: str, agent: str, stage: str = "live") -> CopilotResponse:
        if not question.strip():
            raise ValueError("Question must not be empty")
        agent_record = self.repository.resolve_agent(agent)
        stage_id = self.repository.validate_stage(stage)
        request = CopilotRequest(question.strip(), agent_record["agent_id"], stage_id)
        tools = self.router.route(request.question)
        results = [tool.run(request) for tool in tools]

        fallback_reason: str | None = None
        provider_name = self.provider.name
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

        citations: list[Citation] = []
        for result in results:
            citations.extend(result.citations)
        citations = list({citation.id: citation for citation in citations}.values())
        warnings = unique([warning for result in results for warning in result.warnings])

        citation_footer = "Evidence: " + ", ".join(f"[{citation.id}]" for citation in citations)
        if citations and not all(f"[{citation.id}]" in answer for citation in citations):
            answer = answer.rstrip() + "\n\n" + citation_footer
        if warnings:
            answer = answer.rstrip() + "\n\nLimits:\n- " + "\n- ".join(warnings)

        return CopilotResponse(
            answer=answer,
            agent_id=request.agent_id,
            stage_id=request.stage_id,
            provider=provider_name,
            tool_calls=[result.name for result in results],
            citations=citations,
            warnings=warnings,
            grounded=True,
            fallback_reason=fallback_reason,
        )
