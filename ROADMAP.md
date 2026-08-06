# AI Analyzer Core — Product Roadmap

## Product vision

Build an integral call-center intelligence platform that combines textual and
acoustic signals to evaluate calls, explain performance, coach each agent based
on their own patterns, identify transferable team behaviors, and support agents
and supervisors through role-specific dashboards.

## Guiding principles

- Prefer pretrained and interchangeable models over training a foundation model
  from scratch.
- Keep metric calculations deterministic and auditable; use the LLM to explain
  and coach, not to invent or calculate official KPI values.
- Separate observed signals, derived proxies, and real business outcomes.
- Never present a proxy as real CSAT, NPS, QA, Five Stars, or survey probability.
- Attach confidence and supporting evidence to recommendations.
- Compare agents fairly by call type, complexity, language, market, and sample
  size.
- Optimize efficiency only within customer-service, QA, and compliance
  guardrails.

## Phase 0 — Stabilize the existing pipeline

**Status:** Completed

- Remove overlapping batch-summary duplication.
- Use per-call summaries as the canonical dashboard source.
- Validate exactly 100 unique calls, 10 agents, and 10 calls per agent for the
  current portfolio dataset.
- Detect missing, unexpected, duplicated, or stale outputs before aggregation.
- Add automated tests and document the reproducible execution flow.

**Definition of done:** The aggregation can be rerun safely regardless of which
agent ranges were processed previously, and all dashboard counts reconcile with
`calls_metadata.csv`.

## Phase 1 — Formalize the analytical contract

**Status:** Completed

- Define and version the call-turn, call-summary, agent-summary, and KPI schemas.
- Separate:
  1. observed signals such as pitch, energy, sentiment, speaking rate, empathy,
     probing, ownership, and next steps;
  2. derived scores such as risk, quality proxy, and coachability;
  3. real outcomes such as CSAT, NPS, QA, Five Stars, and survey result.
- Add confidence, evidence, model version, rubric version, and reason codes.
- Review the existing risk rubric and explicitly defer calibration until real
  outcomes or reviewed human labels are available.
- Establish data-quality checks for every pipeline stage.

**Definition of done:** Every displayed metric has a clear definition, source,
grain, confidence level, and limitation.

**Delivered:** Machine-readable contract v1, stable reason codes, turn-level
evidence, signal-coverage confidence, model and rubric manifest, KPI catalog,
contract migration, automated validation, and documented limitations. The
current 100-call dataset passes with zero blocking issues; the uncalibrated risk
rubric remains an explicit warning until real outcomes exist.

## Phase 2 — KPI Performance Tracker MVP

**Status:** Completed

- Build the agent dashboard around `My Performance` and `Today's Focus`.
- Display actual value, goal, trend, projection, freshness, and recommended
  action for each KPI.
- Add start-of-shift, during-shift, and end-of-shift views.
- Surface best call, most coachable call, and evidence-backed daily recap.
- Use clearly labeled synthetic/demo KPI data when AppTek does not provide real
  business outcomes.

**Definition of done:** An agent can understand their status and next best action
within a few seconds without seeing bonus-oriented language.

**Delivered:** Portable agent dashboard with filters for all 10 agents and
start/live/end simulated shift views; current value, goal, trend, projection,
freshness, source type, and recommended action for each KPI; deterministic
Today's Focus coaching; analyzed behavior coverage; best and coachable call
selection with reason-code evidence; and clearly labeled synthetic CSAT, QA,
NPS, and Five Stars fixtures. The canonical artifact and self-contained HTML
both pass the shared renderer's validation and packaging checks.

## Phase 3 — Local Customer Service Copilot

**Status:** Completed

- Implement a swappable LLM provider interface.
- Benchmark a small local instruction model such as Phi-4-mini-instruct against
  Qwen3-4B on project-specific prompts.
- Run a quantized GGUF model through `llama.cpp` or an equivalent local runtime.
- Give the assistant controlled tools for KPI lookup, call evidence, daily
  recap, and coaching context.
