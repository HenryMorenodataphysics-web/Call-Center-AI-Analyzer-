import json
import unittest
from types import SimpleNamespace

from src.copilot.evaluation import (
    DEFAULT_CASES,
    gate_results,
    render_report,
    score_response,
)
from src.copilot.models import Citation


class CopilotEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.specification = json.loads(DEFAULT_CASES.read_text(encoding="utf-8"))

    def test_prompt_set_has_thirty_unique_cases_and_both_surfaces(self):
        prompts = self.specification["prompts"]
        self.assertEqual(len(prompts), 30)
        self.assertEqual(len({prompt["id"] for prompt in prompts}), 30)
        self.assertEqual({prompt["surface"] for prompt in prompts}, {"agent", "supervisor"})
        self.assertTrue(
            all(
                prompt.get("expected_tools") or prompt.get("expected_tools_any")
                for prompt in prompts
            )
        )

    def test_score_requires_tools_citations_context_and_concepts(self):
        case = {
            "id": "test",
            "surface": "agent",
            "expected_context": "Agent_001",
            "expected_tools": ["kpi_lookup"],
            "min_citations": 1,
            "required_any": [["estimated aht"], ["600"]],
            "forbidden_regex": [r"official score is 999"],
            "tags": ["actionable", "personalized"],
        }
        citation = Citation(
            "kpi:Agent_001:end:estimated-aht",
            "dashboard/artifact.json",
            "kpi_status/Agent_001/end/Estimated AHT",
            "proxy",
        )
        response = SimpleNamespace(
            answer=(
                "Estimated AHT is above 600. Focus on the cited evidence "
                "[kpi:Agent_001:end:estimated-aht]"
            ),
            grounded=True,
            tool_calls=["kpi_lookup"],
            citations=[citation],
            warnings=[],
            fallback_reason=None,
            agent_id="Agent_001",
            provider="llama_cpp_server",
        )
        result = score_response(case, response, 100.0)
        self.assertTrue(all(result["checks"].values()))
        self.assertTrue(result["safe_pass"])

    def test_gate_results_fail_when_a_required_rate_is_below_threshold(self):
        rates = {
            "tool_routing": 0.95,
            "citation_count": 1.0,
            "citation_markers": 1.0,
            "required_concepts": 0.9,
            "forbidden_claims": 1.0,
            "numeric_grounding": 1.0,
            "actionability": 0.75,
            "personalization": 1.0,
        }
        qwen = {
            "safe_pass_rate": 1.0,
            "critical_safe_pass_rate": 1.0,
            "rates": rates,
        }
        gates = gate_results(qwen, self.specification["completion_gates"])
        self.assertEqual(gates["status"], "fail")
        self.assertFalse(gates["checks"]["actionability_rate"]["pass"])

    def test_report_discloses_default_and_limits(self):
        provider_summary = {
            "safe_pass_rate": 1.0,
            "direct_provider_rate": 1.0,
            "fallback_count": 0,
            "latency_ms": {"median": 1000.0, "p95": 2000.0},
            "results": [],
        }
        payload = {
            "status": "pass",
            "generated_at": "2026-08-11T00:00:00+00:00",
            "prompt_set_version": "1.0.0",
            "prompt_count": 30,
            "providers": {"llama_cpp_server": provider_summary},
            "gates": {
                "checks": {
                    "safe_pass_rate": {"actual": 1.0, "required": 0.95, "pass": True}
                }
            },
            "decision": {
                "application_default": "deterministic",
                "selected_local_model": "Qwen3-4B-Q4_K_M",
                "deployment_position": "Post-call explanation.",
            },
        }
        report = render_report(payload)
        self.assertIn("Portfolio application default: **deterministic**", report)
        self.assertIn("not human preference scoring", report)


if __name__ == "__main__":
    unittest.main()
