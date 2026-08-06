# Business-aware architecture and restructuring map

## Decision

AI Analyzer Core will remain a regular Python application rather than a
notebook project. The current local Qwen model also remains unchanged. Business
adaptation, analytical memory, and policy context will live outside the LLM so
a future deployment can replace the model or run it on NVIDIA infrastructure
without rewriting the deterministic product logic.

The migration must be incremental. Existing modules and paths continue working
until the replacement path has tests and the reproducibility workflow passes.

## Target architecture

```text
Business profile and governed knowledge
                   |
                   v
Raw call -> observed signals -> contextual analysis -> validated evidence
                                                |             |
                                                v             v
                                      Agent Memory      Supervisor patterns
                                                \             /
                                                 v           v
                                           Controlled tools
                                                  |
                                                  v
                                    Deterministic or LLM provider
                                                  |
                                                  v
                                      Evidence-cited explanation
```

The deterministic layers calculate metrics and select evidence. The LLM only
explains the retrieved context. Agent memory is a versioned analytical artifact,
not hidden state stored inside the model.

## Target repository structure

```text
app/
  dashboard.py

config/
  core/
    contracts/
    runtime/
    evaluation/
  businesses/
    demo_customer_service/
      business_profile_v1.json
      call_taxonomy_v1.json
      kpi_targets_v1.json
      coaching_rules_v1.json

knowledge_base/
  shared/
  businesses/
    demo_customer_service/
      v1/
        compliance_guardrails.md
        customer_service_playbook.md
        qa_policy_demo.md

src/
  core/
    project_paths.py
  business/
    models.py
    repository.py
    validator.py
  personalization/
    models.py
    build_agent_memory.py
    repository.py
  [existing pipeline and product packages]

dashboard/
  artifact.json
  supervisor_artifact.json
  survey_representativeness_artifact.json
  agent_memory_artifact.json

data/
  [existing pipeline stages]
  personalization/
    agent_memory_history.jsonl
```

The existing pipeline packages under `src/` remain in place during this
iteration. Moving working packages into broader folders such as `pipeline/` or
`analytics/` would add import churn without changing product capability. Their
responsibilities are already explained in `src/README.md`.

## Exact configuration migration map

| Current path | Target path | Consumers that must change |
| --- | --- | --- |
| `config/analytical_contract_v1.json` | `config/core/contracts/analytical_contract_v1.json` | `src/contracts/analytical_contract.py`, tests, documentation |
| `config/copilot_contract_v1.json` | `config/core/contracts/copilot_contract_v1.json` | Copilot validation, tests, documentation |
| `config/survey_outcome_contract_v1.json` | `config/core/contracts/survey_outcome_contract_v1.json` | `src/outcomes/survey_dataset.py`, tests, documentation |
| `config/copilot_config.json` | `config/core/runtime/copilot_config.json` | `src/copilot/service.py`, `app/dashboard.py`, tests, scripts |
| `config/copilot_smoke_prompts.json` | `config/core/evaluation/copilot_smoke_prompts.json` | `src/copilot/benchmark.py`, documentation |
| `config/demo_kpi_targets.json` | `config/businesses/demo_customer_service/kpi_targets_v1.json` | KPI and survey artifact builders, tests, citations, documentation |

These files must not be moved first. The safe sequence is to introduce a
central path resolver, update consumers to use it, run tests, and only then move
the files.

## Exact knowledge-base migration map

| Current path | Target path |
| --- | --- |
| `knowledge_base/compliance_guardrails.md` | `knowledge_base/businesses/demo_customer_service/v1/compliance_guardrails.md` |
| `knowledge_base/customer_service_playbook.md` | `knowledge_base/businesses/demo_customer_service/v1/customer_service_playbook.md` |
| `knowledge_base/qa_policy_demo.md` | `knowledge_base/businesses/demo_customer_service/v1/qa_policy_demo.md` |

`src/copilot/retrieval.py` will resolve only the active business and approved
shared documents. Citations will retain the business ID, knowledge version,
document path, and section so an answer can be audited after policies change.

## Business profile contract

Every deployment will select one versioned business profile. The minimum
contract is:

```json
{
  "schema_version": "business_profile_v1",
  "business_id": "demo_customer_service",
  "display_name": "Demo Customer Service",
  "profile_version": "1.0.0",
  "status": "portfolio_demo",
  "default_language": "en",
  "supported_languages": ["en"],
  "market": "demo",
  "call_taxonomy_path": "call_taxonomy_v1.json",
  "kpi_targets_path": "kpi_targets_v1.json",
  "coaching_rules_path": "coaching_rules_v1.json",
  "knowledge_base_version": "v1",
  "comparison_dimensions": [
    "call_type",
    "complexity",
    "language",
    "market"
  ],
  "required_context_fields": [
    "business_id",
    "call_type",
    "complexity",
    "language",
    "market"
  ]
}
```

The profile points to other versioned files instead of embedding every rule in
one large document.

### Call taxonomy

`call_taxonomy_v1.json` defines the call types that are meaningful to that
business. Each type contains:

