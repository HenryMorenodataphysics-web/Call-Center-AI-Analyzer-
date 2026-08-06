# Application entry points

This folder contains the interfaces a reviewer runs directly.

## Files

- `dashboard.py`: primary Streamlit application. It combines the executive
  overview, KPI Performance Tracker, survey-representativeness demo, Agent
  Copilot, Supervisor Board, business-scoped Knowledge Base Admin, and
  methodology views.

The application reads checked-in JSON artifacts from `dashboard/`. It does not
rerun transcription or model inference when the page opens. The Agent Copilot
uses the deterministic provider by default; the local Qwen server is optional.

## Run

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app/dashboard.py
```
