import json
import threading
import unittest
import urllib.request
from unittest.mock import patch

from src.copilot.models import ToolResult
from src.copilot.providers import CopilotProvider, LlamaCppServerProvider
from src.copilot.repository import DashboardRepository
from src.copilot.retrieval import PolicyRetriever
from src.copilot.service import CopilotService
from src.copilot.tools import KpiLookupTool, PolicySearchTool, ToolRouter
from src.copilot.models import CopilotRequest
from src.copilot.web_app import build_server


class HallucinatingProvider(CopilotProvider):
    name = "hallucinating_test_provider"

    def generate(self, question: str, results: list[ToolResult]) -> str:
        del question, results
        return "Your official score is 999 and everything is perfect."


class InvertingProvider(CopilotProvider):
    name = "inverting_test_provider"

    def generate(self, question: str, results: list[ToolResult]) -> str:
        del question, results
        return "Next steps were missing in 14% of calls."


class CopilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repository = DashboardRepository()
        cls.retriever = PolicyRetriever()

    def test_agent_resolution_by_id_and_name(self):
        by_id = self.repository.resolve_agent("Agent_001")
        by_name = self.repository.resolve_agent("Joyce Martinez")
        self.assertEqual(by_id, by_name)

    def test_unknown_agent_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown agent"):
            self.repository.resolve_agent("Nobody")

    def test_kpi_tool_preserves_synthetic_provenance(self):
        result = KpiLookupTool(self.repository).run(
            CopilotRequest("What is my CSAT?", "Agent_001", "live")
        )
        synthetic = [row for row in result.data if row["source_type"] == "synthetic_demo"]
        self.assertEqual(len(synthetic), 1)
        self.assertTrue(all("synthetic demo" in row["metric"].casefold() for row in synthetic))
        self.assertTrue(any("not official" in warning for warning in result.warnings))

    def test_official_kpi_question_withholds_synthetic_value(self):
        result = KpiLookupTool(self.repository).run(
            CopilotRequest("What is my official CSAT?", "Agent_003", "live")
        )
        self.assertIn("Official CSAT is unavailable", result.content[0])
        self.assertIn("value is withheld", result.content[0])
        self.assertNotIn(str(result.data[0]["current"]), result.content[0])

    def test_daily_recap_limits_kpis_to_three(self):
        result = KpiLookupTool(self.repository).run(
            CopilotRequest("Give me my daily recap", "Agent_001", "live")
        )
        self.assertEqual(len(result.data), 3)
        self.assertEqual(
            [row["metric"] for row in result.data],
            ["Estimated AHT", "CSAT - synthetic demo", "QA - synthetic demo"],
        )

    def test_local_provider_sends_api_key(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"choices":[{"message":{"content":"Grounded answer"}}]}'

        provider = LlamaCppServerProvider(api_key="local-test-key")
        with patch("urllib.request.urlopen", return_value=FakeResponse()) as mocked:
            provider.generate("What should I focus on?", [])
        request = mocked.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer local-test-key")

    def test_policy_retrieval_returns_portfolio_sources(self):
        result = PolicySearchTool(self.retriever, "How should I improve AHT safely?").run(
            CopilotRequest("How should I improve AHT safely?", "Agent_001", "live")
        )
        self.assertTrue(result.content)
        self.assertTrue(all(citation.id.startswith("policy:") for citation in result.citations))
        self.assertNotIn("README.md", {citation.source for citation in result.citations})

    def test_router_uses_controlled_tools(self):
        names = [
            tool.name
            for tool in ToolRouter(self.repository, self.retriever).route(
                "Give me my daily recap and best call"
            )
        ]
        self.assertEqual(names, ["daily_recap", "kpi_lookup", "call_evidence"])

    def test_deterministic_copilot_returns_grounded_recap(self):
        response = CopilotService().ask("Give me my daily recap", "Agent_001", "live")
        self.assertTrue(response.grounded)
        self.assertEqual(response.provider, "deterministic")
        self.assertIsNone(response.fallback_reason)
        self.assertIn("Daily recap", response.answer)
        self.assertIn("Evidence:", response.answer)
        self.assertIn("daily_recap", response.tool_calls)

    def test_unsupported_number_triggers_safe_fallback(self):
        response = CopilotService(provider=HallucinatingProvider()).ask(
            "Give me coaching advice", "Agent_001", "live"
        )
        self.assertEqual(response.provider, "deterministic")
        self.assertIn("unsupported numeric values", response.fallback_reason)
        self.assertNotIn("999", response.answer)

    def test_inverted_behavior_coverage_triggers_safe_fallback(self):
        response = CopilotService(provider=InvertingProvider()).ask(
            "What should I focus on next?", "Agent_005", "live"
        )
        self.assertEqual(response.provider, "deterministic")
        self.assertIn("inverted an observed behavior coverage", response.fallback_reason)

    def test_call_evidence_citations_reference_valid_call_ids(self):
        response = CopilotService().ask("Show my best call", "Agent_001", "end")
        call_citations = [citation for citation in response.citations if citation.id.startswith("call:")]
        self.assertEqual(len(call_citations), 2)
        self.assertTrue(all(citation.locator for citation in call_citations))

    def test_local_web_api_serves_agents_and_grounded_chat(self):
        server = build_server(port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            with urllib.request.urlopen(f"{base_url}/api/agents", timeout=5) as response:
                agents = json.loads(response.read().decode("utf-8"))
            self.assertEqual(len(agents["agents"]), 10)

            request = urllib.request.Request(
                f"{base_url}/api/chat",
                data=json.dumps(
                    {
                        "agent": "Agent_001",
                        "stage": "live",
                        "question": "Show my best call",
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                chat = json.loads(response.read().decode("utf-8"))
            self.assertTrue(chat["grounded"])
            self.assertIn("call_evidence", chat["tool_calls"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
