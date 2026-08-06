# Survey prediction readiness

- Status: **blocked**
- Contract version: `1.0.0`
- Analyzed calls: 100
- Completed real survey labels: 0
- Positive / negative: 0 / 0
- Agents with labels: 0

## Target boundary

Conditional probability that a completed survey is positive.

## Issues

- `blocking` `SYNTHETIC_LABELS_NOT_ALLOWED`: Synthetic survey rows may test plumbing but cannot train or validate the real-outcome model.
- `blocking` `NO_REAL_SURVEY_LABELS`: No completed real survey labels are available; training and probability display remain disabled.
