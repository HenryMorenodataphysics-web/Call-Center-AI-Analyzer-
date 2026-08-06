# Synthetic survey fixture quality review

## Executive Summary

- **Fixture only.** Every row is explicitly synthetic and cannot unlock real-outcome modeling.
- **Structurally joinable.** 30/30 rows map to analyzed calls, but source `call_id` is blank.
- **Below modeling gates.** The file has 22 positive and 8 negative synthetic labels.
- **Recommended use.** Keep it for ingestion, contract, and UI tests only.

## Quality checks

### High: Real-outcome provenance

30/30 rows have is_synthetic=True and every generation note says the feedback is for MVP testing only.

Impact: Cannot train, calibrate, validate, or display a real survey probability.

Action: Keep as a fixture and wait for a governed real survey extract.

### High: Training sufficiency

30 rows total: 22 positive and 8 negative; gates require 80 total and 20 per class.

Impact: The sample is too small and the negative class is below the minimum gate.

Action: Do not relax gates for a portfolio result; collect additional real labels.

### Medium: Primary call key completeness

call_id is blank in 30/30 rows; all 30 rows match uniquely through agent_id + agent_call_number.

Impact: The composite join is recoverable but less durable than a source-provided call_id.

Action: Use the recovered call_id only in the fixture adapter; require call_id in the real feed.

### Medium: Template repetition

Only 11 unique comments across 30 rows; the most common comment appears 5 times.

Impact: Text and score patterns are generated templates, not independent customer evidence.

Action: Exclude comments from modeling and from real-world performance claims.

### Pass: Structural integrity

30 unique survey IDs, 30 unique agent-call keys, 10 agents with 3 rows each, 0 NPS label mismatches, 0 name mismatches.

Impact: The file is structurally suitable for plumbing and UI tests.

Action: Retain automated uniqueness, enum, and join checks.
