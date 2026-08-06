# Operational scripts

These scripts handle environment setup, validation, artifact generation, and
optional local-model operations.

## Files

- `setup_demo_environment.ps1`: creates or prepares the lightweight Python
  environment used by the reproducible demo.
- `reproduce_portfolio.ps1`: PowerShell entry point for the complete lightweight
  validation and rebuild workflow.
- `reproduce_portfolio.py`: orchestration and report generation used by the
  PowerShell reproduction command.
- `start_local_model.ps1`: starts the optional localhost-only Qwen server.
- `stop_local_model.ps1`: stops the local Qwen server started by this project.
- `start_copilot_demo.ps1`: starts the standalone Copilot interface.

The normal dashboard does not require the local model to be running.
