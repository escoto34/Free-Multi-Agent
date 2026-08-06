# Systems orchestration — free-durable profile

**Document status:** mid-2026 research snapshot (last updated 2026-08-05, WAVE-21 score-driven `select_for_role` live + 4 roles re-tuned to `cerebras/gpt-oss-120b`; WAVE-20 scoring v2: measured efficiency axis + re-scored benchmarks; WAVE-18 role consolidation: architect→coder, safety_filter→compressor)  
**Live config:** `config/model_router.yaml` (loaded by `core/agent_config.py`)  
**Factory defaults:** `config/defaults_model_router.yaml`  
**Quota soft-caps:** `core/quotas.py` (must stay ≤ real provider limits)  
**Benchmarks + selection + reasoning:** `config/model_benchmarks.yaml`

> **WAVE-21 (2026-08-05) — done:** `select_for_role` (`core/model_selector.py`) is now **score-driven**: it ranks every available/unexpired/quota-healthy catalog model by `fitness` (`core/model_scoring.py`, quality 0.75 + efficiency 0.25) and actually acts on the difficulty `assessment` (the WAVE-20 stub that `del assessment, hard_th` discarded is gone). New rules landed: **hard-threshold escalation** (`relevant_max(areas) ≥ hard_threshold` ⇒ the picked model's role quality must also clear it), **anti-churn hysteresis** (healthy primary only yields to a candidate ahead by ≥ `score_advantage_threshold` = 8), **`pin: true`** (structural no-swap, e.g. `deep_research.web_search`), and quota degradation **derived from the live ledger** via `quota_remaining=` (`default_quota_remaining`). The `cli.chat` / `cli.planner` bypass is gone — chat turns, `/do` planning and `_compact --llm` resolve through `resolve_role_selection("cli","chat"|"planner")` and carry `role_path`. Four roles re-tuned to `cerebras/gpt-oss-120b` on fitness (coder, context_compressor, cli.chat, cli.planner), each keeping its former primary as the role fallback; `deep_research.web_search` is `pin: true`. Perf: `provider_registry` + `model_scoring._providers` now cache the YAML (a wave-21 candidate scan was re-reading `model_router.yaml` per candidate — a single select went 14.6s → ~0.4s). `tests/test_wave21.py` adds the wave's mandatory tests (hysteresis, escalation, pin, quota-derived status, `role_path` on chat turns, cli.chat difficulty bias).

> **WAVE-20 (2026-08-04) — done:** scoring v2 landed. `config/model_benchmarks.yaml` is now schema v2 (`quality_aggregate` block under `selection_defaults` replaces the hardcoded aggregate coefficients — `core/difficulty_scorer.py` reads them, byte-identical `overall`; dead `selection_defaults` keys removed). New `core/model_scoring.py` provides the score-driven vocabulary (`quality_for_role`, `efficiency_score`, `fitness`, `rank_candidates`) that WAVE-21 will route on. `scripts/benchmark_models.py` measured **live efficiency** (ttft, tokens/sec, context) for all 43 benchmarkable catalog models on 2026-08-04 → `config/model_efficiency.json`; every benchmark row now carries `efficiency` + `evidence` + `verified` (guard-tested). Quality bands of the WAVE-19 rows were re-scored from public/vendor sources. `fitness = 0.75·quality + 0.25·efficiency`.

> **WAVE-19 (2026-08-04) — done:** CI `gpt-researcher` pin fixed (moved to a `research` optional extra), `scripts/probe_providers.py` added, provider catalogs refreshed from live `/models` probes (dead models removed, new live free models added, opencode_zen verified with a real key, hy3 expiry mechanism generalized to any row's `free_until`).

This document explains **why** each free-tier model sits in each System A / System B / CLI role: benchmarks (relative quality), a reusable **0–100 scoring rubric**, API rate limits, orchestration constraints (shared buckets, cascade design, calls per run), **how primary vs fallback is chosen at runtime**, and **how reasoning/thinking effort is applied inside each call**.

> **Runtime modules (implemented):**  
> `core/difficulty_scorer.py` · `core/model_selector.py` · `core/reasoning_params.py` ·  
> `core/handoff.py` · `core/agent_runtime.py` · `core/router.py` · `core/quotas.py`

---

## 0. Live role inventory (primary + fallback)

Source of truth: `config/model_router.yaml` via `get_agent_config(...)` in `core/agent_config.py`.  
Roles requested for scoring (WAVE-18: `architect` folded into `coder`; `safety_filter` folded into `context_compressor`): System A (`coder`, `debugger`) and System B (`context_compressor`, `web_search`, `grounding`, `synthesizer`).

| Pipeline | Role | Primary `provider` / `model` | Fallback `provider` / `model` |
|----------|------|------------------------------|-------------------------------|
| **A — Vibe** | `coder` *(merged plan+implement)* | `cerebras` / `gpt-oss-120b` | `mistral` / `codestral-latest` |
| **A — Vibe** | `debugger` | `groq` / `openai/gpt-oss-120b` | `agnes` / `agnes-2.0-flash` |
| **B — Research** | `context_compressor` *(incl. safety gate)* | `cerebras` / `gpt-oss-120b` | `agnes` / `agnes-2.0-flash` |
| **B — Research** | `web_search` | `groq` / `groq/compound-mini` | **none** (hard-fail if no live search) |

The `web_search` role is **wired, not reserved**: one bounded LLM call per run expands a vague topic into concrete DuckDuckGo facets (`expand_query_facets`), then the live DDG scrape + page fetches run. The expansion call is optional — if quota/network fails, the heuristic facet builder is used unchanged; the live-search requirement is unchanged (pipeline still hard-aborts if the search admits it did not run live). WAVE-21: this role is `pin: true` in `config/model_benchmarks.yaml` — `select_for_role` never proposes a swap for it.
| **B — Research** | `grounding` | `cohere` / `command-a-plus-05-2026` | `mistral` / `mistral-small-latest` |
| **B — Research** | `synthesizer` | `groq` / `openai/gpt-oss-120b` | `agnes` / `agnes-2.0-flash` |

**Unique models in the live hot path (primary or role-level fallback):**  
`cerebras/gpt-oss-120b`, `codestral-latest`, `agnes-2.0-flash`, `openai/gpt-oss-120b`, `groq/compound-mini`, `command-a-plus-05-2026`, `mistral-small-latest`.

**Catalog-only (not currently assigned as primary/fallback to those roles):**  
`tencent/hy3:free` remains in the OpenRouter free catalog and is scored below for historical/optional use.  
**⚠ `tencent/hy3:free` promo window ended 2026-07-21** — treat as **expired / non-durable**; verified absent from any hot-path default. Keep the row only for historical/optional profiles, never as free-durable capacity.

CLI (`chat`, `planner`) uses Cerebras 120b → Agnes fallback — they now route through `select_for_role`/`resolve_role_selection(name)` just like pipeline roles; see §7. Provider-level `fallback_cascade` is §8.

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
| **System A — Vibe** | 1–4 | Coder (1; merged planner, WAVE-18) + Debugger (0–3 fix cycles; can fix directly via `fixed_files` → local `fix_applier`, no coder extra call) |
| **System B — Research** | 4–5 | Compressor (incl. safety gate, WAVE-18) + web_search + grounding + synthesizer; web_search includes **+1 optional** bounded query-expansion LLM call (WAVE-11) that falls back to heuristic facets on any failure |
| **CLI `/do`** | +1 planner | Then N× vibe and/or research (independent steps may run in parallel, WAVE-15) |
| **chat `run_pipeline` tool (WAVE-17)** | same as `/do` | No new call shape — same planner + per-step calls; `cli.llm_compact=True` adds **1 chat call per compaction** (off by default) |

**RPD picture after WAVE-09B/10/11/15/18 (recomputed):** LLM *call counts* are
unchanged by WAVE-09B (HTTP cache cuts network fetches, not LLM calls), WAVE-10
(parallelism cuts wall-clock, not calls), and WAVE-15 (parallel plan steps make
the same per-step calls concurrently). WAVE-18 **reduces** counts (role consolidation, §2.1); the only *added* count is the **+1
optional web_search expansion call** above. So the budget ceiling stands: if
Cohere (~28/day) sat only on grounding, the bound is ~28 full reports/day (or
~250/day when `compound-mini`'s RPD is the tighter limit); three Cohere roles
would still collapse to ~9/day — see §10.

### 2.1 WAVE-18 role consolidation (call-count reduction)

WAVE-18 cuts LLM calls by folding two roles into a neighbor's system prompt instead of deleting their work:

| Consolidation | Before | After | Improvement |
|---------------|--------|-------|-------------|
| `architect` → `coder` (merged plan+implement; debugger stays separate) | A happy path = **3 calls** | **2 calls** (implementer + debugger) | **-33% happy path** |
| `architect` → `coder` (guaranteed, no debugger editor) | A avg (real `runs.db` mix 12 runs: 1×1, 4×2, 7×3) ≈ **6.0 calls/run** | ~5.0 calls/run | **-17%** |
| …plus `debugger` hybrid editor (`fixed_files` → local `fix_applier`) | 5.0 calls/run | ~4.4 calls/run | **-27%** |
| `safety_filter` → `context_compressor` | B = **5 calls** | **4 calls** (compressor incl. gate) | **-20%** |
| **Combined System A+B** | — | — | **~-22%** |

The `fix_applier` node writes the debugger's corrected files and re-runs tests (a local node, **counts 0 LLM calls**) — the cheaper edge of the fix loop. Only when the debugger is unsure (file not fully visible) does it emit `suggested_fix` and the coder loop still runs. The **rejected** candidate was merging `grounding`+`synthesizer`: the two-pass scrub/verify (grounding RAG `documents=` + synthesizer re-scrub) is the anti-hallucination core, so merging would save 1 call but add fabrication risk — not worth it.

### 2.2 Latency (WAVE-10 — concurrent fetching)

The three HTTP loops that were serial are now parallel (ThreadPoolExecutor, `min(3, n)` workers), so their wall-clock is ~`ceil(n/3)×` per-request timeout instead of `n×`:

| Loop | Before (worst case) | After (measured bound) |
|------|---------------------|------------------------|
| Per-facet DDG search (≤12 facets × 12 s) | ~144 s | ~48 s |
| Up-to-8 result-page fetches (× 12 s) | ~96 s | ~36 s |
| `verify_cited_urls` ≤ 8 URLs (× 6 s) | ~48 s | ~24 s (first/cold call) |

Per-request timeouts unchanged; WAVE-09B's cache makes the second `verify_cited_urls` (synthesis) essentially free regardless.

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
| `groq/compound` | 30 | **~250** | Full compound system (web search + reasoning); catalog alternate (WAVE-19) |
| `llama-3.3-70b-versatile` | 30 | **1 000** | General 70B; live again per 2026-08-04 probe (WAVE-19) |
| (other Llama/Qwen) | 30–60 | 1 000–14.4k | Some small models historically higher RPD |

- **Scope:** per-model counters (good for spreading roles).  
- **YAML soft-cap:** 800 RPD/model (`daily_limit_per_model`).  
- **Sources:** [Groq rate limits docs](https://console.groq.com/docs/rate-limits), community free-tier summaries 2026.

### 3.2 Agnes AI

| Model ID | Endpoint | Free notes |
|----------|----------|------------|
| **`agnes-2.0-flash`** | `/v1/chat/completions` | Free / $0 per M tokens (promo pricing); ~**20 RPM** free/default plan; large context (docs cite 256K–512K depending on revision); tool-calling, coding, agents; Claw-Eval ~top-10 general / strong agent Pass^3 |
| `agnes-2.5-flash` | `/v1/chat/completions` | Newer text model, live per 2026-08-04 probe (WAVE-19); catalog alternate |
| `agnes-2.5-pro` | `/v1/chat/completions` | Larger text model, live per 2026-08-04 probe (WAVE-19); catalog alternate |
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
| `devstral-medium-latest` | Coding alternate | Live per 2026-08-04 probe (WAVE-19); catalog option |
| `mistral-medium-3-5` | General quality | Newer medium line, live per probe (WAVE-19) |
| `ministral-14b-latest` | Small general | Live per probe (WAVE-19) |
| `magistral-small-latest` | Reasoning-tuned small | Live per probe (WAVE-19) |

- **YAML soft-cap:** 200 calls/day (conservative; console Limits page is source of truth).  
- **Sources:** Mistral admin docs / Experiment free tier posts 2025–2026.

### 3.4 Google AI Studio (Gemini)

| Model ID | Free RPM (approx.) | Free RPD (approx.) | Notes |
|----------|--------------------|--------------------|--------|
| `gemini-2.5-flash` | ~10–15 | ~250–1 500 | Varies by account/tier updates |
| `gemini-2.0-flash` | ~15 | often more available for new free users | **Preferred fallback ID** for reliability |
| `gemini-2.5-flash-lite` | higher | higher | Cheap structured extract |
| `gemini-3.1-flash-lite`, `gemini-3-flash-preview` | higher | higher | New flash-lite line, live per 2026-08-04 probe (WAVE-19) |
| `gemini-3.5-flash`, `gemini-3.5-flash-lite`, `gemini-3.6-flash` | ~10–15 | ~250–1 500 | Newer flash line, live per probe (WAVE-19) |
| `gemma-4-31b-it`, `gemma-4-26b-a4b-it` | ~5–10 | ~250 | Open gemma-4 line on AI Studio, live per probe (WAVE-19) |
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
| `google/gemma-4-31b-it:free`, `google/gemma-4-26b-a4b-it:free` | Open gemma-4 line (WAVE-19) |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | 1M context flagship (WAVE-19) |
| `nvidia/nemotron-3-super-120b-a12b:free`, `nvidia/nemotron-3-nano-30b-a3b:free` | Nemotron line (WAVE-19) |
| `nvidia/nemotron-3.5-content-safety:free` | Safety-tuned classifier (WAVE-19) |
| `openai/gpt-oss-20b:free` | Open reasoning sibling (WAVE-19) |
| `inclusionai/ling-3.0-flash:free`, `poolside/laguna-s-2.1:free`, `poolside/laguna-xs-2.1:free` | Other live :free alternates (WAVE-19) |

> **WAVE-19 (2026-08-04 live probe):** `tencent/hy3:free`, `meta-llama/llama-3.3-70b-instruct:free`, `google/gemma-3-27b-it:free` and `qwen/qwen3-32b:free` are **gone** from the live catalog and removed. The `tencent/hy3:free` benchmark row remains as the documented `free_until` expiry example (mechanism is row-driven, no hardcoded constant).

- **YAML soft-cap:** 45 RPD shared.  
- **Orchestration decision:** **off hot path** for free-durable defaults. Cascade `openrouter_fallback` → Agnes, not deeper free OR.  
- **Sources:** [OpenRouter limits](https://openrouter.ai/docs/api_reference/limits).

### 3.8 Ollama (local)

| Item | Value |
|------|--------|
| Limits | Hardware only (local soft-cap 100 000 in tracker) |
| Models | **Only** what `ollama list` reports — no static catalog |
| Role fit | Optional override for privacy / offline; not default cloud path |

### 3.9 OpenCode Zen (WAVE-08)

| Item | Value |
|------|--------|
| Limits | Free tier, no card — per-model rate limits **not publicly documented**; tracker soft-cap 100 shared/day (conservative placeholder, adjust once observed) |
| Endpoint | `https://opencode.ai/zen/v1` (OpenAI-compatible), signup `opencode.ai/auth` |
| Free models | `big-pickle`, `deepseek-v4-flash-free`, `nemotron-3-ultra-free`, `mimo-v2.5-free`, `north-mini-code-free`, `laguna-s-2.1-free`, `ling-3.0-flash-free` |
| Role fit | **Catalog / fallback tier only** — not assigned as any primary role (WAVE-08 prohibition) |

> **WAVE-19 (2026-08-04):** verified live with a real `OPENCODE_ZEN_API_KEY` — 7/7 configured models confirmed; `hy3-free` is gone from the live catalog and was removed. The WAVE-08 "never verified against a real key" gap is closed.

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
| **(b) reason** | Razonamiento y planificación | MMLU-Pro / GPQA / AIME-class hard reasoning, multi-step plans, structured specs (coder / compressor / planner) |
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

**Efficiency axis (WAVE-20, measured live 2026-08-04):**

| Axis | Weight | Definition |
|------|--------:|------------|
| **speed** | 0.50 | tokens/sec on one 128-token streaming completion (incl. reasoning tokens), stack-relative linear |
| **context** | 0.25 | live `/models` context window (or documented provider fallback), log-normalized to the stack |
| **capacity** | 0.25 | tps × context throughput, stack-relative linear |

`efficiency_score = 0.50·speed + 0.25·context + 0.25·capacity`; model `fitness = quality_weight·quality + efficiency_weight·efficiency` (`0.75` / `0.25`, `config/model_benchmarks.yaml` `selection_defaults`). Measured rows live in `config/model_efficiency.json`; providers without a documented context window (opencode_zen) get **0** credit on context/capacity. Reasoning-heavy models that spend the whole 128-token budget thinking report efficiency 0 — that is the rubric intent (poor user-visible latency).

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
| **`openrouter` / `tencent/hy3:free`** ⚠ | 55 | 60 | 38 | 58 | 35 | **Expired promo (window ended 2026-07-21).** Sparse independent benches; historically general free chat. **Not durable free capacity.** Cap auto-score ≤49 (expired). `sparse` |

**Catalog backfill (WAVE-06 + WAVE-19, re-scored WAVE-20):** rows below cover every model registered in `config/model_router.yaml` — the silent flat-60 fallback for unscored models is a loud CI failure. WAVE-19 rows were proven **live** on 2026-08-04 via `/models` probes; WAVE-20 re-scored the quality bands from public/vendor sources (`quality_evidence: research_2026-08-04`) and measured **live efficiency** per model (one 128-token streaming completion; `evidence: measured`). Efficiency errors are recorded per row (`benchmark_error` + note) — e.g. gemini-2.0/2.5-flash are unusable on this key (quota 0 / 404) and poolside laguna-s/xs never reached content in 128 thinking tokens. Full probe: `python scripts/benchmark_models.py --yes --write` (dry-run default; `--refresh-context` rescales context without new calls).

| Model (provider ID) | (a) code | (b) reason | (c) ground | (d) synth | (e) safety | Evidence notes |
|---------------------|--------:|----------:|----------:|---------:|----------:|--------------------------------------------|
| **`mistral` / `codestral-latest`** | **88** | 62 | 40 | 55 | 35 | public+vendor |
| **`groq` / `openai/gpt-oss-120b`** | 82 | **90** | 48 | **85** | 45 | public+vendor |
| **`agnes` / `agnes-2.0-flash`** | 78 | 76 | 42 | 80 | 40 | public+vendor |
| **`gemini` / `gemini-2.0-flash`** | 70 | 78 | 55 | 75 | 50 | WAVE-20 live-probe error (see note) |
| **`cohere` / `command-a-plus-05-2026`** | 58 | 72 | **93** | 78 | 48 | WAVE-20 measured efficiency |
| **`mistral` / `mistral-small-latest`** | 58 | 62 | 55 | 65 | 40 | WAVE-20 measured efficiency |
| **`groq` / `groq/compound-mini`** | 50 | 58 | **88** | 52 | 30 | WAVE-20 measured efficiency |
| **`groq` / `openai/gpt-oss-safeguard-20b`** | 35 | 55 | 30 | 40 | **92** | non-conversational (no chat benchmark) |
| **`openrouter` / `tencent/hy3:free`** ⚠ | 55 | 60 | 38 | 58 | 35 | expired promo example |



| Model (provider ID) | (a) code | (b) reason | (c) ground | (d) synth | (e) safety | Notes |
|---------------------|--------:|----------:|----------:|---------:|----------:|-------|
| **`groq` / `openai/gpt-oss-20b`** | 72 | 80 | 44 | 72 | 40 | WAVE-20 measured efficiency |
| **`groq` / `qwen/qwen3.6-27b`** | 70 | 84 | 42 | 70 | 38 | re-scored WAVE-20 + measured efficiency |
| **`groq` / `groq/compound`** | 52 | 64 | **90** | 54 | 30 | re-scored WAVE-20 + measured efficiency |
| **`groq` / `llama-3.3-70b-versatile`** | 62 | 68 | 44 | 60 | 38 | re-scored WAVE-20 + measured efficiency |
| **`agnes` / `agnes-2.5-flash`** | 70 | 72 | 42 | 72 | 40 | re-scored WAVE-20 + measured efficiency |
| **`agnes` / `agnes-2.5-pro`** | 66 | 70 | 44 | 68 | 38 | re-scored WAVE-20 + measured efficiency |
| **`cohere` / `command-r-plus-08-2024`** | 54 | 68 | **88** | 72 | 44 | WAVE-20 measured efficiency |
| **`cohere` / `command-r7b-12-2024`** | 50 | 60 | 80 | 62 | 40 | WAVE-20 measured efficiency |
| **`mistral` / `mistral-medium-latest`** | 66 | 68 | 48 | 64 | 38 | WAVE-20 measured efficiency |
| **`mistral` / `devstral-latest`** | 80 | 58 | 36 | 52 | 34 | WAVE-20 measured efficiency |
| **`mistral` / `ministral-8b-latest`** | 56 | 54 | 40 | 50 | 34 | WAVE-20 measured efficiency |
| **`mistral` / `devstral-medium-latest`** | 70 | 58 | 36 | 52 | 34 | re-scored WAVE-20 + measured efficiency |
| **`mistral` / `mistral-medium-3-5`** | 68 | 72 | 48 | 66 | 38 | re-scored WAVE-20 + measured efficiency |
| **`mistral` / `ministral-14b-latest`** | 62 | 58 | 40 | 54 | 34 | re-scored WAVE-20 + measured efficiency |
| **`mistral` / `magistral-small-latest`** | 62 | 68 | 40 | 60 | 36 | re-scored WAVE-20 + measured efficiency |
| **`gemini` / `gemini-2.5-flash`** | 74 | 82 | 58 | 78 | 52 | live probe 2026-08-04: 404 'no longer available to new users' -> currently unusable (follow-up: remove from catalog). |
| **`gemini` / `gemini-2.5-flash-lite`** | 66 | 74 | 52 | 70 | 48 | live probe 2026-08-04: 404 'no longer available to new users' -> currently unusable (follow-up: remove from catalog). |
| **`gemini` / `gemini-3.1-flash-lite`** | 60 | 68 | 46 | 60 | 42 | re-scored WAVE-20 + measured efficiency |
| **`gemini` / `gemini-3-flash-preview`** | 68 | 76 | 50 | 70 | 44 | re-scored WAVE-20 + measured efficiency |
| **`gemini` / `gemini-3.5-flash`** | 68 | 78 | 50 | 72 | 44 | re-scored WAVE-20 + measured efficiency |
| **`gemini` / `gemini-3.5-flash-lite`** | 62 | 70 | 46 | 62 | 42 | re-scored WAVE-20 + measured efficiency |
| **`gemini` / `gemini-3.6-flash`** | 70 | 82 | 52 | 74 | 46 | re-scored WAVE-20 + measured efficiency |
| **`gemini` / `gemma-4-31b-it`** | 68 | 74 | 44 | 64 | 40 | re-scored WAVE-20 + measured efficiency |
| **`gemini` / `gemma-4-26b-a4b-it`** | 66 | 72 | 42 | 62 | 38 | re-scored WAVE-20 + measured efficiency |
| **`cerebras` / `gemma-4-31b`** | 74 | 80 | 46 | 72 | 42 | WAVE-20 measured efficiency |
| **`cerebras` / `gpt-oss-120b`** | 82 | **90** | 48 | **85** | 45 | WAVE-20 measured efficiency |
| **`cerebras` / `zai-glm-4.7`** | 68 | 76 | 44 | 66 | 40 | live probe 2026-08-04: empty stream (finish=length, 128 tokens) -> efficiency 0 until validated with tool/reasoning invocation. |
| **`openrouter` / `cohere/north-mini-code:free`** | 64 | 56 | 38 | 50 | 32 | re-scored WAVE-20 + measured efficiency |
| **`openrouter` / `google/gemma-4-31b-it:free`** | 68 | 74 | 44 | 64 | 40 | live probe 2026-08-04: upstream 429 (OpenRouter shared pool) on both attempts. |
| **`openrouter` / `google/gemma-4-26b-a4b-it:free`** | 66 | 72 | 42 | 62 | 38 | re-scored WAVE-20 + measured efficiency |
| **`openrouter` / `inclusionai/ling-3.0-flash:free`** | 62 | 62 | 38 | 58 | 34 | re-scored WAVE-20 + measured efficiency |
| **`openrouter` / `nvidia/nemotron-3-nano-30b-a3b:free`** | 62 | 62 | 38 | 58 | 36 | re-scored WAVE-20 + measured efficiency |
| **`openrouter` / `nvidia/nemotron-3-super-120b-a12b:free`** | 66 | 70 | 40 | 62 | 38 | re-scored WAVE-20 + measured efficiency |
| **`openrouter` / `nvidia/nemotron-3-ultra-550b-a55b:free`** | 70 | 74 | 40 | 68 | 40 | re-scored WAVE-20 + measured efficiency |
| **`openrouter` / `nvidia/nemotron-3.5-content-safety:free`** | 50 | 54 | 34 | 50 | 62 | non-conversational content-safety classifier -> not chat-benchmarked. |
| **`openrouter` / `openai/gpt-oss-20b:free`** | 72 | 78 | 42 | 68 | 40 | re-scored WAVE-20 + measured efficiency |
| **`openrouter` / `poolside/laguna-s-2.1:free`** | 60 | 62 | 36 | 54 | 32 | live probe 2026-08-04: empty stream in 128 tokens -> efficiency 0 (heavy reasoning). |
| **`openrouter` / `poolside/laguna-xs-2.1:free`** | 56 | 58 | 34 | 50 | 30 | live probe 2026-08-04: empty stream in 128 tokens -> efficiency 0 (heavy reasoning). |
| **`opencode_zen` / `big-pickle`** | 62 | 62 | 38 | 58 | 34 | re-scored WAVE-20 + measured efficiency |
| **`opencode_zen` / `deepseek-v4-flash-free`** | 66 | 72 | 40 | 62 | 36 | re-scored WAVE-20 + measured efficiency |
| **`opencode_zen` / `nemotron-3-ultra-free`** | 62 | 66 | 38 | 56 | 34 | re-scored WAVE-20 + measured efficiency |
| **`opencode_zen` / `mimo-v2.5-free`** | 60 | 60 | 36 | 54 | 32 | re-scored WAVE-20 + measured efficiency |
| **`opencode_zen` / `north-mini-code-free`** | 60 | 54 | 36 | 50 | 32 | re-scored WAVE-20 + measured efficiency |
| **`opencode_zen` / `laguna-s-2.1-free`** | 56 | 58 | 34 | 48 | 30 | live probe 2026-08-04: heavy reasoning consumed the 128-token budget before content -> efficiency 0 (slow UX). |
| **`opencode_zen` / `ling-3.0-flash-free`** | 62 | 64 | 38 | 54 | 34 | re-scored WAVE-20 + measured efficiency |



| Model (provider ID) | tok/s | TTFT (ms) | ctx | speed | context | capacity |
|---------------------|------:|----------:|----:|------:|--------:|---------:|
| **`agnes` / `agnes-2.0-flash`** | 133.5 | 12587 | 100,000 | 4 | 83 | 0.5 |
| **`agnes` / `agnes-2.5-flash`** | 1740.0 | 15865 | 100,000 | 59 | 83 | 5.9 |
| **`agnes` / `agnes-2.5-pro`** | 55.7 | 4920 | 100,000 | 2 | 83 | 0.2 |
| **`cerebras` / `gemma-4-31b`** | 2945.7 | 515 | 131,072 | 100 | 85 | 13.1 |
| **`cerebras` / `gpt-oss-120b`** | 1675.6 | 468 | 131,072 | 57 | 85 | 7.5 |
| **`cohere` / `command-a-plus-05-2026`** | 216.5 | 412 | 436,000 | 7 | 94 | 3.2 |
| **`cohere` / `command-r-plus-08-2024`** | 14.4 | 432 | 128,000 | 0 | 85 | 0.1 |
| **`cohere` / `command-r7b-12-2024`** | 69.8 | 382 | 132,000 | 2 | 85 | 0.3 |
| **`gemini` / `gemini-3-flash-preview`** | 1847.7 | 17932 | 1,000,000 | 63 | 100 | 62.7 |
| **`gemini` / `gemini-3.1-flash-lite`** | 153.1 | 789 | 1,000,000 | 5 | 100 | 5.2 |
| **`gemini` / `gemini-3.5-flash`** | 582.0 | 8099 | 1,000,000 | 20 | 100 | 19.8 |
| **`gemini` / `gemini-3.5-flash-lite`** | 123.6 | 737 | 1,000,000 | 4 | 100 | 4.2 |
| **`gemini` / `gemini-3.6-flash`** | 36.3 | 1460 | 1,000,000 | 1 | 100 | 1.2 |
| **`gemini` / `gemma-4-26b-a4b-it`** | 28.0 | 921 | 1,000,000 | 1 | 100 | 1.0 |
| **`gemini` / `gemma-4-31b-it`** | 20.4 | 1106 | 1,000,000 | 1 | 100 | 0.7 |
| **`groq` / `groq/compound`** | 477.2 | 1468 | 131,072 | 16 | 85 | 2.1 |
| **`groq` / `groq/compound-mini`** | 479.1 | 805 | 131,072 | 16 | 85 | 2.1 |
| **`groq` / `llama-3.3-70b-versatile`** | 277.6 | 483 | 131,072 | 9 | 85 | 1.2 |
| **`groq` / `openai/gpt-oss-120b`** | 471.0 | 652 | 131,072 | 16 | 85 | 2.1 |
| **`groq` / `openai/gpt-oss-20b`** | 1215.0 | 642 | 131,072 | 41 | 85 | 5.4 |
| **`groq` / `qwen/qwen3.6-27b`** | 446.2 | 458 | 131,072 | 15 | 85 | 2.0 |
| **`mistral` / `codestral-latest`** | 166.1 | 791 | 256,000 | 6 | 90 | 1.4 |
| **`mistral` / `devstral-latest`** | 38.8 | 629 | 262,144 | 1 | 90 | 0.3 |
| **`mistral` / `devstral-medium-latest`** | 46.6 | 676 | 262,144 | 2 | 90 | 0.4 |
| **`mistral` / `magistral-small-latest`** | 82.2 | 765 | 262,144 | 3 | 90 | 0.7 |
| **`mistral` / `ministral-14b-latest`** | 99.2 | 660 | 262,144 | 3 | 90 | 0.9 |
| **`mistral` / `ministral-8b-latest`** | 108.5 | 601 | 262,144 | 4 | 90 | 1.0 |
| **`mistral` / `mistral-medium-3-5`** | 65.8 | 603 | 262,144 | 2 | 90 | 0.6 |
| **`mistral` / `mistral-medium-latest`** | 165.6 | 611 | 262,144 | 6 | 90 | 1.5 |
| **`mistral` / `mistral-small-latest`** | 141.2 | 690 | 262,144 | 5 | 90 | 1.3 |
| **`opencode_zen` / `big-pickle`** | 75.5 | 1265 | 0 | 3 | 0 | 0.0 |
| **`opencode_zen` / `deepseek-v4-flash-free`** | 89.8 | 1648 | 0 | 3 | 0 | 0.0 |
| **`opencode_zen` / `ling-3.0-flash-free`** | 358.1 | 2336 | 0 | 12 | 0 | 0.0 |
| **`opencode_zen` / `mimo-v2.5-free`** | 31.8 | 3448 | 0 | 1 | 0 | 0.0 |
| **`opencode_zen` / `nemotron-3-ultra-free`** | 130.9 | 2859 | 0 | 4 | 0 | 0.0 |
| **`opencode_zen` / `north-mini-code-free`** | 28.2 | 6028 | 0 | 1 | 0 | 0.0 |
| **`openrouter` / `cohere/north-mini-code:free`** | 10.2 | 3872 | 256,000 | 0 | 90 | 0.1 |
| **`openrouter` / `google/gemma-4-26b-a4b-it:free`** | 17.8 | 1149 | 262,144 | 1 | 90 | 0.2 |
| **`openrouter` / `inclusionai/ling-3.0-flash:free`** | 224.0 | 816 | 262,144 | 8 | 90 | 2.0 |
| **`openrouter` / `nvidia/nemotron-3-nano-30b-a3b:free`** | 167.6 | 814 | 256,000 | 6 | 90 | 1.5 |
| **`openrouter` / `nvidia/nemotron-3-super-120b-a12b:free`** | 128.3 | 1111 | 262,144 | 4 | 90 | 1.1 |
| **`openrouter` / `nvidia/nemotron-3-ultra-550b-a55b:free`** | 54.4 | 1176 | 1,000,000 | 2 | 100 | 1.8 |
| **`openrouter` / `openai/gpt-oss-20b:free`** | 46.4 | 5827 | 131,072 | 2 | 85 | 0.2 |

**Quick capability matrix (stack defaults):**

| Capability | Strong free options | Weaker / avoid as primary |
|------------|---------------------|---------------------------|
| **(a) Coding** | Codestral; Agnes; GPT-OSS-120B | Safeguard-20B; pure search systems |
| **(b) Reasoning / plan** | GPT-OSS-120B; Gemini Flash; Agnes | Safeguard-only; expired hy3 |
| **(c) Search / ground** | compound-mini (live search); Command A+ (RAG/citas) | Models that invent citations without corpus |
| **(d) Synthesis** | GPT-OSS-120B; Agnes (context); Command A+; Gemini | Mini search system as sole writer |
| **(e) Safety** | Compressor LLM gate + host hard-regex pre-gate (WAVE-18) | Random general chat for policy gates |
| **Live web search** | **Only** `groq/compound-mini` in this free stack | Models that “pretend” to search |

### 4.3 Recomendación primario vs fallback por rol (WAVE-21 score-driven)

Política **implementada** en `core/model_selector.py` (`select_for_role`) + reglas en `config/model_benchmarks.yaml` (`score_advantage_threshold: 8`, `hard_threshold`, `pin`, `capacity_margin`). El planeador emite un `DifficultyAssessment` estructurado; el grafo/runtime llama `select_for_role(...)` — ahora **usa** el assessment (ya no lo descarta).

| Role | Primary (scores that matter) | Fallback | Prefer **fallback** when… | Prefer **keep primary** when… |
|------|------------------------------|----------|---------------------------|-------------------------------|
| **coder** *(merged plan+implement, WAVE-18)* | Cerebras GPT-OSS-120B (code **82**, reason **90**) | Codestral (code **88**) | Primary degraded (429 / quota / empty) / a candidate clearly out-fitnesses by ≥8 | Healthy primary + best candidate wins by < `score_advantage_threshold` (8) |
| **debugger** | GPT-OSS-120B (code **82**, reason **90**) | Agnes (code **78**, reason **76**) | Groq 120b RPD exhausted / 429 / empty | Healthy 120b + hard traceback — raise **reasoning_effort**, do not hop early |
| **context_compressor** *(incl. safety gate, WAVE-18)* | Cerebras GPT-OSS-120B (reason **90**, synth **85**, safety **45**) | Agnes (reason **76**, synth **80**) | Cerebras quota / empty JSON | Healthy Cerebras; compressor is one call that also classifies safety |
| **web_search** | compound-mini (ground **88**) | *none* | **Never model-fallback** — no live search → **abort run**; `pin: true` blocks any swap | Always when research needs live web |
| **grounding** | Command A+ (ground **93**, synth **78**) | Mistral Small (ground **55**, synth **65**) | Cohere trial empty / 429 / ToS | Default cited claims; scarce bucket |
| **synthesizer** | GPT-OSS-120B (synth **85**, reason **90**) | Agnes (synth **80**, large context) | Groq 120b exhausted / 429 / empty | Healthy 120b + long report — raise **reasoning_effort** |

**Runtime selection rules (code → `select_for_role`):**

1. **Candidate set** = role primary + role fallback + every catalog model that is `available`, unexpired (`free_until`), and quota-healthy; ranked by `fitness` (quality 0.75 + efficiency 0.25, `core/model_scoring.py`).
2. **Primary expired** (`free_until` past — e.g. `tencent/hy3:free` after **2026-07-21**) → role fallback then catalog `expired_fallback`; scores capped ≤49.
3. **`primary_status` degraded** (`quota_exhausted` | `rate_limited_429` | `empty_completion` | `unavailable` | `degraded`) → best-ranked **non-primary** candidate. When `quota_remaining=` is provided (all live call sites pass `default_quota_remaining`), an exhausted primary is **derived** as `quota_exhausted` from the real ledger.
4. **Hard-task escalation:** when `assessment.relevant_max(areas) ≥ hard_threshold` (default 70), the picked model's role quality must also clear it — escalate to the best-ranked candidate that does (never a fit leader missing the required strength).
5. **Anti-churn hysteresis:** on a healthy primary, only switch when the best candidate's fitness beats the primary by ≥ `score_advantage_threshold` (default **8**). A marginal edge keeps the primary.
6. **Pinned roles** (`roles.<path>.pin: true` — `deep_research.web_search`) never swap, structurally.
7. Model switches **must** go through `record_model_selection_handoff` → `transfer_control` (user input preserved + audit) and rely on `chain_fallback` as the runtime next hop.

**Also never:**

- Promote `tencent/hy3:free` as free-durable default primary/fallback.  
- Replace `compound-mini` for web_search (pinned).  
- Put Command A+ on coder/debugger/synth primary.  
- Switch away from a healthy primary on a sub-threshold fitness edge (churn).

### 4.4 Cómo se elige y se usa el modelo en un run (end-to-end)

```text
User task
   │
   ▼
DifficultyAssessment  (core/difficulty_scorer.py; cli.chat turns get a +5 reason
   │  / −5 synth / −5 code role bias through the same scorer)
   │  areas: code, reason, ground, synth, safety  (0–100)
   │  + overall, logic_complexity, estimated_context_tokens
   ▼
select_for_role(role, assessment, quota_remaining=default_quota_remaining)  (core/model_selector.py)
   │  candidate set = primary + fallback + catalog models (available, unexpired,
   │  quota-healthy) ranked by fitness
   │  rules: quota-derived degradation, hard_threshold escalation, hysteresis
   │  (score_advantage_threshold), pin-immune roles
   │  → ModelSelection { provider, model, used_fallback, reason, role_path,
   │                     primary_status, chain_fallback }
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
   │  retry budgets (core/call_outcome.py): network-transient ≤2 w/ backoff;
   │  402/429/512 retried with per-class budget; body-confirmed quota wall or
   │  Cohere 422 → skip remaining retries; validated JSON repair-once (1)
   ▼
Worker agent (coder / debugger / …) returns domain schema
```

**Who calls what:**

| Entry | Selection | Reasoning kwargs |
|-------|-----------|------------------|
| `run_structured_agent` / `run_role_raw` | yes | yes (default) |
| `invoke_router(..., assessment=, role_path=)` | no (caller fixed provider/model) | yes if assessment provided |
| Graph nodes | `select_for_role` + handoff | via agents → runtime |
| `resolve_role_selection` (CLI: `cli.chat`, `cli.planner`, `_compact --llm`, `/do`) | yes — resolves `select_for_role` per turn | yes |
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
| `deep_research.web_search` | max `low` | Tool/search system, not long CoT |

(WAVE-18: the former `safety_filter` max-`low` clamp disappeared with the role — the safety gate inside the compressor is a classification field, not a reasoning-effort concern.)

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

**hy3 explicit policy:** include in benchmark tables for continuity; **do not** assign as default primary/fallback for A/B roles while free-durable defaults hold. Its promo window ended **2026-07-21**; it is only usable under an optional `openrouter-boosted` profile after an explicit availability probe, and scores stay capped ≤49. Prefer removing the row once the provider drops it.

---

## 5. System A — Vibe Coding (role assignments)

```text
Coder (plan + implement) → Test Executor (local) → Debugger (≤ 3) ─→ fix_applier (local, WAVE-18)
              ▲                                                └──────── repairs via coder
              └──────────── fix cycle with debugger alert (suggested_fix) ──────
```

| Role | Primary | Fallback | Why this placement |
|------|---------|----------|--------------------|
| **coder** *(merged plan+implement, WAVE-18)* | `cerebras` / `gpt-oss-120b` | `mistral` / `codestral-latest` | WAVE-21 re-tune: `cerebras/gpt-oss-120b` is the fitness top for the coder's `[code, reason]` areas (quality 82/90 + measured efficiency) and has 150 RPD of its own bucket. The former primary `codestral-latest` (code **88**) stays as the role fallback — best free coding specialist when Cerebras is degraded. Agent/planning rules (surgical edits, repo tree, grounded facts, preservation) are part of the coder system prompt, so the old `architect` LLM call is gone. |
| **debugger** | `groq` / `openai/gpt-oss-120b` | `agnes` / `agnes-2.0-flash` | Fix loops (up to 3) need strong reasoning + roomy per-model RPD. GPT-OSS-120B on Groq is fast and independent of Agnes volume. Agnes is the durable free alternate when Groq 120b is exhausted or 429s. WAVE-18: when the debugger edits a fully-visible file, it ships `fixed_files` → local `fix_applier` re-writes and re-runs tests (no coder call back); else it emits `suggested_fix` → coder fix cycle. |

**Not used as Vibe primaries:** Cohere (save for research grounding), OpenRouter `:free` (shared 50 RPD), compound-mini (search budget only), gemini-2.0-flash (quota 0 / 404 on this key — `available: false`).

---

## 6. System B — Deep Research (role assignments)

```text
Context compressor (incl. safety gate, WAVE-18) → Web search (+ primary URL fetch) → Grounding → Synthesizer
```

| Role | Primary | Fallback | Why this placement |
|------|---------|----------|--------------------|
| **context_compressor** *(incl. safety gate, WAVE-18)* | `cerebras` / `gpt-oss-120b` | `agnes` / `agnes-2.0-flash` | WAVE-21 re-tune: Cerebras GPT-OSS-120B tops `[reason, synth, safety]` (90/85/45) — the compressor's structured JSON + safety classification benefits from the strongest reasoning. Agnes free volume is the durable fallback (large context). The old gemini fallback is gone: `gemini-2.0-flash` is `available: false` (quota 0 / 404 on this key, WAVE-20 follow-up). WAVE-18: the safety gate from the removed `safety_filter` role lives here — the prompt classifies the query (`is_safe` + `safety_reasons`) and a host-side hard-regex pre-gate (`SAFETY_HARD_RE`) overrides an unsafe LLM verdict; the graph routes to END on `is_safe=False`. |
| **web_search** | `groq` / `groq/compound-mini` | *(none — hard fail if no live search)* | **Only free stack role with integrated search.** ~250 RPD — **used** for one optional bounded query-expansion LLM call per run (vague topic → concrete DDG facets; on failure the heuristic builder stands in). Also HTTP-fetches user-named domains into a PRIMARY SOURCES block before the live dump. Live-search emptiness still aborts the run (anti-fabrication). |
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
10. **Research → vibe chaining:** prior research is not loose prose only. `/do` injects a **GROUNDED FACTS** block (hex colors, wa.me phones, social URLs, logo assets, address lines, explicit gaps) plus hard rules so vibe cannot invent medical-green palettes, NYC map embeds, fake emails, or doctor bios. Coder prompts require copying those facts and prefer file-based tests over Selenium for static sites.
10b. **Planner URL guard:** `/do` passes the original user task as `origin_prompt`. Before each research step, `ensure_origin_urls_in_research_prompt` re-injects any official domains the planner dropped (PRIMARY fetch only sees the step text). Planner rules forbid inventing USP/competitors/colors and require copying user-named domains into research prompts.
11. **Vibe test executor (pytest-only):** never runs the MultiAgent monorepo `tests/` catch-all. Only `test_*.py` from the current artifact. Marketing sites default to **static HTML/CSS/JS** (planner/coder forbid inventing Next.js/Jest unless the user asks). Static content checks enforce grounded hex/wa.me/logo strings. Next/Jest stacks fail fast with a rewrite suggestion. Failed artifacts are snapshotted to `data/vibe_last_failed/` before git rollback. Pytest is launched via repo `venv` / running `sys.executable` (`python -m pytest`), not a bare PATH binary alone.
12. **Brand landing quality + known failure modes** (`agents/vibe_coding/web_quality.py`):
    - **Fragile no-email tests** — `assert "@" not in html` fails on CSS `@media` / `@keyframes`. Host **web-quality lint** fails the run and tells the debugger to fix the *test* (use `mailto:` / email-regex), not strip CSS.
    - **Invented email UI** — when GROUNDED FACTS list email as gap/none, lint fails on `type="email"`, `mailto:`, or invented `user@domain` strings. Prefer **wa.me** CTAs.
    - **Wrong stack wording** — planner must say *static landing*, not *SPA* (models expand SPA → React/Next). Host still rejects Node/Jest projects for marketing sites.
    - **Mis-diagnosis on fix loops** — debugger prompt forbids claiming “email present” when the only `@` is CSS; preservation warnings about dropped `soup`/BeautifulSoup are acceptable.
    - **Quality bar** — coder requires hero + services + contact + responsive layout, not a 40-line stub; copy grounded hex/logo/wa.me/address exactly.
    - Shared rules live in `WEB_LANDING_QUALITY_RULES` and are injected into coder (merged architect, WAVE-18) and debugger system prompts; research→vibe prior context and `format_grounded_constraints_block` restate rules 11–15.
13. **External skills → vibe:** skills register **disabled by default** (`multiagent skills add`; opt-in with `enable` or `add --enable`). Only **enabled** skills with frontmatter `pipelines: [vibe_coding]` and optional `match` regex inject into coder/debugger when the task matches (`core.skills.build_vibe_skills_block`). Bundled packs: `skills/vibe-landing`, `skills/vibe-content-tests`. Chat-only skills default to `pipelines: [chat]`.


---

## 7. CLI roles

| Role | Primary | Fallback | Why |
|------|---------|----------|-----|
| **chat** | `cerebras` / `gpt-oss-120b` | `agnes` / `agnes-2.0-flash` | WAVE-21: `cli.chat` now resolves through `resolve_role_selection("cli","chat")` per turn (the raw `invoke_router` bypass is gone — the turn's `model_selection` is recorded in the reply envelope). Cerebras GPT-OSS-120B tops `[reason, synth]` for interactive tool-using conversation; Agnes free fair-use volume is the fallback. |
| **planner** (`/do`) | `cerebras` / `gpt-oss-120b` | `agnes` / `agnes-2.0-flash` | Same re-tune: `/do` planning + `_compact --llm` and the pipeline translation resolve via role selection (`cli.planner` / `cli.chat`). Agent-style planning benefits from Cerebras reasoning; Agnes stays the cheap durable fallback every `/do`. |

The `/do` TUI flow (*planner → execute_plan*) is exposed headlessly as `pipeline run [--planner-only] [--provider P] [--model M] [--gpt-researcher] TASK…` (`cli_app/pipeline_cli.py`). It resolves the planner from the same `cli.planner` config, translates non-English tasks with the same chat router, and returns a machine-readable dict — the loop lives only there, so CI/cron/other programs can drive a pipeline with no TUI or session. Chat (agent-loop) hygiene: read-only tools are batched into a single `run_tools` call per turn (approval stays strictly per mutating call via `one_mutating_at_a_time`), and the chat agent's `webfetch` returns readable page text through the cache-aware `agents.deep_research.source_fetch.fetch_url` instead of raw truncated HTML.

**Plan-step execution (WAVE-15):** `execute_plan` runs independent (`uses_prior=False`) plan steps in a `ThreadPoolExecutor` wave (results collected in plan order, so a later dependent step sees identical prior context), while dependent (`uses_prior=True`) steps stay strictly sequential. The ADR recommendation was thread-pool-in-`orchestrate.py` over LangGraph-native parallel branches: the outer plan loop is a coarse fan-out with a single dependency signal, LangGraph's Send/branch state-management adds no value at this granularity, and the codebase already uses `ThreadPoolExecutor` for concurrent fetches in `source_fetch.py`. Every concurrent LLM call still goes through WAVE-07's reserve-before-call, thread-safe ledger (`try_reserve` under one lock+connection), so parallel steps near a shared daily limit can never over-commit. System A's merged coder→test→debugger chain (WAVE-18: `fix_applier` shortcut when the debugger ships `fixed_files`) and System B's compressor→…→synthesis chains are untouched and remain sequential.

**Agent tools (WAVE-14):** the chat READ set gained `git_log`/`git_diff` (structured repo history without a `run_terminal` approval), `run_tests` (project suite via the project venv, structured pass/fail), and `search_web` (WAVE-11's keyless DuckDuckGo chain surfaced to free-form chat). All are READ-classified; every shell-based one runs through the same WAVE-04 hardened `_guarded_shell` gate as `run_terminal` (`_BLOCKED_CMD` denylist + modern-catalog soft-upgrade), never raw `subprocess`.

**CLI output contract (WAVE-17):** every outer CLI subcommand accepts a global `--json` flag (accepted before the subcommand, e.g. `multiagent --json pipeline run …`). In `--json` mode stdout carries exactly one *envelope*; in default mode the same information renders as a human block. Envelope fields: `status` (`OK`/`WARNING`/`ERROR`), `message`, `timestamp` (UTC ISO 8601, `Z` suffix), optional `errorCode` (IBM-style `MAE-<nnnn>` catalog with Explanation/Action, see `cli_app/output.py`), optional `detail` (results container), optional `context` (step/tool/provider/model). Stream policy: final results → stdout; progress/diagnostics/preflight → stderr (`eprint`), in both modes. Exit codes: `0` OK, `1` ERROR, `2` usage error, `130` SIGINT/SIGTERM (headless `pipeline run` emits a final `MAE-9000` envelope then exits 130). All `CommandResult`/`chat_turn`/`ToolResult` objects also carry `status`/`error_code`/`timestamp` fields (additive — the TUI still reads `.text`/`.data`).

**Cross-AI context wiring (WAVE-17):** the planner AI now receives a `=== CHAT HISTORY ===` block (last ~4 turns, 400 chars each, via `_chat_context_for_planner`) merged with the project context in `/do`, and `pipeline run` accepts `chat_context=` for headless callers. The chat AI: (1) gets a PIPELINES briefing in its system prompt (what System A/B do, the `run_pipeline` tool, `RECENT PIPELINE RUNS` from `runs.db` injected each seed — so it can reference recorded pipeline work instead of inventing it); (2) gains a `run_pipeline` chat tool (WRITE-classified → approval required; `{task, use_gpt_researcher?, provider?, model?}`) that delegates to `pipeline_cli.run_pipeline`, forwarding the session's recent conversation to the planner and progress to stderr. Context-economy fixes: the per-turn graphify query is now mtime-gated (reuses `session.cached_graph_snippet` when `graph.json` is unchanged — same policy as the planner), the recent-message window grows 4→8 when usage is <35% of budget, and `cli.llm_compact` (default off) switches auto-compaction from local message-drop to LLM summarization.

---

## 8. Fallback cascade (provider DAG)

When a role has no usable role-level fallback, or the fallback fails, `core/router.py` walks `fallback_cascade`. The DAG below is the live `config/model_router.yaml` graph (WAVE-16 redraw — matches `fallback_cascade:` exactly, including the WAVE-08 `opencode_zen` node and `ollama`):

```text
cohere       → mistral / mistral-small-latest
mistral      → agnes  / agnes-2.0-flash
openrouter   → agnes  / agnes-2.0-flash
opencode_zen → agnes  / agnes-2.0-flash
ollama       → mistral / mistral-small-latest
agnes        → groq   / openai/gpt-oss-120b
groq         → gemini / gemini-2.0-flash
gemini       → cerebras / gemma-4-31b
cerebras     → groq   / openai/gpt-oss-120b
```

| Edge | Rationale |
|------|-----------|
| cohere → mistral | Leave free-durable path if trial exhausted |
| openrouter → agnes | **Do not** cascade into another `:free` model (same 50 RPD bucket) |
| opencode_zen → agnes | WAVE-08 node: catalog/fallback tier only, also must not sink into `:free`-style shared buckets |
| ollama → mistral | Local model unavailable → closest free cloud fallback |
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
| OpenCode Zen | 100 shared | Not publicly documented (WAVE-08) | Conservative placeholder |

### 9.1 Quota ledger (WAVE-07): reserve → confirm/refund

Every LLM call goes through a **reservation ledger** (`core/quotas.py`,
table `quota_reservations`) that decides *when* a call is counted:

1. **Reserve** — before any bytes go out on the wire, `try_reserve()` atomically
   checks the day's bucket and inserts a `RESERVED` row (same connection +
   lock, so concurrent callers can never over-commit past the limit). A
   pending reservation already eats into today's quota.
2. **Confirm** — after the call, if the provider was reached (success, any
   HTTP error, or an empty HTTP-200 completion) the row becomes `CONFIRMED`.
3. **Refund** — only when the provider was never reached: the exception carried
   no HTTP status at all (connection died before a response). The row stays
   in the ledger marked `REFUNDED` for auditability and the slot returns to
   the bucket.

Day attribution: a row is dated by its **reservation day**, so a call
reserved at 23:59 and resolved at 00:01 counts against the day it was
reserved, never the resolution day. Transitions are one-way from `RESERVED`
(double-confirm / refund-after-confirm are guarded no-ops).

The legacy `quota_usage.call_count` table remains for backward compatibility
(`record_call()`), but the router only uses the ledger; `get_usage` /
`status_summary` sum both sources. — Tests: `tests/test_quota_ledger.py`.

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

> **Optional: Lightpanda JS rendering (off by default, WAVE-12).**
> MultiAgent has no JS rendering on any live path. You may opt in a renderer for
> SPA/login-wall social fetches (`fetch_outbound_presence_pages`) by installing
> the [Lightpanda](https://github.com/lightpanda-io/browser) binary and enabling
> it via `core/render` (`render="lightpanda"` on `fetch_url`). It degrades
> silently: if the binary is absent (`LIGHTPANDA_BIN` or `PATH`) the pipeline
> behaves byte-identically to a no-render run — one log line, no exception, no
> hang, no extra dependency (no Playwright/Puppeteer). A rendered-but-empty page
> is `SourceResultStatus.EMPTY`, distinct from a fetch that failed.

| Profile | When | Sketch |
|---------|------|--------|
| **free-durable** | Default (this doc) | As above |
| **openrouter-boosted** | Lifetime ≥ $10 OR credits → 1 000 free RPD | Can put coder/debugger on strong `:free` models |
| **free-max-quality** | Prefer quality over latency | Synthesizer/coder → Cerebras gpt-oss / gemma-4 (watch 5 RPM) |
| **local-first** | Offline / privacy | Ollama for coder/synth; keep compound-mini + keys for search/safety |

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
| `AGNES_API_KEY` | chat, planner, coder (fallback), compressor (+ several fallbacks) |
| `MISTRAL_API_KEY` | coder primary; grounding fallback |
| `GROQ_API_KEY` | debugger, web_search, synthesizer |
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

Re-validate limits and any **remaining promo expiries** in each provider console before production-ish unattended runs; update this file, YAML soft-caps, and reasoning capability entries together when free tiers change. (`tencent/hy3:free`'s promo already ended 2026-07-21.)
