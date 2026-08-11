# Automated tests

This folder verifies data contracts, aggregation, dashboards, Copilot
grounding, survey safeguards, and human-review utilities.

## Contents

- `fixtures/`: small deterministic inputs used only by tests.
- `test_agent_memory.py`: cumulative stage scope, sample confidence, source
  context, self-history recommendations, evidence links, and Copilot retrieval.
- `test_personalization_evaluation.py`: Phase 5 recommendation variation,
  evidence, confidence, context-proxy, and operational-history boundaries.
- `test_analytical_contract.py`: schema and evidence-boundary validation.
- `test_dashboard_data.py`: population reconciliation and aggregation behavior.
- `test_kpi_dashboard.py`: KPI artifact and portable dashboard checks.
- `test_knowledge_ingestion.py`: TXT, Markdown, DOCX, and PDF ingestion;
  approval gates; business isolation; prompt-injection rejection; and Copilot
  retrieval citations.
- `test_supervisor_dashboard.py`: supervisor artifact and dashboard checks.
- `test_supervisor_agent.py`: bounded planning, team and agent tools, citations,
  and grounding fallback checks.
- `test_streamlit_dashboard.py`: Streamlit loading and interaction smoke tests.
- `test_copilot.py`: routing, retrieval, grounding, fallback, and API behavior.
- `test_copilot_evaluation.py`: prompt-set integrity, rubric scoring,
  completion gates, and report boundaries.
- `test_survey_outcomes.py`: survey provenance, readiness, and training gates.
- `test_survey_representativeness.py`: survey sample-mix calculations and
  interpretation safeguards.
- `test_risk_review_pilot.py`: blinded human-review preparation and evaluation.

Run the complete lightweight suite from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
