# Versioned configuration and contracts

This folder defines how analytical records, Copilot behavior, demo targets,
and survey outcomes are interpreted. Configuration belongs here; calculated
results belong in `dashboard/`, `data/`, or `reports/`.

## Files

- `analytical_contract_v1.json`: schemas, field meanings, evidence boundaries,
  and validation rules for the analytical pipeline.
- `agent_memory_contract_v1.json`: behavior definitions, sample-confidence
  thresholds, evidence requirements, and Agent Memory guardrails.
- `copilot_config.json`: active Copilot provider and local generation settings.
- `copilot_contract_v1.json`: supported Copilot tools, grounding requirements,
  warnings, and response rules.
- `copilot_smoke_prompts.json`: small prompt set used to verify the optional
  local model.
- `copilot_evaluation_prompts_v1.json`: 30-case Phase 4 evaluation set and
  completion thresholds for both Copilot surfaces.
- `personalization_evaluation_v1.json`: fixed Phase 5 recommendation-variation,
  evidence, confidence, context, and self-history gates.
- `cross_agent_learning_contract_v1.json`: Phase 6 context matching, anonymous
  evidence thresholds, technique definitions, and operational guardrails.
- `cross_agent_learning_evaluation_v1.json`: fixed Phase 6 evidence,
  anonymization, noncausal-language, and early-stage leakage gates.
- `demo_kpi_targets.json`: clearly labeled demonstration targets used by the KPI
  dashboard; they are not employer targets.
- `knowledge_ingestion_contract_v1.json`: approved formats, metadata, storage,
  chunking, approval states, and upload security guardrails.
- `survey_outcome_contract_v1.json`: governed schema and readiness gates for
  real survey labels when available.

Changes to these files can change metric meaning or system behavior and should
therefore be versioned and tested.
