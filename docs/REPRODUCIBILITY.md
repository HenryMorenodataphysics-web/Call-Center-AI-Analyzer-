# Reproducible portfolio package

The default reproduction path is intentionally lightweight. It rebuilds the
canonical dashboards and Agent Memory, validates the analytical contract, exercises the survey
provenance gates, and runs the complete automated test suite from the checked-in
analytical outputs. It does not start Whisper, Transformers, Qwen, llama.cpp,
or a GPU workload.

## Supported environment

- Windows 10 or 11
- Python 3.12
- PowerShell 5.1 or newer
- No API key, enterprise service, database server, or GPU required

## Clean setup

From a local checkout:

```powershell
cd ai_analyzer_core_v0
.\scripts\setup_demo_environment.ps1
.\scripts\reproduce_portfolio.ps1
```

The setup script creates `.venv` and installs the exact versions in
`requirements-demo.lock.txt`. The reproduction script uses that environment
automatically when it exists.

## What the reproduction run does

1. Runs all unit and integration tests.
2. validates the versioned analytical contract across 100 calls and 11,056
   fused turns.
3. Rebuilds the agent and supervisor canonical dashboard artifacts.
4. Rebuilds the 30-row Agent Memory v1.1 artifact and validates the Phase 5
   personalization gates.
5. Normalizes the supplied synthetic survey fixture while preserving its
   provenance.
6. Rebuilds the synthetic survey representativeness artifact.
7. Confirms that survey training remains blocked without real labels.
8. Verifies memory confidence, key counts, safety boundaries, expected deliverables, and SHA-256
   hashes.

The machine-readable and human-readable outputs are:

- `reports/reproducibility_report.json`
- `reports/reproducibility_report.md`

## Presentation artifacts

The self-contained HTML files are committed presentation packages and open
directly without a server:

- `dashboard/kpi_performance_tracker.html`
- `dashboard/supervisor_board.html`
- `reports/synthetic_survey_quality_report.html`

The Python builders reconstruct their canonical JSON artifacts. The enhanced
HTML renderer used to package those JSON artifacts is not a runtime dependency
of the lightweight demo; the already packaged HTML contains its semantic
fallback and remains viewable offline.

## Full inference environment

`requirements.txt` describes the heavier raw-audio analysis environment with
Faster Whisper, Transformers, Torch, Librosa, OpenSMILE, and related packages.
That environment may download model weights and process approximately 3.9 GB of
source audio. It is intentionally separated from the portfolio-demo lock file.

The optional local copilot additionally requires the ignored Qwen GGUF model
and llama.cpp binaries documented in `docs/local_customer_service_copilot.md`.
Neither component is required to reproduce the analytical dashboards.

## Reproducibility boundary

The package verifies semantic reproducibility and governance invariants, not
byte-for-byte equality. Generated timestamps and environment paths change from
run to run. Model inference can also vary across library, hardware, and model
runtime versions; therefore the validated, checked-in analytical outputs are
the stable portfolio fixture.