- Add retrieval over QA policies, compliance rules, and customer-service
  playbooks.
- Require evidence references and forbid invented KPI values.

**Definition of done:** The copilot answers KPI and coaching questions locally,
uses the correct agent context, cites supporting calls, and respects guardrails.

**Delivered:** Swappable deterministic and `llama.cpp` server providers;
controlled KPI, daily recap, call evidence, coaching, and policy retrieval
tools; explicit agent context; call and policy citations; synthetic/proxy
warnings; unsupported-number and inverted-coverage fallbacks; CLI; synchronized
localhost dashboard and chat interface; authenticated local runtime scripts;
official Qwen3-4B Q4_K_M GGUF; six-prompt real-model smoke harness; and automated
tests. The final Phase 3 smoke run grounded all six answers: four were accepted
directly from Qwen and two safely used deterministic wording after the model
introduced unsupported numbers. Comparative model evaluation remains Phase 4.

**Business knowledge extension delivered:** Local Knowledge Base Admin in
Streamlit; business-scoped PDF, DOCX, TXT, and Markdown ingestion; required
version, effective-date, language, market, and approval metadata; LangChain
recursive text splitting; ignored runtime storage; lexical retrieval across
checked-in and approved uploaded policies; versioned citations; business
isolation; prompt-injection rejection; and a safe retrieval fallback when no
uploaded index exists. Semantic embeddings, enterprise authentication, OCR,
and document lifecycle approval remain future production adapters.

## Phase 4 — Copilot evaluation

**Status:** Deferred — optional local-model work

- Create a 25–50 prompt evaluation set covering summaries, KPI explanations,
  coaching, evidence requests, unavailable metrics, privacy, and guardrails.
- Compare groundedness, numerical accuracy, actionability, personalization,
  hallucination rate, latency, and memory use.
- Choose the default model using these results rather than generic benchmarks.
- Add safe deterministic fallbacks for high-risk or unsupported answers.

**Definition of done:** The selected small model passes a documented evaluation
and its limitations are visible in the portfolio.

**Resource boundary:** This phase consumes model resources only when
`llama-server` and the evaluation harness are explicitly started. The pipeline,
agent dashboard, and supervisor dashboard do not load the LLM automatically.

## Phase 5 — Agent personalization

**Status:** In progress — Agent Memory v1 delivered

- Build an individual baseline from longitudinal behavior.
- Compare each agent with their own history and with context-matched peers.
- Adjust for call type, complexity, language, market, emotion, and workload.
- Apply conservative estimates when sample sizes are small.
- Detect stable strengths as well as improvement opportunities.

**Definition of done:** Recommendations change meaningfully with the agent and
call context, and low-confidence conclusions are labeled as such.

**Delivered so far:** Deterministic Agent Memory v1 with cumulative start, live,
and end snapshots for every agent; explicit sample-confidence bands; heuristic
risk mix; behavior coverage; evidence-backed observed strengths and coaching
opportunities; dataset-derived source-domain profiles; structured summaries;
and a controlled Copilot tool with call and memory citations. The current 10
calls per agent remain low confidence, source domains are not approved business
call types, and no governed dated history exists yet.

**Remaining completion gate:** Add versioned dated snapshots from real operating
periods, approved business call type and complexity context, conservative
context-matched comparisons, and validation that recommendations change
meaningfully without overstating low-sample patterns.

**Resource boundary:** Agent Memory is deterministic and stored outside the LLM.
It does not start or require Qwen.

## Phase 6 — Cross-agent learning and supervisor dashboard

**Status:** In progress — Supervisor Board MVP delivered

- Compare similar calls rather than ranking whole people without context.
- Identify behaviors associated with better outcomes.
- Translate team patterns into anonymized, transferable coaching advice.
- Add supervisor views for team health, exceptions, coaching queue, best calls,
  coachable calls, and supporting evidence.
- Avoid causal claims unless the available data supports them.

**Definition of done:** Supervisors can identify where attention is needed
without random monitoring or unnecessary micromanagement.

