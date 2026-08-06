# Project structure

This guide explains where each part of AI Analyzer Core belongs and gives
technical and nontechnical reviewers a clear path through the repository. The
project intentionally uses application code, versioned configuration, tests,
and documentation instead of notebooks.

## Recommended review path

1. Read the root `README.md` for the business problem, proof points, and limits.
2. Run `app/dashboard.py` to explore the product in Streamlit.
3. Read `docs/AI_Analyzer_Technical_Design.pdf` for the architecture and design
   decisions.
4. Inspect `config/analytical_contract_v1.json` to see how evidence, proxies,
   synthetic fixtures, and real outcomes are separated.
5. Review `src/` for implementation and `tests/` for verification.
6. Use `docs/REPRODUCIBILITY.md` to rebuild and validate the portfolio.

## Repository map

| Path | Purpose | Typical contents |
| --- | --- | --- |
| `app/` | User-facing application | Primary Streamlit dashboard |
| `config/` | Versioned behavior and data contracts | JSON schemas, model settings, demo targets |
| `src/` | Reusable implementation | Pipeline, aggregation, dashboards, Copilot, outcomes, personalization, validation |
| `tests/` | Automated verification | Unit tests and small fixtures |
| `knowledge_base/` | Checked-in Copilot retrieval sources | Demo compliance, service, and QA documents |
| `data/` | Inputs and derived evidence | Audio, transcripts, signals, summaries, outcomes, validation records |
| `dashboard/` | Checked-in presentation artifacts | Canonical JSON snapshots and portable HTML fallbacks |
| `reports/` | Generated review outputs | Reproducibility and synthetic-data quality reports |
| `docs/` | Durable explanation | Technical brief, methodology, limitations, and runbooks |
| `scripts/` | Reproducible operations | Environment setup, rebuild, and optional local-model control |
| `copilot/` | Legacy standalone UI | Static Copilot page retained as a fallback demonstration |
| `models/` | Local model files | Optional Qwen GGUF files; excluded from the lightweight demo |
| `tools/` | Local third-party runtimes | Optional llama.cpp runtime and downloads |
| `ROADMAP.md` | Product status and gates | Completed, deferred, blocked, and remaining phases |

## How information moves through the system

```text
raw audio and metadata
        -> transcription and speaker turns
        -> text and acoustic signals
        -> fused call-level evidence
        -> validated dashboard artifacts
        -> Agent Memory and controlled Copilot tools
        -> Streamlit views
```

Survey fixtures follow a separate governed path. They can demonstrate coverage
and sampling bias, but they cannot unlock outcome-model training. Real survey
labels must pass the readiness gates defined in
`config/survey_outcome_contract_v1.json`.

## Source, generated, and local-only content

- **Source-controlled implementation:** `app/`, `src/`, `config/`, `scripts/`,
  `tests/`, `knowledge_base/`, and `docs/`.
- **Reproducible artifacts:** selected files in `dashboard/`, `reports/`, and
  derived `data/` subfolders.
- **Local or heavyweight content:** `.venv/`, `.runtime/`, `models/`, `tools/`,
  original audio, and uploaded business documents. These are not required to
  review the lightweight demo.

## Design boundaries

- Heuristic risk is a review-priority proxy, not a quality score or probability.
- Synthetic KPI and survey values are demonstrations, not real outcomes.
- The deterministic pipeline calculates metrics; the LLM explains retrieved
  evidence and must cite its sources.
- Agent comparisons are descriptive until call context, sample size, and real
  outcomes support stronger conclusions.
- No output should be used as an automated employment decision.
