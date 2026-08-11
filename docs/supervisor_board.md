# Supervisor Team Performance Board MVP

The Supervisor Board gives a team lead a summary-first view of where evidence
deserves attention, which behaviors need coaching support, and which calls can
be reviewed or shared. It runs entirely from the existing analytical outputs;
the local Qwen model and Copilot are not started or required.

The integrated Streamlit application also includes an optional **Supervisor
Copilot**. It reads this same artifact through controlled tools for team
metrics, agent-versus-team context, coaching queues, review calls, and
descriptive statistics. It can additionally reuse Agent Memory and policy
retrieval when a specific agent or policy question requires them. A Phase 6
tool retrieves anonymous recurring technique candidates from matched contexts.

In deterministic mode, a safe router selects tools without starting a model.
In Local Qwen mode, the model may plan at most four calls from the fixed
read-only catalog; invalid or unavailable plans fall back to the deterministic
router. The model never receives raw SQL access and all numerical claims remain
subject to the existing grounding validator.

## What the MVP includes

- Start, live, and end simulated shift views covering 30, 70, and 100 calls.
- Team health cards for calls reviewed, triage volume, estimated AHT, heuristic
  risk, and next-steps coverage.
- Agent proxy map comparing estimated AHT with heuristic conversation risk.
- Team distribution across Needs attention, Watch, and On track review states.
- Team behavior coverage versus portfolio coaching benchmarks.
- Explainable coaching queue with one action and guardrail per agent.
- Agent context table for exact proxy values and focus areas.
- Best-call and coachable-call examples with call IDs, reason codes, and turn
  evidence.
- Seven anonymous technique candidates across four exact end-view
  language-market and source-domain contexts, with canonical call evidence and
  explicit low-confidence limits.

## Triage definition

Triage uses only the existing Estimated AHT and Heuristic risk statuses:

- `Needs attention`: at least one proxy has Needs attention status.
- `Watch`: neither proxy needs attention and at least one has Watch status.
- `On track`: both proxies are within their portfolio thresholds.

These categories order evidence review. They are not a performance ranking,
official QA decision, disciplinary finding, or customer-outcome prediction.
Supervisor Copilot preserves the same boundary and requires human inspection
of cited call evidence before action.

## Data boundary

The board intentionally excludes synthetic CSAT, QA, NPS, and Five Stars.
Estimated AHT remains an audio-duration proxy, conversation risk remains an
uncalibrated heuristic, and behavior coverage remains rule-based. A missing
behavior flag does not prove the behavior was absent.

Every shift view gives each agent the same number of calls, so the team AHT and
risk values are arithmetic means of agent means and reconcile to the underlying
call-level mean. Goals and behavior benchmarks remain portfolio assumptions from
`config/demo_kpi_targets.json`.

Cross-agent candidates require at least four calls and two agents in the exact
context, with each behavior recurring in at least two calls from two agents.
They are not best practices, rankings, causal effects, or validated outcome
improvements. Operational outcome learning remains blocked by
`NO_GOVERNED_OUTCOMES_FOR_CROSS_AGENT_LEARNING`.

## Build and validation

Build the canonical artifact from the project root:

```powershell
python -m src.dashboard.build_supervisor_dashboard
```

This writes `dashboard/supervisor_artifact.json`. The delivered
`dashboard/supervisor_board.html` was generated with the Data Analytics portable
artifact builder and is self-contained: no server, network connection, API key,
or LLM is required.

The artifact passed canonical validation, packaging, payload-equality checks,
and structural verification. Automated browser-level QA was unavailable because
no compatible Chromium headless executable was installed; the semantic fallback
is embedded and readable without the enhanced runtime.
