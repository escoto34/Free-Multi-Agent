# Systems orchestration — free-durable profile

**Document status:** mid-2026 research snapshot (last updated 2026-07-17)  
**Live config:** `config/model_router.yaml` (loaded by `core/agent_config.py`)  
**Factory defaults:** `config/defaults_model_router.yaml`  
**Quota soft-caps:** `core/quotas.py` (must stay ≤ real provider limits)  
**Benchmarks + selection + reasoning:** `config/model_benchmarks.yaml`

This document explains **why** each free-tier model sits in each System A / System B / CLI role: benchmarks (relative quality), a reusable **0–100 scoring rubric**, API rate limits, orchestration constraints (shared buckets, cascade design, calls per run), **how primary vs fallback is chosen at runtime**, and **how reasoning/thinking effort is applied inside each call**.

> **Runtime modules (implemented):**  
> `core/difficulty_scorer.py` · `core/model_selector.py` · `core/reasoning_params.py` ·  
> `core/handoff.py` · `core/agent_runtime.py` · `core/router.py` · `core/quotas.py`

---

## 0. Live role inventory (primary + fallback)

Source of truth: `config/model_router.yaml` via `get_agent_config(...)` in `core/agent_config.py`.  
Roles requested for scoring: System A (`architect`, `coder`, `debugger`) and System B (`safety_filter`, `context_compressor`, `web_search`, `grounding`, `synthesizer`).

| Pipeline | Role | Primary `provider` / `model` | Fallback `provider` / `model` |
|----------|------|------------------------------|-------------------------------|
| **A — Vibe** | `architect` | `agnes` / `agnes-2.0-flash` | `gemini` / `gemini-2.0-flash` |
| **A — Vibe** | `coder` | `mistral` / `codestral-latest` | `agnes` / `agnes-2.0-flash` |
| **A — Vibe** | `debugger` | `groq` / `openai/gpt-oss-120b` | `agnes` / `agnes-2.0-flash` |
| **B — Research** | `safety_filter` | `groq` / `openai/gpt-oss-safeguard-20b` | `gemini` / `gemini-2.0-flash` |
| **B — Research** | `context_compressor` | `agnes` / `agnes-2.0-flash` | `gemini` / `gemini-2.0-flash` |
| **B — Research** | `web_search` | `groq` / `groq/compound-mini` | **none** (hard-fail if no live search) |
| **B — Research** | `grounding` | `cohere` / `command-a-plus-05-2026` | `mistral` / `mistral-small-latest` |
| **B — Research** | `synthesizer` | `groq` / `openai/gpt-oss-120b` | `agnes` / `agnes-2.0-flash` |

**Unique models in the live hot path (primary or role-level fallback):**  
`agnes-2.0-flash`, `gemini-2.0-flash`, `codestral-latest`, `openai/gpt-oss-120b`, `openai/gpt-oss-safeguard-20b`, `groq/compound-mini`, `command-a-plus-05-2026`, `mistral-small-latest`.

**Catalog-only (not currently assigned as primary/fallback to those roles):**  
`tencent/hy3:free` remains in the OpenRouter free catalog and is scored below for historical/optional use.  
**⚠ `tencent/hy3:free` expires 2026-07-21** — treat as **temporal; verify availability before every run**. Do not assume it is durable free capacity.

CLI (`chat`, `planner`) uses Agnes → Groq 120b; see §7. Provider-level `fallback_cascade` is §8.

---

## 1. Design goals

1. **Survive a full personal workday** on free/trial APIs without early hard-stop.
2. **One scarce bucket = one critical role** (never burn Cohere or OpenRouter `:free` on three nodes).
3. **Spread Groq load across model IDs** (independent ~1 000 RPD counters).
4. **Reserve the only free live-search path** (`groq/compound-mini`) for research web search.
5. **Prefer durable free models** (Agnes, Groq gpt-oss, Codestral, Gemini Flash) over expiring promos (e.g. `tencent/hy3:free`).
6. **Cascade without OpenRouter sinks** — free OR is optional catalog, not the leaf of every failure.

---

## 2. Calls per pipeline (budget math)

| Pipeline | LLM steps (typical) | Notes |
|----------|---------------------|--------|
| **System A — Vibe** | 2–5 | Architect (1) + Coder (1) + Debugger (0–3 fix cycles) |
| **System B — Research** | 5 | Safety + compressor + web_search + grounding + synthesizer |
| **CLI `/do`** | +1 planner | Then N× vibe and/or research |

Implication: if three research nodes all hit **Cohere (~28/day)**, theoretical max is ~9 full reports; with Cohere **only on grounding**, max is ~28 reports/day (or ~250 if limited by `compound-mini` RPD instead).

---

## 3. Provider rate limits (research summary)

Limits below are **public free/trial reference values** as of ~2026-06/07. Providers change catalogs and tiers without notice — treat as planning bounds, not SLAs. YAML soft-caps are **conservative** fractions of these.

### 3.1 Groq

