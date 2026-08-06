# Dashboard artifacts

- `kpi_performance_tracker.html` is the self-contained KPI dashboard.
- `artifact.json` is its canonical source manifest and bounded snapshot.
- `supervisor_board.html` is the self-contained Supervisor Board.
- `supervisor_artifact.json` is the Supervisor Board's canonical manifest and
  bounded snapshot.
- `survey_representativeness_artifact.json` compares the complete analyzed-call
  mix with the subset linked to synthetic survey fixtures.
- `agent_memory_artifact.json` stores the 30 cumulative Agent Memory v1 rows for
  10 agents across start, live, and end views.

Open the HTML directly in a modern browser. No local server, CDN, API key, or
network request is required.

Use the Agent and Shift view filters to inspect every agent across the start,
live, and end views.

The `fixture` status is intentional: CSAT, QA, NPS, and Five Stars are
synthetic demo values. Estimated AHT and conversation risk are also labeled as
proxies. See `docs/kpi_performance_tracker.md` for definitions and limitations.

The Supervisor Board uses the same 100 analyzed calls but excludes synthetic
CSAT, QA, NPS, and Five Stars from its team view. Its attention categories are
review aids derived from AHT and risk proxy statuses, not employee rankings.
See `docs/supervisor_board.md` for details.

The Streamlit application in `app/dashboard.py` is the primary interface. These
HTML files remain portable fallbacks, while the JSON files are checked-in,
auditable inputs used by the Streamlit views.
