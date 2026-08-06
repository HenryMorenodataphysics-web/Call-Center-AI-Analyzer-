# KPI Performance Tracker MVP

Phase 2 packages the existing 100-call analysis into an agent-facing dashboard
centered on **My Performance** and **Today's Focus**.

## What the MVP includes

- Agent and shift-view filters.
- Start, live, and end views simulated from call sequence.
- Current value, portfolio goal, trend, projection, status, freshness, source
  type, and recommended action for each headline KPI.
- Estimated AHT and conversation-risk proxy trends.
- Rule-based empathy, probing, ownership, and next-step call rates.
- Best analyzed call and most coachable candidate with reason-code evidence.
- Deterministic synthetic CSAT, QA, NPS, and Five Stars fixtures for UI
  demonstration.

## Data boundary

AppTek does not provide official CSAT, QA, NPS, Five Stars, or survey outcomes.
The dashboard therefore marks those values as `synthetic_demo` everywhere and
sets the snapshot status to `fixture`. They are not predictions and must be
replaced with governed business feeds before operational use.

Estimated AHT is the analyzed audio duration. Conversation risk remains the
uncalibrated `conversation_risk_v1` heuristic proxy defined in the Phase 1
analytical contract.

## Build

From the project root:

```powershell
python src/dashboard/build_kpi_dashboard.py
```

This writes `dashboard/artifact.json`. Package it with the Data Analytics
portable artifact builder to create the self-contained
`dashboard/kpi_performance_tracker.html` file.

The delivered HTML passed canonical artifact validation, portable packaging,
payload-equality checks, and structural verification. Browser-level automated
QA was not available in the build environment because no compatible Chromium
headless executable was installed; the semantic fallback remains embedded and
readable without the enhanced runtime.

## Customize portfolio assumptions

Edit `config/demo_kpi_targets.json` to change demo targets, stage sizes, or
behavior coaching benchmarks. The values are deliberately separate from the
analytical contract because they are business assumptions, not model outputs.