| Model ID | Free RPM (approx.) | Free RPD (approx.) | Notes |
|----------|--------------------|--------------------|--------|
| `openai/gpt-oss-120b` | 30 | **1 000** | Strong open reasoning; backbone for debug/synth |
| `openai/gpt-oss-20b` | 30 | **1 000** | Lighter sibling |
| `openai/gpt-oss-safeguard-20b` | 30 | **1 000** | Safety / moderation flavored |
| `qwen/qwen3.6-27b` | 30 | **1 000** | Catalog alternate |
| `groq/compound-mini` | 30 | **~250** | **Built-in Tavily web search** — scarce; search-only |
| (other Llama/Qwen) | 30–60 | 1 000–14.4k | Some small models historically higher RPD |

- **Scope:** per-model counters (good for spreading roles).  
- **YAML soft-cap:** 800 RPD/model (`daily_limit_per_model`).  
- **Sources:** [Groq rate limits docs](https://console.groq.com/docs/rate-limits), community free-tier summaries 2026.

### 3.2 Agnes AI

| Model ID | Endpoint | Free notes |
|----------|----------|------------|
| **`agnes-2.0-flash`** | `/v1/chat/completions` | Free / $0 per M tokens (promo pricing); ~**20 RPM** free/default plan; large context (docs cite 256K–512K depending on revision); tool-calling, coding, agents; Claw-Eval ~top-10 general / strong agent Pass^3 |
| `agnes-image-2.0-flash` | `/v1/images/generations` | Free image — **not** used in MultiAgent chat roles |
| `agnes-image-2.1-flash` | `/v1/images/generations` | Free image — not used in chat roles |
| `agnes-video-v2.0` | `/v1/videos` | Free video (async) — not used in chat roles |

- **YAML soft-cap:** 2 000 calls/day (local fair-use gate; real free is RPM/fair-use, not a hard public RPD).  
- **Role fit:** high-volume structured text, planning, compression, chat — **hot path primary**.  
- **Sources:** [Agnes wiki / model docs](https://wiki.agnes-ai.com/en/docs/agnes-20-flash), [AgnesAI-Models catalog](https://github.com/AgnesAI-Labs/AgnesAI-Models) (2026-06-28 reference: free text ~20 RPM).

### 3.3 Mistral (La Plateforme Experiment)

| Model ID | Role fit | Free notes |
|----------|----------|------------|
| **`codestral-latest`** | Code generation | Free Experiment tier; rate-limited (community: ~1 RPS class); **best free coding specialist** in this stack |
| `mistral-small-latest` | Grounding fallback, light JSON | Higher availability under Experiment |
| `mistral-medium-latest` | Optional quality | Same free pool, tighter if abused |
| `devstral-latest` | Agent coding alternate | Catalog option |

- **YAML soft-cap:** 200 calls/day (conservative; console Limits page is source of truth).  
- **Sources:** Mistral admin docs / Experiment free tier posts 2025–2026.

### 3.4 Google AI Studio (Gemini)

| Model ID | Free RPM (approx.) | Free RPD (approx.) | Notes |
|----------|--------------------|--------------------|--------|
| `gemini-2.5-flash` | ~10–15 | ~250–1 500 | Varies by account/tier updates |
| `gemini-2.0-flash` | ~15 | often more available for new free users | **Preferred fallback ID** for reliability |
| `gemini-2.5-flash-lite` | higher | higher | Cheap structured extract |
| Pro family | low | very low / paid-only trends | Avoid as free primary |

- **YAML soft-cap:** 400 RPD shared soft (provider-level).  
- **Strengths:** structured JSON, long context, solid Flash-tier intelligence.  
- **Sources:** [Gemini rate limits](https://ai.google.dev/gemini-api/docs/rate-limits), third-party free-tier tables 2026 (numbers drift).

### 3.5 Cohere (Trial)

| Model ID | Fit | Limits |
|----------|-----|--------|
| **`command-a-plus-05-2026`** | RAG / grounding | Trial: **~1 000 API calls/month** (~25–30/day), Chat ~20 RPM; **non-commercial** trial ToS |
| `command-r-plus-08-2024` | Alternate RAG | Same trial pool |
| `command-r7b-12-2024` | Lighter | Same pool |

- **YAML soft-cap:** 28 RPD shared.  
- **Why sole primary use = grounding:** documents= / citation-oriented quality + ultra-scarce monthly budget.  
- **Sources:** [Cohere rate limits](https://docs.cohere.com/docs/rate-limits).

### 3.6 Cerebras Inference

| Model ID | Free RPM | Free TPD (approx.) | Notes |
|----------|----------|--------------------|--------|
| `gemma-4-31b` | **5** | ~1M tokens | Strong open quality; catalog can rotate |
| `gpt-oss-120b` | **5** | ~1M | Very high tokens/s on Cerebras hardware |
| `zai-glm-4.7` | **5** | ~1M | Catalog alternate |

- **YAML soft-cap:** 150 calls/day (tokens/day + RPM dominate real use).  
- **Role fit:** quality **burst fallback**, not high-frequency primary (RPM=5). Llama IDs often **404** after catalog shrink.  
- **Sources:** [Cerebras rate limits](https://inference-docs.cerebras.ai/support/rate-limits), model overview.

### 3.7 OpenRouter (`:free` models)

| Constraint | Value |
|------------|--------|
| Free models RPM | **20** |
| Free models RPD | **50** total shared if &lt; $10 lifetime credits |
| After ≥ $10 credits | **1 000** free RPD shared |

| Example free IDs (catalog) | Notes |
|----------------------------|--------|
| `cohere/north-mini-code:free` | Fast code-ish; still shares 50 RPD |
| `tencent/hy3:free` | Promo; may expire (`free_until` if set) |
| `meta-llama/llama-3.3-70b-instruct:free` | General |
| `google/gemma-3-27b-it:free`, `qwen/qwen3-32b:free` | Alternates |

- **YAML soft-cap:** 45 RPD shared.  
- **Orchestration decision:** **off hot path** for free-durable defaults. Cascade `openrouter_fallback` → Agnes, not deeper free OR.  
- **Sources:** [OpenRouter limits](https://openrouter.ai/docs/api_reference/limits).

### 3.8 Ollama (local)

| Item | Value |
|------|--------|
| Limits | Hardware only (local soft-cap 100 000 in tracker) |
| Models | **Only** what `ollama list` reports — no static catalog |
| Role fit | Optional override for privacy / offline; not default cloud path |

---

## 4. Scoring rubric and model benchmarks (0–100)

**Machine-readable twin:** `config/model_benchmarks.yaml` (scores + per-role selection thresholds + reasoning policy).  
**Runtime:**

| Concern | Module |
|---------|--------|
| Score task 0–100 (structured) | `core/difficulty_scorer.py` → `DifficultyAssessment` |
| Primary vs fallback model | `core/model_selector.py` → `select_for_role` |
| Reasoning / thinking effort on the **same call** | `core/reasoning_params.py` → `resolve_reasoning_kwargs` |
| Inject both into LLM call | `core/agent_runtime.py` → `run_structured_agent` / `run_role_raw` |
| Cascade-safe kwargs + quota per **call** | `core/router.py` + `core/quotas.py` |
| Audit model switch | `core.handoff.transfer_control` / `record_model_selection_handoff` |

Public leaderboards move weekly. Scores below are a **reusable MultiAgent rubric** for automatic scoring systems: they map *role-relevant* capability on free/trial tiers, not absolute frontier rank vs paid GPT-5 / Claude Opus class.

### Critical quota fact (calls ≠ tokens)

Free/trial soft-caps in this stack are almost always **requests per day (RPD / calls)**, not token budgets:

| What | Costs an extra daily call? |
|------|----------------------------|
| Cascade to another model after 429 | **Yes** (+1 on the next model) |
| Retry same model after 429 | **Yes** each attempt that reaches the API |
| Raise `reasoning_effort` low→high on GPT-OSS | **No** — same call, more tokens/latency only |
| `include_reasoning=true` | **No** — same call |

**Implication:** on hard debugger/synth work, prefer **higher reasoning effort** on the model already selected rather than inventing extra hops. Effort is free in RPD terms; model switches are not.

### 4.1 Rubric definition (0–100 per area)

Five areas map to this repo’s pipelines:

| Code | Area | What we measure |
|------|------|-----------------|
| **(a) code** | Generación / depuración de código | HumanEval / LiveCodeBench / SWE-bench-class edit quality, multi-file edits, fix-from-tracebacks |
| **(b) reason** | Razonamiento y planificación | MMLU-Pro / GPQA / AIME-class hard reasoning, multi-step plans, structured specs (architect / compressor / planner) |
| **(c) ground** | Búsqueda / grounding con citas | Live web retrieval, citation faithfulness, RAG anti-hallucination (documents= style) |
| **(d) synth** | Síntesis / redacción | Long coherent reports, section structure, bilingual clarity, long-context assembly |
| **(e) safety** | Seguridad / filtrado | Policy classification, refusal/allow decisions, low false-negative risk for unsafe research topics |

**Range bands (reusable by an auto-scorer):**

| Score | Band | Meaning for MultiAgent |
|------:|------|------------------------|
| **0–30** | Unreliable | Do **not** use unsupervised for this area. Expect failure, fabrication, or wrong modality. |
| **31–49** | Weak | Only with heavy host guards (schema, scrub, unit tests) or as last-resort cascade. |
| **50–69** | Adequate | Usable for the area with supervision / pipeline checks; not best-in-stack. |
| **70–84** | Strong | Prefer as role primary when quota allows; good default free quality. |
| **85–100** | Production-class *(within free/trial stack)* | Best-in-stack for that area; still subject to rate limits and ToS, not paid frontier SLA. |

**Scoring rules for future automation:**

1. Prefer **public** numbers (model cards, Artificial Analysis, Claw-Eval, RealtimeEval, vendor technical reports) when available.  
2. If only relative evidence exists, map rank within free/open class into the 50–90 band (never invent exact HumanEval % you did not read).  
3. Mark **evidence** as `public` | `vendor` | `inferred` | `sparse`.  
4. Cap any score at **49** if the model is **unavailable / expired** for that run (auto-scorer should re-probe).  
5. Specialization beats generalism: a safety-tuned model may score high on (e) and mid/low on (a)–(d) by design.

### 4.2 Benchmark scores by model × area

Scores are **relative within this free-durable stack** (snapshot mid-2026). They are for routing documentation and future auto-scoring — not a claim of absolute frontier rank.

| Model (provider ID) | (a) code | (b) reason | (c) ground | (d) synth | (e) safety | Evidence notes (primary sources / proxies) |
|---------------------|--------:|----------:|----------:|---------:|----------:|--------------------------------------------|
| **`mistral` / `codestral-latest`** | **88** | 62 | 40 | 55 | 35 | Vendor: Codestral-2501 HumanEval **86.6%**, strong MultiPL-E / fill-in-middle; coding specialist, not RAG/safety. `public`+`vendor` |
| **`groq` / `openai/gpt-oss-120b`** | **82** | **90** | 48 | **85** | 45 | Open weights reasoning MoE (~117B / ~5.1B active); AA Intelligence Index competitive open class; HumanEval-class ~high 80s in secondary tables; strong debug/synth, no native search API. `public` |
| **`agnes` / `agnes-2.0-flash`** | **78** | **76** | 42 | **80** | 40 | Claw-Eval ~**51.8%** Pass^3 (top tier free agents, May 2026 tables); large context, tool-calling, coding/agents marketing + independent agent benches. `public`+`vendor` |
| **`gemini` / `gemini-2.0-flash`** | 70 | **78** | 55 | 75 | 50 | Flash-class structured JSON / long-context; solid MMLU-Pro family proxies; good plan/compress fallback; not Codestral-level pure code; not Cohere-level citation RAG. `public`+`inferred` |
| **`cohere` / `command-a-plus-05-2026`** | 58 | 72 | **93** | 78 | 48 | Cohere Command A technical report: **best-in-class enterprise RAG / grounding / tool use**; solid code understanding but not our free coding primary. Trial ToS non-commercial. `vendor`+`public` |
| **`mistral` / `mistral-small-latest`** | 58 | 62 | 55 | 65 | 40 | Mid free generalist (Small line; Small 4 claims competitive LiveCodeBench vs OSS 120B in vendor blogs — treat as upper bound if alias drifts). Grounding fallback only. `vendor`+`inferred` |
| **`groq` / `groq/compound-mini`** | 50 | 58 | **88** | 52 | 30 | **System** (GPT-OSS + Llama + tools), not a bare LLM. Built-in **Tavily web search**; RealtimeEval **> GPT-4o-search-preview** (Groq). Single tool call / low latency. Unique free live-search path. `vendor`+`public` |
| **`groq` / `openai/gpt-oss-safeguard-20b`** | 35 | 55 | 30 | 40 | **92** | OpenAI open safety classifier (post-trained from gpt-oss); BYO policy; purpose-built for Trust & Safety — **not** a general coder. `vendor`+`public` |
| **`openrouter` / `tencent/hy3:free`** ⚠ | 55 | 60 | 38 | 58 | 35 | **Temporal promo.** **Expires 2026-07-21.** Sparse independent benches; historically general free chat. **Verify availability before every execution.** Cap auto-score ≤49 if 404/expired. `sparse` |

**Quick capability matrix (stack defaults):**

| Capability | Strong free options | Weaker / avoid as primary |
|------------|---------------------|---------------------------|
| **(a) Coding** | Codestral; Agnes; GPT-OSS-120B | Safeguard-20B; pure search systems |
| **(b) Reasoning / plan** | GPT-OSS-120B; Gemini Flash; Agnes | Safeguard-only; expired hy3 |
| **(c) Search / ground** | compound-mini (live search); Command A+ (RAG/citas) | Models that invent citations without corpus |
| **(d) Synthesis** | GPT-OSS-120B; Agnes (context); Command A+; Gemini | Mini search system as sole writer |
| **(e) Safety** | GPT-OSS Safeguard 20B | Random general chat for policy gates |
| **Live web search** | **Only** `groq/compound-mini` in this free stack | Models that “pretend” to search |

### 4.3 Recomendación primario vs fallback por rol

Política **implementada** en `core/model_selector.py` + umbrales en `config/model_benchmarks.yaml`  
(`score_advantage_threshold: 8`, `weak_specialization_max: 49`). El planeador emite un  
`DifficultyAssessment` estructurado; el grafo/runtime llama `select_for_role(...)`.

| Role | Primary (scores that matter) | Fallback | Prefer **fallback** when… | Prefer **keep primary** when… |
|------|------------------------------|----------|---------------------------|-------------------------------|
| **architect** | Agnes (reason **76**, synth **80**, code **78**) | Gemini 2.0 Flash (reason **78**, structured JSON strong) | Agnes 429 / soft quota / empty (`primary_status=degraded…`); mis-specialized primary (weak ≤49 + Δ≥8) | Healthy primary; high volume of `/do` + vibe (Agnes fair-use); Gemini only edges reason by Δ=2 |
| **coder** | Codestral (code **88**) | Agnes (code **78**) | Mistral 429 / empty artifact / quota; never switch only because Agnes is “good enough” | Healthy Codestral on clean `TechnicalSpec` — best free coding specialist |
| **debugger** | GPT-OSS-120B (code **82**, reason **90**) | Agnes (code **78**, reason **76**) | Groq 120b RPD exhausted / 429 / empty | Healthy 120b + hard traceback — raise **reasoning_effort**, do not hop early |
| **safety_filter** | Safeguard-20B (safety **92**) | Gemini Flash (safety **50**) | Safeguard 429 / unavailable | Default every research run — specialty gate |
| **context_compressor** | Agnes (reason **76**, synth **80**) | Gemini Flash (reason **78**) | Agnes quota / empty JSON | High research volume on Agnes |
| **web_search** | compound-mini (ground **88**) | *none* | **Never model-fallback** — no live search → **abort run** | Always when research needs live web |
| **grounding** | Command A+ (ground **93**, synth **78**) | Mistral Small (ground **55**, synth **65**) | Cohere trial empty / 429 / ToS | Default cited claims; scarce bucket |
| **synthesizer** | GPT-OSS-120B (synth **85**, reason **90**) | Agnes (synth **80**, large context) | Groq 120b exhausted / 429 / empty | Healthy 120b + long report — raise **reasoning_effort** |

**Runtime selection rules (code):**

1. **Expired promo** (`free_until` past, e.g. hy3 after **2026-07-21**) → role/catalog fallback; scores capped ≤49.  
2. **`primary_status` degraded** (`quota_exhausted` | `rate_limited_429` | `empty_completion` | `unavailable` | `degraded`) → role fallback if configured.  
3. **Mis-specialized:** for a relevant area, `score_fb − score_p ≥ score_advantage_threshold` (default **8**) **and** primary score ≤ `weak_specialization_max` (default **49**) — e.g. Safeguard forced onto coding.  
4. Else **keep primary** (even if fallback edges higher by a few points on a secondary area).  
5. Model switches **must** go through `record_model_selection_handoff` → `transfer_control` (user input preserved + audit).

**Also never:**

- Promote `tencent/hy3:free` as free-durable default primary/fallback.  
- Replace `compound-mini` for web_search.  
- Put Command A+ on architect/coder/debugger/synth primary.

### 4.4 Cómo se elige y se usa el modelo en un run (end-to-end)

```text
User task
   │
   ▼
DifficultyAssessment  (core/difficulty_scorer.py)
   │  areas: code, reason, ground, synth, safety  (0–100)
   │  + overall, logic_complexity, estimated_context_tokens
   ▼
select_for_role(role, assessment)  (core/model_selector.py)
   │  reads model_router.yaml primary/fallback
   │  reads model_benchmarks.yaml scores + thresholds
   │  → ModelSelection { provider, model, used_fallback, reason }
   ▼
[if used_fallback / forced_expiry]
   record_model_selection_handoff → transfer_control  (audit trail)
   ▼
resolve_reasoning_kwargs(provider, model, assessment, role)
   │  only if model is in reasoning.model_capabilities
   │  → e.g. reasoning_effort=high, include_reasoning=false
   ▼
router.call_agent  (1 quota call on success)
   │  sanitize_call_kwargs per hop (cascade strips unsupported effort)
   ▼
Worker agent (architect / coder / …) returns domain schema
```

**Who calls what:**

| Entry | Selection | Reasoning kwargs |
|-------|-----------|------------------|
| `run_structured_agent` / `run_role_raw` | yes | yes (default) |
| `invoke_router(..., assessment=, role_path=)` | no (caller fixed provider/model) | yes if assessment provided |
| Graph nodes | `select_for_role` + handoff | via agents → runtime |
| Direct `call_agent` without runtime | none | only if caller passes kwargs |

**State fields (LangGraph):** `difficulty_by_role`, `last_model_selection`, `handoff_history`.

### 4.5 Reasoning / thinking effort (same call, no extra RPD)

**Module:** `core/reasoning_params.py`  
**Config:** `config/model_benchmarks.yaml` → `reasoning:`

#### When to raise effort vs when to change model

| Situation | Prefer |
|-----------|--------|
| Hard reasoning/debug/synth, primary healthy, model supports effort | **Raise `reasoning_effort`** (low→medium→high) |
| Primary 429 / quota / empty / expired | **Fallback model** (costs another call) |
| Easy task / safety binary classify | **Keep effort low** (latency + less noise) |
| Model has no capability entry (Agnes, Codestral, Gemini, Cohere, compound-mini) | **No effort kwargs** — quality = model choice only |

#### Difficulty → abstract effort bands

| Relevant difficulty score | Effort |
|---------------------------|--------|
| &lt; 50 | `low` |
| 50–74 | `medium` |
| ≥ 75 | `high` |

Score used = max over the role’s `relevant_areas` (else `overall`).  
Then **role clamps** (YAML `role_effort`):

| Role | Clamp | Why |
|------|-------|-----|
| `vibe_coding.debugger` | min `medium` | Fix loops need deeper CoT |
| `deep_research.synthesizer` | min `medium` | Long structured reports |
| `cli.planner` | min `medium` | Multi-step plan quality |
| `deep_research.safety_filter` | max `low` | Fast allow/deny |
| `deep_research.web_search` | max `low` | Tool/search system, not long CoT |

#### Provider-native kwargs (only capable models)

| Style | Models | API params |
|-------|--------|------------|
| `groq_gpt_oss` | `groq/openai/gpt-oss-120b`, `…-20b`, `…-safeguard-20b`; `cerebras/gpt-oss-120b` | `reasoning_effort`: `low`\|`medium`\|`high`; `include_reasoning`: bool |
| `groq_qwen` | `groq/qwen/qwen3.6-27b` | abstract low→`none`, medium/high→`default`; `reasoning_format`: `hidden`\|`parsed` |

**Default for MultiAgent agents:** `include_reasoning: false` so `message.content` stays clean JSON/prose for Pydantic (CoT still runs server-side when effort &gt; none).  
Do **not** combine `include_reasoning` with `reasoning_format` on GPT-OSS (mutually exclusive on Groq).

#### Cascade safety

If hop 1 is GPT-OSS with `reasoning_effort=high` and hop 2 is Agnes, `sanitize_call_kwargs` **strips** reasoning keys before the second provider sees them (avoids HTTP 400). If hop 2 is also GPT-OSS, effort is **re-mapped** for that model + difficulty.

#### What is **not** thinking mode

- CLI progress text `thinking (round N)…` in agent chat = tool-loop UI, not API reasoning.  
- Cohere response blocks of type `thinking` = response shape parsing only (Command A+), not a request param we set.  
- Prompt-only “think step by step” is **not** a substitute for `reasoning_effort` on GPT-OSS when the API supports it.

**hy3 explicit policy:** include in benchmark tables for continuity; **do not** assign as default primary/fallback for A/B roles while free-durable defaults hold. If used under an optional `openrouter-boosted` profile, re-check availability **every execution** until after 2026-07-21 (then remove or replace). Cap scores ≤49 when expired.

---

## 5. System A — Vibe Coding (role assignments)

```text
Architect → Coder → Test Executor (local) → Debugger (≤ max_fix_cycles)
```

| Role | Primary | Fallback | Why this placement |
|------|---------|----------|--------------------|
| **architect** | `agnes` / `agnes-2.0-flash` | `gemini` / `gemini-2.0-flash` | Needs surgical JSON specs + multi-file planning. Agnes is free, agent-strong, large context, high daily soft budget — **does not burn Cohere**. Gemini is a solid structured-JSON backup with separate free quota. |
| **coder** | `mistral` / `codestral-latest` | `agnes` / `agnes-2.0-flash` | Highest coding specialization among free APIs we integrate. Agnes fallback keeps code generation alive if Mistral Experiment is rate-limited, without OpenRouter’s 50 RPD pool. |
| **debugger** | `groq` / `openai/gpt-oss-120b` | `agnes` / `agnes-2.0-flash` | Fix loops (up to 3) need strong reasoning + roomy per-model RPD. GPT-OSS-120B on Groq is fast and independent of Agnes volume. Agnes is the durable free alternate when Groq 120b is exhausted or 429s. |

**Not used as Vibe primaries:** Cohere (save for research grounding), OpenRouter `:free` (shared 50 RPD), compound-mini (search budget only), Cerebras (5 RPM too slow for fix loops).

---

## 6. System B — Deep Research (role assignments)

```text
Safety → Context compressor → Web search (+ primary URL fetch) → Grounding → Synthesizer
```

| Role | Primary | Fallback | Why this placement |
|------|---------|----------|--------------------|
| **safety_filter** | `groq` / `openai/gpt-oss-safeguard-20b` | `gemini` / `gemini-2.0-flash` | Purpose-aligned safeguard model with **its own** ~1k RPD counter — one cheap classify call per run. Gemini is a binary-classify backup. |
| **context_compressor** | `agnes` / `agnes-2.0-flash` | `gemini` / `gemini-2.0-flash` | Keyword/trend extraction is medium difficulty, high frequency. Agnes free volume replaces OpenRouter/hy3. Gemini Flash is a reliable structured alternative. |
| **web_search** | `groq` / `groq/compound-mini` | *(none — hard fail if no live search)* | **Only free stack model with integrated Tavily-class search.** ~250 RPD — must not be reused for chat/plan. Pipeline aborts if search admits it did not run live (anti-fabrication). **Also HTTP-fetches user-named domains** into a PRIMARY SOURCES block before the live dump. |
| **grounding** | `cohere` / `command-a-plus-05-2026` | `mistral` / `mistral-small-latest` | **Single Cohere primary** in the whole product. Best trial-tier anti-hallucination / documents grounding for claims+citations. Mistral Small preserves pipeline if Cohere trial is empty (lower grounding quality). Post-step **scrub** strips emails/phones/archive URLs/hex colors not present in the corpus. |
| **synthesizer** | `groq` / `openai/gpt-oss-120b` | `agnes` / `agnes-2.0-flash` | Long report assembly needs strong reasoning + large output; Groq 120b has headroom separate from safeguard and compound-mini. Agnes large-context fallback if Groq synth is exhausted. **Not Cohere** — that would double-tax the 28/day pool with grounding. Scrub again + drop sources absent from the search dump. |

**Entity focus / multi-facet search** (application logic, not a separate model role) keeps queries anchored so compressors do not blend similar business names.

**Research typology (System B — domain-agnostic):**

Before/with compression, the topic is classified into:

| Dimension | Options |
|-----------|---------|
| Purpose | `basic` (theory) · `applied` (practical problem) |
| Depth | `exploratory` · `descriptive` · `explanatory` |
| Data approach | `quantitative` · `qualitative` · `mixed` |
| Design | `experimental` · `non_experimental` |

Heuristics + compressor JSON fields feed a `ResearchProfile` used by search facets, grounding outline, and synthesizer framing. Choosing the profile defines whether the run expands theory, supports a practical decision, describes vs explains, and emphasizes numbers vs meanings — without hardcoding any industry.

**Anti-hallucination + multi-source (System B code path):**

1. Extract bare domains / URLs from the user topic (if any).
2. `fetch_user_primary_sources` → inject `=== PRIMARY SOURCES ===` (highest trust for named official sites).
3. Live multi-facet search is **domain-agnostic**: official site *plus* open-web facets from the query and from the research profile.
4. Grounding report structure: official website findings **and** third-party web findings when available; outline adapts to typology.
5. Prompts forbid inventing archive years, phones, emails, brand hex/fonts, or citation URLs unless verbatim in documents.
6. Primary HTML fetch extracts a **STRUCTURED EXTRACTS** block (JSON-LD, meta/og, CSS hex colors, wa.me/social hrefs, logo image URLs) so brand-rebuild research is not limited to visible body text after script/style stripping.
7. **Outbound presence follow-up (domain-agnostic):** buttons/schema on the official page that point to WhatsApp (`wa.me` / `api.whatsapp.com`), Instagram, Facebook, LinkedIn, TikTok, YouTube, X, mailto, or tel are decoded into an **OUTBOUND PRESENCE** corpus block (phone digits from WhatsApp links are valid contact evidence). Social profile URLs are HTTP-fetched when possible (**LINKED PRESENCE FETCHES**, parallel, short timeout) and injected as live-search facets (profile URL + posts/handle queries). No industry- or brand-specific hardcoding.
7b. **Host plausibility:** bare-domain extraction rejects Latin abbreviations (`e.g.`, `i.e.`, `U.S.`) and other false hosts so they never become `https://e.g` primary fetches or listed sources. `schema.org` / `w3.org` are vocabulary hosts, not subject sites. Primary URL fetches run in parallel with tighter timeouts; live-search facet lists are capped for latency.
8. Synthesizer recovers when free models return JSON with only `content` (missing `sources`) or bare prose, using content URLs / grounded fallback instead of failing polish.
9. `source_url_is_verified` + `scrub_ungrounded_claims` drop invented sources and strip ungrounded contacts.
9b. **`merge_host_verified_primary`:** if the host already HTTP-fetched a PRIMARY OK page but the model denies the site or omits brand tokens, re-inject structured extracts (colors, logo, wa.me, social) and force primary URLs into `sources[]`.
10. **Research → vibe chaining:** prior research is not loose prose only. `/do` injects a **GROUNDED FACTS** block (hex colors, wa.me phones, social URLs, logo assets, address lines, explicit gaps) plus hard rules so vibe cannot invent medical-green palettes, NYC map embeds, fake emails, or doctor bios. Architect/coder prompts require copying those facts and prefer file-based tests over Selenium for static sites.
10b. **Planner URL guard:** `/do` passes the original user task as `origin_prompt`. Before each research step, `ensure_origin_urls_in_research_prompt` re-injects any official domains the planner dropped (PRIMARY fetch only sees the step text). Planner rules forbid inventing USP/competitors/colors and require copying user-named domains into research prompts.
11. **Vibe test executor (pytest-only):** never runs the MultiAgent monorepo `tests/` catch-all. Only `test_*.py` from the current artifact. Marketing sites default to **static HTML/CSS/JS** (planner/architect forbid inventing Next.js/Jest unless the user asks). Static content checks enforce grounded hex/wa.me/logo strings. Next/Jest stacks fail fast with a rewrite suggestion. Failed artifacts are snapshotted to `data/vibe_last_failed/` before git rollback. Pytest is launched via repo `venv` / running `sys.executable` (`python -m pytest`), not a bare PATH binary alone.


---

## 7. CLI roles

| Role | Primary | Fallback | Why |
|------|---------|----------|-----|
| **chat** | `agnes` / `agnes-2.0-flash` | `groq` / `openai/gpt-oss-120b` | Interactive volume; tool-using host agent benefits from Agnes agent/coding strengths and free fair-use. Groq 120b backup for quality bursts. |
| **planner** (`/do`) | `agnes` / `agnes-2.0-flash` | `groq` / `openai/gpt-oss-120b` | Task split into vibe/research steps is agent-style planning — Agnes-fit. Must stay cheap and available every `/do`. |

---

## 8. Fallback cascade (provider DAG)

When a role has no usable role-level fallback, or the fallback fails, `core/router.py` walks `fallback_cascade`:

```text
cohere     → mistral-small-latest
mistral    → agnes-2.0-flash
openrouter → agnes-2.0-flash
agnes      → groq openai/gpt-oss-120b
groq       → gemini-2.0-flash
gemini     → cerebras gemma-4-31b
cerebras   → groq openai/gpt-oss-120b
```

| Edge | Rationale |
|------|-----------|
| cohere → mistral | Leave free-durable path if trial exhausted |
| openrouter → agnes | **Do not** cascade into another `:free` model (same 50 RPD bucket) |
| gemini → cerebras | Quality leaf; **not** OpenRouter free (historical starve) |
| cerebras → groq | Catalog 404 / empty content escapes Cerebras |
| agnes → groq | Dual free backbones (Agnes volume + Groq reasoning) |
| skip-visited | Prevents infinite rings (e.g. groq→gemini→…→groq) |

Empty HTTP 200 completions are treated as failures and cascade (see `EmptyCompletionError`).

---

## 9. Soft quotas in MultiAgent vs real limits

| Provider | YAML / tracker soft-cap | Real free (approx.) | Policy |
|----------|-------------------------|---------------------|--------|
| Groq | 800 / model | ~1 000 RPD / model (compound-mini ~250) | 80% safety margin |
| OpenRouter | 45 shared | 50 RPD free shared | 90% margin |
| Cohere | 28 shared | ~1 000 / month | Daily pacing |
| Mistral | 200 | Experiment rate limits | Conservative call cap |
| Gemini | 400 | Flash ~hundreds–1.5k RPD | Mid conservatism |
| Cerebras | 150 | 5 RPM + ~1M TPD | Call soft-cap under token limit |
| Agnes | 2 000 | ~20 RPM fair-use | Soft local gate |
| Ollama | 100 000 | Local | Tracking only |

---

## 10. Anti-patterns deliberately avoided

| Anti-pattern | Why it failed free-tier runs |
|--------------|------------------------------|
| Architect + grounding + synthesizer all on Cohere | ~3× burn → ~9 research runs/day |
| Coder + debugger + compressor on OpenRouter `:free` | Shared **50 RPD** exhausts in one afternoon |
| Primary on `tencent/hy3:free` past promo window | Hard 404 / expiry |
| Cascade gemini → openrouter llama:free | Soft Gemini fail becomes hard OR starve |
| Using `compound-mini` for chat/plan | Burns the only search budget (~250 RPD) |
| Cerebras Llama IDs as primary | Catalog volatility / model_not_found 404 |
| “Best leaderboard model on every node” | Ignores bucket scope and calls/run |

---

## 11. Optional profiles (not default)

| Profile | When | Sketch |
|---------|------|--------|
| **free-durable** | Default (this doc) | As above |
| **openrouter-boosted** | Lifetime ≥ $10 OR credits → 1 000 free RPD | Can put coder/debugger on strong `:free` models |
| **free-max-quality** | Prefer quality over latency | Synthesizer/coder → Cerebras gpt-oss / gemma-4 (watch 5 RPM) |
| **local-first** | Offline / privacy | Ollama for architect/coder/synth; keep compound-mini + keys for search/safety |

Change live roles with:

```bash
multiagent config show
multiagent config set vibe_coding.coder mistral codestral-latest
multiagent config reset   # restore defaults_model_router.yaml → model_router.yaml
```

---

## 12. Key checklist for free-durable defaults

| Env | Used by default as |
|-----|--------------------|
| `AGNES_API_KEY` | chat, planner, architect, compressor (+ several fallbacks) |
| `MISTRAL_API_KEY` | coder primary; grounding fallback |
| `GROQ_API_KEY` | debugger, safety, web_search, synthesizer |
| `COHERE_API_KEY` | grounding primary only |
| `GEMINI_API_KEY` | role/cascade fallbacks |
| `CEREBRAS_API_KEY` | cascade quality leaf |
| `OPENROUTER_API_KEY` | optional / catalog only |
| Ollama | no key; optional override |

```bash
multiagent keys set agnes
multiagent keys set mistral
multiagent keys set groq
multiagent keys set cohere
multiagent providers
multiagent config show
multiagent quota
```

---

## 13. Source map (research)

| Topic | Primary references |
|-------|-------------------|
| Groq RPD/RPM | console.groq.com/docs/rate-limits |
| OpenRouter free 50/1000 | openrouter.ai docs limits / FAQ |
| Cohere trial 1k/mo | docs.cohere.com rate-limits |
| Cerebras free 5 RPM / 1M TPD | inference-docs.cerebras.ai |
| Gemini free tier | ai.google.dev Gemini rate limits + AI Studio |
| Agnes free models & ~20 RPM | wiki.agnes-ai.com, AgnesAI-Models GitHub (2026-06-28) |
| GPT-OSS-120B intelligence / speed | artificialanalysis.ai/models/gpt-oss-120b |
| GPT-OSS Safeguard 20B | console.groq.com/docs/model/openai/gpt-oss-safeguard-20b ; OpenAI open safety posts |
| Codestral HumanEval etc. | mistral.ai/news/codestral-2501 (HumanEval 86.6% for Codestral-2501) |
| Command A RAG / grounding | cohere.com Command A technical report (arXiv 2504.00698 family) |
| Compound Mini + RealtimeEval / Tavily | console.groq.com Compound / web-search docs |
| Claw-Eval agent scores | claw-eval / benchlm Claw-Eval tables (Agnes-2.0-flash ~51.8% Pass^3) |
| Relative model quality | Artificial Analysis, Claw-Eval, vendor cards, independent coding scorecards 2026 |
| Role → model binding | `config/model_router.yaml` + `core/agent_config.get_agent_config` |
| Difficulty + primary/fallback | `config/model_benchmarks.yaml` + `core/difficulty_scorer.py` + `core/model_selector.py` |
| Reasoning effort (GPT-OSS / Qwen) | [Groq Reasoning docs](https://console.groq.com/docs/reasoning) + `core/reasoning_params.py` |
| Handoff audit | `docs/handoff_protocol.md` + `core/handoff.py` |

Re-validate limits and **promo expiry** (`tencent/hy3:free` → **2026-07-21**) in each provider console before production-ish unattended runs; update this file, YAML soft-caps, and reasoning capability entries together when free tiers change.