**Delivered so far:** Self-contained Supervisor Team Performance Board with
start/live/end shift views; team health cards; agent AHT-versus-risk proxy map;
team triage distribution; behavior coverage versus coaching benchmarks;
explainable coaching queue; agent context table; and best/coachable call review
evidence. It runs entirely from the existing analytical artifact and does not
start the Copilot. Context-matched cross-agent learning remains for a later
iteration.

## Phase 7 — Survey outcome prediction

**Status:** In progress — readiness layer delivered; training blocked on real labels

- Integrate real labeled CSAT, NPS, QA, Five Stars, or survey results when they
  become available.
- Start with interpretable tabular baselines before considering neural models.
- Calibrate predicted probabilities and evaluate discrimination, calibration,
  fairness, and stability.
- Keep survey probability separate from the current quality proxy.

**Definition of done:** Survey predictions are validated against real outcomes
and are presented as calibrated probabilities with documented limitations.

**Delivered so far:** Versioned survey-outcome contract; blank governed import
template linked to all 100 call IDs; real-label readiness validator; minimum
sample, class-balance, agent-coverage, survey-type, and label-version gates;
leakage-controlled feature engineering; interpretable logistic baseline;
agent-grouped evaluation; sigmoid calibration; coefficient reporting; and a
hard block preventing model training or probability display without real
labels. The current readiness report is correctly blocked because the AppTek
sample contains zero completed survey outcomes. The additional 30-row survey
file from the same database is now profiled and normalized as an explicit
synthetic fixture: all 30 rows reconcile to analyzed calls, while a provenance
gate excludes them from training and keeps Phase 7 blocked on real labels.

**Remaining completion gate:** Link governed real survey results, pass the
readiness thresholds, evaluate discrimination/calibration/stability, add a
governed fairness slice, approve a decision threshold, and only then expose
research probabilities in the dashboard.

## Phase 8 — Portfolio hardening

**Status:** In progress — documentation and reproducible package delivered;
visual walkthrough pending

- Complete the README and architecture diagrams.
- Document setup, data lineage, model choices, evaluation, and limitations.
- Add screenshots and a short end-to-end demonstration video.
- Include representative successes, failures, and uncertainty handling.
- Package a reproducible demo that can run without enterprise infrastructure.

**Definition of done:** A reviewer can understand the business problem, run or
view the solution, inspect the evidence, and see why the architecture is
credible despite limited compute.

**Delivered so far:** One-page, 60-second portfolio README; compact 10-page
technical portfolio brief with editable LaTeX source; native
architecture and Copilot trust-boundary diagrams; lightweight Python 3.12
dependency lock; clean-environment setup script; one-command reproduction
runner; machine-readable and human-readable reproducibility reports; artifact
hashes; and explicit separation between the lightweight demo, full audio
inference, and optional local Qwen runtime. Known failures, the no-employment-
decision principle, the post-call Copilot latency boundary, and the AppTek
license/use note are now prominent. A score-blinded 30-call human review pilot
and evaluator are prepared for exploratory construct validation of
`conversation_risk_v1`.

The technical PDF was reduced from 19 to 10 pages after tutor feedback. Repeated
catalogs, the repository map, and detailed runbooks now route to focused
Markdown references, while the PDF retains the executive story, architecture,
core rubric, evidence boundaries, dashboards, Copilot latency decision, human
validation pilot, failure register, responsible-use constraints, cost, and
reproducibility path.

**Remaining completion gate:** Complete and report at least 20 human risk-review
labels (30 preferred); capture final agent/supervisor dashboard images; record
the short end-to-end demonstration video; link the final repository URL; and
perform the final visual portfolio review.

## Recommended portfolio milestone

The current strong portfolio release centers on completed Phases 0–3, the
Supervisor Board MVP from Phase 6, the guarded survey-readiness layer from Phase
7, and the reproducible documentation package from Phase 8. Formal Copilot
comparison, full longitudinal personalization, context-matched cross-agent learning,
and real-outcome calibration remain visible extensions rather than hidden gaps.
