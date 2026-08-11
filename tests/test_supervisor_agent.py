import json
import unittest
from unittest.mock import patch

from src.copilot.models import ToolResult
from src.copilot.providers import CopilotProvider, LlamaCppServerProvider
from src.copilot.supervisor_agent import (
    LlamaCppSupervisorPlanner,
    SupervisorAgentService,
    SupervisorRepository,
    SupervisorToolRouter,
)
from src.copilot.retrieval import PolicyRetriever
from src.personalization.build_agent_memory import AgentMemoryRepository


class HallucinatingSupervisorProvider(CopilotProvider):
    name = "hallucinating_supervisor_test"

    def generate(self, question: str, results: list[ToolResult]) -> str:
        del question, results
        return "The official team performance score is 999."


class SupervisorAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repository = SupervisorRepository()
        cls.router = SupervisorToolRouter(
            cls.repository,
            PolicyRetriever(),
            AgentMemoryRepository(),
        )

    def test_team_question_routes_to_metrics_and_statistics(self):
        names = [
            tool.name
            for tool in self.router.tools(
                "Resume la salud del equipo y sus datos estadísticos", "team"
            )
        ]
        self.assertEqual(names, ["team_metrics", "team_statistics"])

    def test_team_scope_rejects_agent_only_model_tools(self):
        names = [
            tool.name
            for tool in self.router.tools(
                "Compare performance",
                "team",
                ["agent_team_comparison", "agent_memory", "team_metrics"],
            )
        ]
        self.assertEqual(names, ["team_metrics"])

    def test_agent_comparison_is_grounded_and_descriptive(self):
        response = SupervisorAgentService().ask(
            "Compare this agent with the team", "end", "Agent_004"
        )
        self.assertEqual(response.agent_id, "Agent_004")
        self.assertIn("agent_team_comparison", response.tool_calls)
        self.assertIn("descriptive difference", response.answer)
        self.assertIn("dashboard/supervisor_artifact.json", response.citations[0].source)
        self.assertTrue(any("not adjust" in warning for warning in response.warnings))

    def test_team_call_review_returns_bounded_cited_evidence(self):
        response = SupervisorAgentService().ask(
            "Show the best calls for team feedback", "end"
        )
        self.assertEqual(response.tool_calls, ["team_metrics", "coaching_queue", "review_calls"])
        call_citations = [
            citation
            for citation in response.citations
            if citation.id.startswith("supervisor-call:")
        ]
        self.assertGreaterEqual(len(call_citations), 1)
        self.assertLessEqual(len(call_citations), 4)

    def test_unsupported_number_uses_safe_fallback(self):
        response = SupervisorAgentService(
            provider=HallucinatingSupervisorProvider()
        ).ask("Summarize team health", "end")
        self.assertEqual(response.provider, "deterministic")
        self.assertIn("unsupported numeric values", response.fallback_reason)
        self.assertNotIn("999", response.answer)

    def test_local_qwen_planner_returns_only_valid_bounded_tools(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                content = '["team_metrics", "review_calls", "unknown_tool"]'
                return json.dumps(
                    {"choices": [{"message": {"content": content}}]}
                ).encode("utf-8")

        provider = LlamaCppServerProvider(api_key="planner-test-key")
        with patch("urllib.request.urlopen", return_value=FakeResponse()) as mocked:
            names = LlamaCppSupervisorPlanner(provider).plan(
                "Show team metrics and calls", has_agent=False
            )
        self.assertEqual(names, ["team_metrics", "review_calls"])
        request = mocked.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer planner-test-key")


if __name__ == "__main__":
    unittest.main()
