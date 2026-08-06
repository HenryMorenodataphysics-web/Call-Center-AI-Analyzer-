# Human validation pilot for `conversation_risk_v1`

## Purpose

This pilot asks whether the uncalibrated risk proxy is directionally aligned
with a human supervisor's judgment. It does **not** turn the proxy into CSAT,
QA, a survey probability, or an employee score.

The sample contains 30 calls: the minimum-, middle-, and maximum-score call for
each of the ten portfolio agents. This purposive design covers the observed
score range while preserving equal agent representation. It is appropriate for
an exploratory construct-validity check, not for population inference.

## Review question

For every call, answer:

> Would a supervisor benefit from reviewing this call for customer-risk context,
> QA context, or actionable coaching?

Use `human_review_needed=1` for yes and `0` for no. Review the transcript and,
when possible, both audio channels. Do not look at the proxy key, dashboard risk
band, reason codes, or risk weights while labeling.

Also complete:

- `reviewer_confidence`: `low`, `medium`, or `high`;
- `primary_reason`: a short category such as `customer_distress`,
  `resolution_gap`, `agent_behavior`, `compliance_context`, or `none`;
- `notes`: one short evidence-based rationale;
- `reviewer_id` and `reviewed_at_utc`.

Agent identity, AHT, demo KPI values, compensation, and assumptions about
customer outcomes are not labeling criteria.

## Run the pilot

```powershell
python -m src.validation.prepare_risk_review_pilot
```

Label only:

`data/validation/risk_review_pilot_blinded.csv`

Do not open the separated key until labeling is complete:

`data/validation/risk_review_pilot_key.csv`

After at least 20 labels (30 preferred):

```powershell
python -m src.validation.evaluate_risk_review_pilot
```

The evaluator reports the confusion matrix, accuracy, balanced accuracy,
precision, recall, specificity, F1, Cohen's kappa, ROC AUC, and average
precision where estimable.

## Decision rule

Report the result even if it is poor. Do not tune weights or thresholds on this
same pilot and then present the re-evaluated pilot as independent validation.
Any revised rubric requires a new version and a separate holdout review set.

The pilot remains exploratory because it is small, purposively sampled, and may
have only one reviewer. Production use would require multiple trained reviewers,
inter-rater agreement, a representative holdout, threshold selection, subgroup
error analysis, drift monitoring, and a documented human-appeal process.
