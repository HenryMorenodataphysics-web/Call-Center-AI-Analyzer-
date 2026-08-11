# AI Analyzer reproducibility report

- Status: **PASS**
- Generated: `2026-08-11T02:55:23+00:00`
- Python: `3.12.10`
- Scope: `lightweight_portfolio_demo`

## Reproduction steps

- **PASS** `Automated unit and integration tests` (7.473 seconds)

## Invariant checks

- **PASS** `METADATA_CALL_COUNT`: Metadata contains exactly 100 calls.
- **PASS** `ANALYZED_CALL_COUNT`: Canonical call summary contains exactly 100 calls.
- **PASS** `UNIQUE_CALL_IDS`: All canonical call IDs are unique.
- **PASS** `AGENT_COUNT`: The portfolio sample contains exactly 10 agents.
- **PASS** `CONTRACT_STATUS`: Analytical contract validation passes.
- **PASS** `TURN_COUNT`: The contract reconciles 11,056 fused turns.
- **PASS** `AGENT_PROVENANCE`: Agent dashboard preserves fixture provenance.
- **PASS** `SUPERVISOR_PROVENANCE`: Supervisor dashboard preserves fixture provenance.
- **PASS** `REAL_SURVEY_GATE`: Real survey modeling remains blocked because no governed labels exist.
- **PASS** `PHASE_5_PERSONALIZATION_GATE`: Phase 5 passes the bounded portfolio gates while governed longitudinal history remains blocked.
- **PASS** `SYNTHETIC_SURVEY_GATE`: All 30 supplied survey rows remain fixture-only.
- **PASS** `SURVEY_REPRESENTATIVENESS_GATE`: Survey representativeness reconciles 100 calls and 30 synthetic surveys while preserving zero real labels.
- **PASS** `AGENT_MEMORY_POPULATION`: Agent Memory v1 reconciles 30 cumulative agent-stage rows to all 100 calls.
- **PASS** `AGENT_MEMORY_BOUNDARY`: Agent Memory preserves low sample confidence and the initial-snapshot-only boundary.
- **PASS** `KNOWLEDGE_INGESTION_CONTRACT`: Knowledge ingestion is business-scoped, local-only, and limited to four approved formats.
- **PASS** `COPILOT_PHASE_4_EVALUATION`: The 30-prompt Agent and Supervisor Copilot evaluation passes all completion gates.
- **PASS** `RISK_PILOT_SIZE`: Human risk-review pilot contains 30 calls.
- **PASS** `RISK_PILOT_UNIQUE_CALLS`: Human risk-review pilot contains 30 unique calls.
- **PASS** `RISK_PILOT_BLINDING`: Human review sheet excludes proxy scores, flags, bands, and reason codes.
- **PASS** `RISK_PILOT_AGENT_COVERAGE`: Human risk-review pilot contains three calls for each of ten agents.
- **PASS** `ARTIFACT_DASHBOARD_KPI_PERFORMANCE_TRACKER_HTML`: Required artifact exists: dashboard/kpi_performance_tracker.html
- **PASS** `ARTIFACT_DASHBOARD_SUPERVISOR_BOARD_HTML`: Required artifact exists: dashboard/supervisor_board.html
- **PASS** `ARTIFACT_DASHBOARD_ARTIFACT_JSON`: Required artifact exists: dashboard/artifact.json
- **PASS** `ARTIFACT_DASHBOARD_SUPERVISOR_ARTIFACT_JSON`: Required artifact exists: dashboard/supervisor_artifact.json
- **PASS** `ARTIFACT_DASHBOARD_SURVEY_REPRESENTATIVENESS_ARTIFACT_JSON`: Required artifact exists: dashboard/survey_representativeness_artifact.json
- **PASS** `ARTIFACT_DASHBOARD_AGENT_MEMORY_ARTIFACT_JSON`: Required artifact exists: dashboard/agent_memory_artifact.json
- **PASS** `ARTIFACT_CONFIG_PERSONALIZATION_EVALUATION_V1_JSON`: Required artifact exists: config/personalization_evaluation_v1.json
- **PASS** `ARTIFACT_DATA_VALIDATION_PERSONALIZATION_EVALUATION_RESULTS_JSON`: Required artifact exists: data/validation/personalization_evaluation_results.json
- **PASS** `ARTIFACT_REPORTS_PERSONALIZATION_EVALUATION_REPORT_MD`: Required artifact exists: reports/personalization_evaluation_report.md
- **PASS** `ARTIFACT_CONFIG_KNOWLEDGE_INGESTION_CONTRACT_V1_JSON`: Required artifact exists: config/knowledge_ingestion_contract_v1.json
- **PASS** `ARTIFACT_REPORTS_SYNTHETIC_SURVEY_QUALITY_REPORT_HTML`: Required artifact exists: reports/synthetic_survey_quality_report.html
- **PASS** `ARTIFACT_DATA_VALIDATION_ANALYTICAL_CONTRACT_VALIDATION_JSON`: Required artifact exists: data/validation/analytical_contract_validation.json
- **PASS** `ARTIFACT_DATA_VALIDATION_SURVEY_PREDICTION_READINESS_JSON`: Required artifact exists: data/validation/survey_prediction_readiness.json
- **PASS** `ARTIFACT_CONFIG_COPILOT_EVALUATION_PROMPTS_V1_JSON`: Required artifact exists: config/copilot_evaluation_prompts_v1.json
- **PASS** `ARTIFACT_DATA_VALIDATION_COPILOT_EVALUATION_RESULTS_JSON`: Required artifact exists: data/validation/copilot_evaluation_results.json
- **PASS** `ARTIFACT_REPORTS_COPILOT_EVALUATION_REPORT_MD`: Required artifact exists: reports/copilot_evaluation_report.md
- **PASS** `ARTIFACT_DOCS_AI_ANALYZER_TECHNICAL_DESIGN_PDF`: Required artifact exists: docs/AI_Analyzer_Technical_Design.pdf
- **PASS** `ARTIFACT_DOCS_RISK_PROXY_VALIDATION_PILOT_MD`: Required artifact exists: docs/risk_proxy_validation_pilot.md
- **PASS** `ARTIFACT_DATA_VALIDATION_RISK_REVIEW_PILOT_BLINDED_CSV`: Required artifact exists: data/validation/risk_review_pilot_blinded.csv
- **PASS** `ARTIFACT_DATA_VALIDATION_RISK_REVIEW_PILOT_KEY_CSV`: Required artifact exists: data/validation/risk_review_pilot_key.csv

