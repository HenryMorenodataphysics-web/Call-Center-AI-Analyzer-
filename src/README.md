# Source code

This folder contains the reusable implementation. Pipeline stages are separated
from dashboards and generated artifacts so each transformation can be tested
and reproduced independently.

## Packages

- `data_prep/`: prepares the bounded analysis sample and metadata.
- `transcription/`: converts audio channels into text.
- `speaker_separation/`: assigns and normalizes customer and agent turns.
- `text_classifier/`: extracts sentiment and service-behavior signals.
- `acoustic_analyzer/`: extracts acoustic measurements from audio.
- `fusion_logic/`: combines textual and acoustic evidence into call records and
  the heuristic review-priority proxy.
- `knowledge/`: validates, extracts, chunks, and stores business-scoped uploaded
  policy documents under the ignored local runtime directory.
- `batch_processing/`: coordinates processing across multiple calls.
- `aggregation/`: validates coverage and creates canonical dashboard tables.
- `contracts/`: applies and validates the versioned analytical contract.
- `dashboard/`: builds the portable KPI and supervisor artifacts.
- `copilot/`: provides controlled tools, retrieval, provider adapters,
  guardrails, CLI/service orchestration, and deterministic fallback behavior.
- `outcomes/`: imports synthetic survey fixtures, checks real-label readiness,
  measures survey representativeness, and contains the guarded baseline
  training workflow.
- `personalization/`: builds and reads deterministic accumulated Agent Memory
  summaries for the selected agent and analysis stage.
- `validation/`: prepares and evaluates the human risk-review pilot and runs
  analytical-contract validation.

The deterministic pipeline owns metric calculation. The LLM may explain
retrieved evidence but does not calculate official KPI values.
