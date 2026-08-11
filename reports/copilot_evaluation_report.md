# Copilot Phase 4 evaluation

- Status: **PASS**
- Generated: `2026-08-11T02:17:13.232933+00:00`
- Prompt set: `1.0.0` (30 prompts)
- Surfaces: Agent Copilot and Supervisor Copilot

## Provider comparison

| Provider | Safe pass | Direct provider | Fallbacks | Median latency | P95 latency |
| --- | ---: | ---: | ---: | ---: | ---: |
| deterministic | 100% | 0% | 0 | 0.00 s | 0.00 s |
| llama_cpp_server | 100% | 100% | 0 | 11.33 s | 21.64 s |

## Qwen completion gates

- **PASS** `safe_pass_rate`: 100.0% (required 95.0%).
- **PASS** `critical_safe_pass_rate`: 100.0% (required 100.0%).
- **PASS** `tool_routing_rate`: 100.0% (required 90.0%).
- **PASS** `citation_count_rate`: 100.0% (required 95.0%).
- **PASS** `citation_marker_rate`: 100.0% (required 100.0%).
- **PASS** `required_concept_rate`: 100.0% (required 85.0%).
- **PASS** `forbidden_claim_pass_rate`: 100.0% (required 100.0%).
- **PASS** `numeric_grounding_rate`: 100.0% (required 90.0%).
- **PASS** `actionability_rate`: 100.0% (required 80.0%).
- **PASS** `personalization_rate`: 100.0% (required 90.0%).

## Default decision

- Portfolio application default: **deterministic**
- Selected optional local model: **Qwen3-4B-Q4_K_M**
- Deployment position: Post-call and end-of-day grounded explanation; deterministic mode remains the zero-resource portfolio default.

## Interpretation limits

- Actionability is a transparent keyword-and-rubric proxy, not human preference scoring.
- Personalization checks context and evidence citations, not coaching effectiveness.
- GPU memory is total device usage and includes Windows applications.
- A safe fallback counts as a safe answer but not as direct model acceptance.
- No result authorizes employee ranking, discipline, compensation, or termination.

## Failed cases

No Qwen rubric failures.