## Runtime boundary

This run reconstructs and validates the portfolio surfaces from checked-in canonical outputs. It deliberately does not download or start inference models. The Qwen/llama.cpp path remains optional, and survey training remains disabled until real labels pass the readiness contract.

## Required artifacts

- `dashboard/kpi_performance_tracker.html`: present, SHA-256 `f4ee3db0387876020c21bbadb5cc8acacf3fdd6b193fc4c0f8c5205f6ca97f8c`
- `dashboard/supervisor_board.html`: present, SHA-256 `1df1a617115fa25a0f968b82ae5bfc85a5130031fc6770a6a089b9224e297cfd`
- `dashboard/artifact.json`: present, SHA-256 `b67aafec9c502a3fe3b04cd2a28326762ffa3093f08a5eade7646b8c625f2124`
- `dashboard/supervisor_artifact.json`: present, SHA-256 `17bb81d0da9431fbaa405718ea78147b23c930feb13f8189dc8d203fe231565b`
- `dashboard/survey_representativeness_artifact.json`: present, SHA-256 `4bd138394d8430901e4488961ceb22edcfcf8d56aadd20b7a0f6cec3afcc7c5f`
- `dashboard/agent_memory_artifact.json`: present, SHA-256 `97a78ca0d7d4519ca1a123de1a3b4c273ddeb799c85db3d554fa4b8b25904c90`
- `config/personalization_evaluation_v1.json`: present, SHA-256 `56d12479ed398c7b95a05049d0df81014d0c8751396f00b26c08e5ca5d648ecf`
- `data/validation/personalization_evaluation_results.json`: present, SHA-256 `8a189de1c643c5a55b2986b9979e0c525a87541d78ccbf6fe3e3fa4d6c6139ea`
- `reports/personalization_evaluation_report.md`: present, SHA-256 `bcf6201a895442a6ec57cd8435e493075531e6241f77a898d441fb6b5fd2e947`
- `config/knowledge_ingestion_contract_v1.json`: present, SHA-256 `0897c965012a1b27288161846c69834882b2bc0053f4388552057141fa7a3c4e`
- `reports/synthetic_survey_quality_report.html`: present, SHA-256 `2be70b13eefdf392e2d4aec7a7d8617b498cdb1d10ed208ad3aabb406c1dbdc6`
- `data/validation/analytical_contract_validation.json`: present, SHA-256 `25168aad9dfc185cb6ce13d8446c6727b2cd4e60b8a58549183b4999c36c9d63`
- `data/validation/survey_prediction_readiness.json`: present, SHA-256 `b77f761cfcd50bcd994c3d19c3df77f2f500a21f70f8a4a340be85a39683407b`
- `config/copilot_evaluation_prompts_v1.json`: present, SHA-256 `a6e6615b7b2ce6608f8bad39e4eddd4abee71122252cb66c08c77fdfc2d5d219`
- `data/validation/copilot_evaluation_results.json`: present, SHA-256 `2ab29310c862785c665e803fb0825b089cd84b1dea369e2f88a30443333cfd37`
- `reports/copilot_evaluation_report.md`: present, SHA-256 `fe7215d4d4a502004d2767f8f1c3feafa9b4b9de0094583c9466e77e009bd217`
- `docs/AI_Analyzer_Technical_Design.pdf`: present, SHA-256 `305497b231a62bf383138bc888320e6dc9da073ae0b8ee8eb4277c99dfb7d0db`
- `docs/risk_proxy_validation_pilot.md`: present, SHA-256 `f8bb136594eb43364f23c25402208dde9cc00119378e8375cb0a713521be146e`
- `data/validation/risk_review_pilot_blinded.csv`: present, SHA-256 `796243c18394523d850fb71ddaefe55c2605ed0eceee9b0689afa91d04c6ef5a`
- `data/validation/risk_review_pilot_key.csv`: present, SHA-256 `8f101347a47b4b4b9c0fddc56e764235b01308ae72dfbbf58c52e7ea8eeccdc4`