- stable call-type ID and display name;
- allowed complexity levels and assignment method;
- expected service steps;
- relevant behaviors and evidence requirements;
- escalation conditions;
- minimum sample size for comparisons.

Unknown or unclassified calls remain valid but cannot be used for strong
context-matched recommendations.

### KPI targets

`kpi_targets_v1.json` defines the metric, target, direction, unit, source type,
freshness expectation, and guardrails. Real, synthetic, proxy, and unavailable
values remain explicitly different.

### Coaching and red-flag rules

`coaching_rules_v1.json` defines required behaviors, prohibited actions,
severity, evidence thresholds, escalation routing, and whether human
confirmation is mandatory. A rule match creates a review flag; it does not
automatically establish misconduct.

The existing `conversation_risk_v1` remains unchanged and uncalibrated until a
separate, validated business-specific rubric is approved.

## Runtime context

Every analysis and Copilot request will resolve a `BusinessContext` containing:

```text
business_id
profile_version
knowledge_base_version
call_type
complexity
language
market
context_confidence
context_source
```

For the current dataset, unavailable dimensions will be recorded as `unknown`
rather than inferred without evidence. Recommendations that require an unknown
dimension will be labeled low confidence or withheld.

## Component responsibilities

### `src/core/project_paths.py`

- resolves core and business-specific files from the repository root;
- prevents path constants from being duplicated across modules;
- validates that resolved business paths stay inside approved directories;
- provides compatibility aliases during migration.

### `src/business/models.py`

- typed records for the business profile and runtime context;
- no file access and no metric calculation.

### `src/business/repository.py`

- loads the selected business profile and referenced configuration;
- exposes approved knowledge-base directories;
- caches immutable versioned configuration.

### `src/business/validator.py`

- checks required fields, referenced files, unique IDs, allowed source types,
  and valid knowledge versions;
- blocks startup or artifact generation when the active profile is invalid.

### Existing analyzers

- continue extracting observed text and acoustic signals;
- receive business context only where interpretation depends on the business;
- do not import Streamlit, the LLM provider, or Agent Memory.

### Copilot

- receives the resolved business and agent context;
- retrieves only approved evidence and policies for that context;
- remains provider-independent and keeps deterministic fallback behavior.

## Migration phases

### R1 - Business contract foundation

Add the path resolver, business models, repository, validator, demo profile,
taxonomy, and coaching rules. Keep existing configuration paths operational.

**Gate:** business-profile validation and all existing tests pass.

### R2 - Business-aware knowledge retrieval

Create the versioned knowledge-base hierarchy, update the retriever and
citations, then remove compatibility aliases after all consumers use the new
location.

**Gate:** policy searches return only the selected business and retain auditable
versioned citations.

### R3 - Business-aware dashboard and pipeline context

Add `business_id` and context fields to generated artifacts. Unknown fields are
explicit and do not fabricate call classifications.

**Gate:** all dashboard populations still reconcile to 100 calls and existing
metric values do not change solely because of the migration.

### R4 - Agent Memory v1

Build deterministic, versioned agent summaries partitioned by business and
context. Add a controlled Copilot memory tool only after the artifact passes
contract and evidence checks.

**Gate:** every memory statement has a time window, sample size, confidence,
reason code, and supporting call IDs.

### R5 - Context-matched cross suggestions

Compare similar calls, extract anonymized transferable behaviors, and present
associations rather than causal claims or whole-person rankings.

**Gate:** comparisons enforce minimum sample size and matching dimensions, hide
peer identity, and expose uncertainty.

## Files affected by the first implementation phase

R1 is intentionally smaller than the complete migration.

### New files

- `src/core/__init__.py`
- `src/core/project_paths.py`
- `src/business/__init__.py`
- `src/business/models.py`
- `src/business/repository.py`
- `src/business/validator.py`
- `config/businesses/demo_customer_service/business_profile_v1.json`
- `config/businesses/demo_customer_service/call_taxonomy_v1.json`
- `config/businesses/demo_customer_service/coaching_rules_v1.json`
- `tests/test_business_profile.py`
- `docs/business_configuration.md`

### Existing files modified

- `config/README.md`
- `src/README.md`
- `docs/PROJECT_STRUCTURE.md`
- `ROADMAP.md`

R1 will not move current configuration, knowledge-base, data, or source files.
Those moves belong to later phases and require their own approval.

## Risks and controls

| Risk | Control |
| --- | --- |
| Broken imports or hard-coded paths | Central resolver plus compatibility paths and full test suite |
| Business rules silently changing existing metrics | R1 loads context only; current metric calculations remain unchanged |
| Invented call type or complexity | Store `unknown` with low confidence until an approved source exists |
| Policy leakage between businesses | Business-scoped retrieval and versioned citations |
| LLM treated as analytical memory | Persist deterministic artifacts outside the provider |
| Agent ranking without fair context | Minimum sample sizes, context matching, anonymization, and uncertainty |
| Red flag treated as proof of wrongdoing | Require evidence and human review; prohibit automated employment decisions |

## Approval boundary

This document is the migration design only. No runtime path, import, public
interface, configuration location, knowledge document, or analytical result is
changed until the corresponding migration phase is explicitly approved.
