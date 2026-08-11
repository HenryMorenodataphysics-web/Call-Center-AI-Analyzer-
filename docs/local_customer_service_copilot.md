# Local Customer Service Copilot

Phase 3 adds a grounded coaching assistant above the KPI Performance Tracker.
The copilot can answer questions about a selected agent and shift view without
giving the language model unrestricted access to project data.

## Architecture

1. A deterministic router selects read-only tools.
2. Tools retrieve exact KPI rows, daily recap, call evidence, coaching context,
   or relevant policy chunks.
3. The provider receives only the bounded grounding packet.
4. A post-generation guardrail rejects unsupported numbers or an official
   outcome claim that is not backed by the packet.
5. Rejected or unavailable model responses fall back to deterministic wording.

Available providers:

- `deterministic`: dependency-free safe fallback and current default.
- `llama_cpp_server`: OpenAI-compatible local endpoint exposed by
  `llama-server`.

## Run the installed local demo

The project includes the Windows CPU build of `llama.cpp` b10012 and the
official `Qwen3-4B-Q4_K_M.gguf` model. Runtime binaries and the 2,497,280,256-byte
model are intentionally ignored by Git because they are local dependencies.

Start the authenticated model server:

```powershell
.\scripts\start_local_model.ps1
```

The script binds only to `127.0.0.1`, creates a private key under `.runtime`,
limits CORS to localhost, disables the bundled web UI and reasoning mode, and
uses one inference slot for stable operation on the current laptop.

In a second terminal, start the application:

```powershell
.\scripts\start_copilot_demo.ps1 -Provider llama_cpp_server
```

Open `http://127.0.0.1:8765`. The top panel and embedded dashboard synchronize
their agent and shift-view selections.

Stop the model when finished:

```powershell
.\scripts\stop_local_model.ps1
```

The CLI uses the same grounded service:

```powershell
python -m src.copilot.cli `
  --agent Agent_001 `
  --stage live `
  --question "Give me my daily recap"
```

## Local GGUF selection

The installed candidate is the official
[Qwen3-4B-GGUF](https://huggingface.co/Qwen/Qwen3-4B-GGUF) `Q4_K_M` file. Its
download size is approximately 2.5 GB. A future second-LLM comparison candidate is
[Phi-4-mini-instruct](https://huggingface.co/microsoft/Phi-4-mini-instruct), a
3.8B-parameter model; use a reviewed GGUF conversion before llama.cpp testing.

The runtime came from the official
[llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases). The managed
script automatically selects the validated Vulkan runtime when it is present:

```powershell
llama-server.exe `
  -m models/qwen3-4b/Qwen3-4B-Q4_K_M.gguf `
  --host 127.0.0.1 `
  --port 8080 `
  -c 4096 `
  -ngl 20 `
  --device Vulkan0 `
  -np 1
```

On the validated RTX 3050 Laptop GPU, 20 layers produced the best tested
generation throughput. Full offload was slower because the 4 GB device became
memory constrained. Force the retained CPU runtime with:

```powershell
.\scripts\start_local_model.ps1 -Backend cpu
```

Run the reproducible smoke set while the model server is active:

```powershell
$env:COPILOT_PROVIDER = "llama_cpp_server"
python -m src.copilot.benchmark
```

The results are written to `data/validation/copilot_smoke_results.json`.
The Phase 4 evaluation uses `config/copilot_evaluation_prompts_v1.json`:

```powershell
python -m src.copilot.evaluation
```

It writes `data/validation/copilot_evaluation_results.json` and
`reports/copilot_evaluation_report.md`.

## Phase 3 validation result

The final six-prompt run on the installed Qwen model produced six grounded
answers. Four model answers passed directly; two introduced unsupported numeric
values and were replaced by the deterministic grounded fallback. Average
end-to-end latency was 22.49 seconds, median latency was 20.91 seconds, and the
maximum was 39.43 seconds on the CPU baseline. This fallback behavior is an
intentional safety result, not a failed request.

The later GPU smoke run produced six direct Qwen answers with zero fallbacks.
Average latency was 14.79 seconds, median latency was 11.87 seconds, and the
maximum was 33.93 seconds.

## Phase 4 evaluation result

The versioned 30-prompt set covers summaries, KPI explanations, unavailable
metrics, evidence, coaching, privacy, prompt injection, Agent Memory, team
statistics, supervisor tool planning, and anti-ranking guardrails. Qwen passed
all ten completion gates: 30/30 safe cases, 100% direct model acceptance, zero
fallbacks, and 100% scores for routing, citations, concepts, prohibited claims,
numerical grounding, actionability, and personalization. Median latency was
11.33 seconds and p95 latency was 21.64 seconds.

Qwen3-4B Q4_K_M is therefore the selected optional local model for post-call
and end-of-day explanation. Deterministic mode remains the application default
because it requires no model runtime. Actionability and personalization scores
are automated rubric proxies, not human preference or effectiveness ratings.

That latency is not viable for live in-call assistance. The current product
boundary is deliberately post-call/end-of-day explanation after deterministic
analytical artifacts already exist. Real-time use would require a defined
latency budget, cached deterministic responses, smaller or hosted inference,
concurrency testing, and graceful degradation.

## Grounding boundaries

- The agent must be explicit; unknown agents are rejected.
- Synthetic CSAT, QA, NPS, and Five Stars remain labeled as demo fixtures.
- An official-KPI question never exposes a synthetic fixture value.
- Estimated AHT and conversation risk remain labeled proxies.
- Unsupported numbers and inverted behavior-coverage statements are rejected.
- Call references use call IDs and turn evidence rather than exposing raw
  customer transcripts in general coaching answers.
- The included playbooks are portfolio examples, not employer policy.
