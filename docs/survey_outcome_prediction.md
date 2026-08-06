# Survey-outcome prediction readiness

Phase 7 prepares an interpretable survey-outcome model without fabricating
labels. The current AppTek portfolio sample contains no real CSAT, NPS, QA,
Five Stars, or survey result. Training and probability display therefore remain
blocked until a governed outcome feed is linked.

This workflow is lightweight CPU analytics. It does not start the local Qwen
model, use the Copilot, or require a GPU.

## Prediction target

The primary target is `survey_positive`, defined as the conditional probability
that a completed, linked survey is positive.

It does not estimate whether a customer will complete a survey. That distinction
matters because completed surveys may have response-selection bias. It is also
separate from official QA, the current `conversation_risk_v1` heuristic, and all
synthetic dashboard KPI fixtures.

The governed source must provide one row per call with:

- `call_id`
- `survey_received`: `1` or `0`
- `survey_positive`: `1` or `0` when a survey was completed
- `survey_type`: `CSAT`, `NPS`, `FIVE_STAR`, or another governed instrument
- `survey_score`: optional raw score for audit
- `survey_completed_at`
- `is_synthetic`: must be explicitly `False` for any completed label used in
  training or evaluation
- `source_system`
- `label_definition_version`

The machine-readable definition is
`config/survey_outcome_contract_v1.json`. A blank 100-call input is available at
`data/outcomes/survey_outcomes.csv`, and the reusable blank template is
`data/outcomes/survey_outcomes_template.csv`.

## Training gates

The initial portfolio baseline requires:

- At least 80 completed survey labels.
- At least 20 positive and 20 negative labels.
- Label coverage across at least 8 agents.
- One survey instrument per model run.
- One governed label-definition version per run.
- No duplicate or unknown call IDs.

These are minimum demonstration gates, not production sample-size claims.
Rows marked `is_synthetic=True` never count toward any gate, regardless of
their score or label balance.

## Supplied synthetic survey fixture

The file obtained from the same database is stored separately at
`data/outcomes/fixtures/synthetic_surveys_3_per_agent.csv`. It contains 30
explicitly synthetic survey rows: three for each of the ten agents. All 30 rows
map uniquely to analyzed calls through `agent_id + agent_call_number`, even
though the source `call_id` field is blank.

Run the fixture adapter with:

```powershell
python -m src.outcomes.import_synthetic_surveys
```

This creates a normalized test fixture and data-quality reports. It preserves
`is_synthetic=True`, so the real-outcome validator rejects the rows for model
training. The fixture is suitable only for schema, join, guardrail, and UI
tests. Its 22 positive and 8 negative generated labels do not complete Phase 7.

Outputs:

- `data/outcomes/fixtures/synthetic_surveys_normalized.csv`
- `data/validation/synthetic_survey_fixture_quality.json`
- `data/validation/synthetic_survey_fixture_quality.md`
- `reports/synthetic_survey_quality_report.html`

## Features and leakage control

The baseline uses length-adjusted call features such as duration, turns per
minute, talk share, negative/frustration/intensity rates, agent behavior rates,
and signal-coverage confidence.

The following are excluded from model features:

- Agent identity and name.
- Survey fields and post-call outcomes.
- Synthetic CSAT, NPS, QA, and Five Stars.
- The uncalibrated conversation-risk score and level.
- Raw transcripts, free text, and customer personal data.

`agent_id` is retained only as an evaluation group so an agent's calls do not
appear in both the training and test side of the same outer fold.

## Evaluation design

The first baseline is standardized logistic regression. Evaluation uses
agent-grouped stratified folds and reports ROC AUC, average precision, Brier
score, log loss, threshold diagnostics, calibration bins, and fold stability.
The final research estimator uses sigmoid probability calibration and publishes
standardized coefficients for interpretation.

No decision threshold is approved automatically. Fairness completion requires
governed protected or operational slices; demographics must never be inferred.
Association between a behavior and an outcome is not a causal claim.

## Run the readiness gate

After placing the governed extract at `data/outcomes/survey_outcomes.csv`:

```powershell
python -m src.outcomes.survey_dataset
```

Outputs:

- `data/validation/survey_prediction_readiness.json`
- `data/validation/survey_prediction_readiness.md`
- `data/modeling/survey_prediction_dataset.csv` only when all gates pass

If readiness is `ready`, run:

```powershell
python -m src.outcomes.train_survey_baseline
```

This creates a research-only calibrated model and evaluation report. The model
must not be exposed in either dashboard until real-label evaluation, stability,
fairness, and threshold review are complete.

## Current status

The real readiness report remains `blocked` with `NO_REAL_SURVEY_LABELS`: 100
analyzed calls, zero completed real survey labels, and no model or prediction
dataset created. A separate validation run against the supplied fixture is also
blocked with `SYNTHETIC_LABELS_NOT_ALLOWED`. This is the expected safe state.
