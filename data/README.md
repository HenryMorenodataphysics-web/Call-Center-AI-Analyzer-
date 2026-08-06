# Data layers

This folder contains inputs and derived analytical records. Each subfolder
represents a stage of the pipeline so evidence can be traced back without
mixing raw inputs with calculated outputs.

## Subfolders

- `raw_audio/`: local source audio. It is large and should not be redistributed
  in the public repository.
- `metadata/`: call identifiers, agent assignments, and source metadata.
- `transcripts/`: channel-level speech transcription outputs.
- `speaker_turns/`: normalized customer and agent conversation turns.
- `text_analysis/`: sentiment and rule-based service-behavior signals.
- `acoustic_features/`: pitch, energy, speaking-rate, and related audio signals.
- `final_outputs/`: fused turn-level and call-level analytical outputs.
- `dashboard_data/`: compact tables prepared for dashboard generation.
- `outcomes/`: governed survey templates and synthetic demo fixtures. Synthetic
  rows are excluded from real outcome-model training.
- `validation/`: contract checks, readiness reports, smoke results, and the
  blinded human-review pilot.

## Evidence boundary

Observed signals, heuristic proxies, synthetic fixtures, and real business
outcomes are different data classes. Do not rename or present one class as
another. See `config/analytical_contract_v1.json` for the authoritative field
definitions.
