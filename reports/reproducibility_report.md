# AI Analyzer reproducibility report

- Status: **PASS**
- Generated: `2026-08-11T03:25:18+00:00`
- Python: `3.12.10`
- Scope: `lightweight_portfolio_demo`

## Reproduction steps

- **PASS** `Automated unit and integration tests` (8.292 seconds)

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
- **PASS** `CROSS_AGENT_LEARNING_POPULATION`: Phase 6 exposes seven anonymous end-view technique candidates without early-stage leakage.
- **PASS** `PHASE_6_CROSS_AGENT_LEARNING_GATE`: Phase 6 passes its bounded portfolio gates while governed outcome learning remains blocked.
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
- **PASS** `ARTIFACT_DASHBOARD_CROSS_AGENT_LEARNING_ARTIFACT_JSON`: Required artifact exists: dashboard/cross_agent_learning_artifact.json
- **PASS** `ARTIFACT_CONFIG_PERSONALIZATION_EVALUATION_V1_JSON`: Required artifact exists: config/personalization_evaluation_v1.json
- **PASS** `ARTIFACT_DATA_VALIDATION_PERSONALIZATION_EVALUATION_RESULTS_JSON`: Required artifact exists: data/validation/personalization_evaluation_results.json
- **PASS** `ARTIFACT_REPORTS_PERSONALIZATION_EVALUATION_REPORT_MD`: Required artifact exists: reports/personalization_evaluation_report.md
- **PASS** `ARTIFACT_CONFIG_CROSS_AGENT_LEARNING_CONTRACT_V1_JSON`: Required artifact exists: config/cross_agent_learning_contract_v1.json
- **PASS** `ARTIFACT_CONFIG_CROSS_AGENT_LEARNING_EVALUATION_V1_JSON`: Required artifact exists: config/cross_agent_learning_evaluation_v1.json
- **PASS** `ARTIFACT_DATA_VALIDATION_CROSS_AGENT_LEARNING_EVALUATION_RESULTS_JSON`: Required artifact exists: data/validation/cross_agent_learning_evaluation_results.json
- **PASS** `ARTIFACT_REPORTS_CROSS_AGENT_LEARNING_EVALUATION_REPORT_MD`: Required artifact exists: reports/cross_agent_learning_evaluation_report.md
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
- `dashboard/artifact.json`: present, SHA-256 `6e4a9160255f8c1eb0c857466fcf86e6ef39a7d2f7279196a33d8ca65ecd6d36`
- `dashboard/supervisor_artifact.json`: present, SHA-256 `0362b90df23ce69b1cfca458ef542e10022f5834d2abeddd84900e2c10538ab3`
- `dashboard/survey_representativeness_artifact.json`: present, SHA-256 `0be48a79562002a997522e6658eda3678723e32f9aad8e283dd70c6d9d6d33ab`
- `dashboard/agent_memory_artifact.json`: present, SHA-256 `a29a560b593b78b5a9c8a5de164f54458014c0f8f4a38e1a850fe243182d1935`
- `dashboard/cross_agent_learning_artifact.json`: present, SHA-256 `02a794a91db10949f84b472983585ea5fc60e7f9c1616173add6b7b5070eebb4`
- `config/personalization_evaluation_v1.json`: present, SHA-256 `1249245c066121c81a8c4ce1918371327e7780f35afe02b84dc19463f35cc4cd`
- `data/validation/personalization_evaluation_results.json`: present, SHA-256 `5e5c799ae65844f194a6ba379a54df2cb2f97d103795eb1b42f2f0673cae373b`
- `reports/personalization_evaluation_report.md`: present, SHA-256 `bcf6201a895442a6ec57cd8435e493075531e6241f77a898d441fb6b5fd2e947`
- `config/cross_agent_learning_contract_v1.json`: present, SHA-256 `8e8c986f6662a362b4332b0c3d6a9fe58de42c600528928c005b6c09a5941bfb`
- `config/cross_agent_learning_evaluation_v1.json`: present, SHA-256 `2fc6f2bc25134882638f753fd37c722a794449cbbbfe0cf208f54bb80507e865`
- `data/validation/cross_agent_learning_evaluation_results.json`: present, SHA-256 `df651c0d83fc4b54352e9c680f85dff70d1551543770fe46edae8612db57ef20`
- `reports/cross_agent_learning_evaluation_report.md`: present, SHA-256 `ac8a3eef0d4e7ce6529f10a4e8dc02e9836ee9de419bdb85d86d70dca16607ef`
- `config/knowledge_ingestion_contract_v1.json`: present, SHA-256 `0897c965012a1b27288161846c69834882b2bc0053f4388552057141fa7a3c4e`
- `reports/synthetic_survey_quality_report.html`: present, SHA-256 `2be70b13eefdf392e2d4aec7a7d8617b498cdb1d10ed208ad3aabb406c1dbdc6`
- `data/validation/analytical_contract_validation.json`: present, SHA-256 `25fa9aa56121ae76b217b8aafcbd8bb189898736e45e9412e5ce78d82c572dc8`
- `data/validation/survey_prediction_readiness.json`: present, SHA-256 `d9ea41ecbc2e34113dea50287f6aac51380e70dad76b2aaf0ed95d45d74bf430`
- `config/copilot_evaluation_prompts_v1.json`: present, SHA-256 `c62bce1a1e635da38187573fbfc4e3f3816318976e9d8a9436ac3d3b4cfac253`
- `data/validation/copilot_evaluation_results.json`: present, SHA-256 `2ab29310c862785c665e803fb0825b089cd84b1dea369e2f88a30443333cfd37`
- `reports/copilot_evaluation_report.md`: present, SHA-256 `fe7215d4d4a502004d2767f8f1c3feafa9b4b9de0094583c9466e77e009bd217`
- `docs/AI_Analyzer_Technical_Design.pdf`: present, SHA-256 `24dcf4f935a17670c360a7d816efb8bf4f9c82a716ef914b8a7e6b461338386e`
- `docs/risk_proxy_validation_pilot.md`: present, SHA-256 `f8bb136594eb43364f23c25402208dde9cc00119378e8375cb0a713521be146e`
- `data/validation/risk_review_pilot_blinded.csv`: present, SHA-256 `796243c18394523d850fb71ddaefe55c2605ed0eceee9b0689afa91d04c6ef5a`
- `data/validation/risk_review_pilot_key.csv`: present, SHA-256 `8f101347a47b4b4b9c0fddc56e764235b01308ae72dfbbf58c52e7ea8eeccdc4`
