"""Shared data structures for the copilot."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Citation:
    id: str
    source: str
    locator: str
    note: str


@dataclass
class ToolResult:
    name: str
    content: list[str]
    data: Any
    citations: list[Citation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "tool": self.name,
            "content": self.content,
            "citations": [asdict(citation) for citation in self.citations],
            "warnings": self.warnings,
        }


@dataclass(frozen=True)
class CopilotRequest:
    question: str
    agent_id: str
    stage_id: str = "live"


@dataclass
class CopilotResponse:
    answer: str
    agent_id: str
    stage_id: str
    provider: str
    tool_calls: list[str]
    citations: list[Citation]
    warnings: list[str]
    grounded: bool
    fallback_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload
