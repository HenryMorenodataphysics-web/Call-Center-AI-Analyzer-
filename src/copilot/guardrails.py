"""Post-generation checks that protect numerical and source grounding."""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation

from .models import ToolResult


NUMBER_RE = re.compile(r"(?<![A-Za-z_])-?\d+(?:\.\d+)?")
CITATION_RE = re.compile(r"\[[^\]]+\]")


def normalized_numbers(text: str) -> set[Decimal]:
    values: set[Decimal] = set()
    for raw in NUMBER_RE.findall(text):
        try:
            values.add(Decimal(raw).normalize())
        except InvalidOperation:
            continue
    return values


def validate_generated_answer(answer: str, question: str, results: list[ToolResult]) -> tuple[bool, str | None]:
    """Reject model answers that introduce numbers absent from grounded context."""

    context = json.dumps(
        [result.to_prompt_dict() for result in results],
        ensure_ascii=False,
        default=str,
    )
    allowed = normalized_numbers(context) | normalized_numbers(question)
    answer_without_citations = CITATION_RE.sub("", answer)
    introduced = normalized_numbers(answer_without_citations) - allowed
    if introduced:
        values = ", ".join(str(value) for value in sorted(introduced))
        return False, f"provider introduced unsupported numeric values: {values}"

    lower = answer.casefold()
    official_claim = re.search(
        r"official\s+(?:csat|nps|qa)(?:\s+score)?\s*(?:is|=|:)", lower
    )
    if official_claim and not any(
        phrase in lower for phrase in ("unavailable", "not official", "no official")
    ):
        return False, "provider presented a demo outcome as official"

    context_lower = context.casefold()
    appeared_values = re.findall(r"appeared in\s+(\d+(?:\.\d+)?)%", context_lower)
    for value in appeared_values:
        if re.search(rf"(?:missing|absent)\s+in\s+{re.escape(value)}%", lower):
            return False, "provider inverted an observed behavior coverage statement"
    return True, None
