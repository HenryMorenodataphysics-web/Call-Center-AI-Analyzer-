# Agent Memory v1.1

## Purpose

Agent Memory v1 gives the Copilot a deterministic summary of the selected
agent's accumulated analyzed calls. The memory is stored outside the LLM, so it
can be audited, rebuilt, and reused with a different model provider.

## Current artifact

`dashboard/agent_memory_artifact.json` contains one row for every agent and
portfolio stage:

- `start`: first 3 calls in agent call-number order;
- `live`: first 7 calls;
- `end`: all 10 calls.

This produces 30 cumulative agent-stage memories over the current 100-call,
10-agent sample. A stage never reads calls that occur later in the portfolio
sequence.

Each row contains:

- sample scope and confidence;
- low, medium, and high heuristic review-priority mix;
- empathy, probing, ownership, and next-steps coverage;
- observed strengths that meet portfolio coaching benchmarks;
- coaching opportunities with the largest benchmark gaps;
- supporting and missing-evidence call IDs;
- dataset-derived source-domain profiles;
- a structured summary for controlled Copilot retrieval.
- stage-to-stage behavior-coverage changes against the agent's own prior stage;
- one personalized coaching focus, action, reason codes, time window, and call evidence;
- an optional dataset-derived context selected only when it contains at least three calls.

The recommendation uses only the selected agent's accumulated evidence. It does
not rank agents or claim that an observed behavior caused an outcome.

## Important boundaries

- All current memories have **low sample confidence** because the portfolio has
  at most 10 calls per agent. The thresholds are 20 calls for moderate and 50
  for high sample confidence.
- The dataset provides call sequence, not governed event timestamps. The
  artifact is therefore an initial accumulated snapshot, not a dated
  longitudinal employment record.
- Source domains such as Banking or Aviation are parsed from dataset call IDs.
  They are not approved business call types.
- The behavior targets are portfolio coaching benchmarks, not employer policy.
- Conversation risk remains an uncalibrated review-priority proxy, not agent
  quality, CSAT, QA, or survey probability.
- Agent Memory must not support automated discipline, compensation, hiring, or
  termination decisions.

## Build

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m src.personalization.build_agent_memory
```

The builder reads:

- `data/final_outputs/all_calls_summary.csv`;
- `config/demo_kpi_targets.json`;
- `config/agent_memory_contract_v1.json`.

## Copilot behavior

Questions containing concepts such as memory, history, accumulated patterns,
or strengths route to the controlled `agent_memory` tool. The tool selects only
the active agent and stage, returns structured evidence, and cites both the
memory row and supporting canonical calls. It now also returns the personalized
focus and states whether it is an initial baseline or a change from the prior
stage. Deterministic and Qwen providers use the same tool output and guardrails.

## Phase 5 evaluation

Run the fixed portfolio evaluation after rebuilding Agent Memory:

```powershell
.\.venv\Scripts\python.exe -m src.personalization.evaluate_personalization
```

The versioned evaluation checks recommendation variation across agents and
stages, call evidence, confidence labels, prior-stage trends, context-proxy
labels, and the absence of fabricated dates. Its outputs are:

- `data/validation/personalization_evaluation_results.json`;
- `reports/personalization_evaluation_report.md`.

The portfolio gate passes. The separate operational gate remains blocked as
`NO_GOVERNED_DATED_HISTORY`.

## Not included in v1

- persisted dated snapshots across real days or weeks;
- approved business call taxonomy and complexity labels;
- governed context-matched peer comparisons;
- cross-agent suggestions;
- causal explanations;
- calibrated outcome predictions.

Those capabilities require the business-aware foundation, more observations,
and stronger validation gates.
