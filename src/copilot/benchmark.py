#!/usr/bin/env python3
"""Run Copilot smoke prompts against the configured provider."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from .service import CopilotService


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROMPTS = PROJECT_ROOT / "config" / "copilot_smoke_prompts.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "validation" / "copilot_smoke_results.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompts", type=Path, default=DEFAULT_PROMPTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    prompts = json.loads(args.prompts.read_text(encoding="utf-8"))["prompts"]
    service = CopilotService()
    results = []
    for prompt in prompts:
        started = time.perf_counter()
        response = service.ask(prompt["question"], prompt["agent"], prompt["stage"])
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        results.append(
            {
                **prompt,
                "provider": response.provider,
                "grounded": response.grounded,
                "fallback_reason": response.fallback_reason,
                "tool_calls": response.tool_calls,
                "citation_count": len(response.citations),
                "warning_count": len(response.warnings),
                "latency_ms": elapsed_ms,
                "answer": response.answer,
            }
        )
    latencies = [result["latency_ms"] for result in results]
    fallback_count = sum(result["fallback_reason"] is not None for result in results)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "configured_provider": service.provider.name,
        "prompt_count": len(results),
        "grounded_count": sum(result["grounded"] for result in results),
        "fallback_count": fallback_count,
        "direct_provider_count": len(results) - fallback_count,
        "latency_ms": {
            "average": round(statistics.mean(latencies), 2),
            "median": round(statistics.median(latencies), 2),
            "maximum": round(max(latencies), 2),
        },
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in payload if key != "results"}, indent=2))
    print(f"Results: {args.output}")


if __name__ == "__main__":
    main()
