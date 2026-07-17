# Systems orchestration — free-durable profile

**Document status:** mid-2026 research snapshot (last updated 2026-07-17)  
**Live config:** `config/model_router.yaml`  
**Factory defaults:** `config/defaults_model_router.yaml`  
**Quota soft-caps:** `core/quotas.py` (must stay ≤ real provider limits)

This document explains **why** each free-tier model sits in each System A / System B / CLI role: benchmarks (relative quality), API rate limits, and orchestration constraints (shared buckets, cascade design, calls per run).

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

## 4. Relative benchmarks (free-relevant models)

Public leaderboards move weekly. Relative **role-relevant** picture used for routing (not absolute scores):

| Capability | Strong free options | Weaker / avoid as primary |
|------------|---------------------|---------------------------|
| **Coding (generate/edit)** | Codestral; Agnes 2.0 Flash; Gemma 4 31B; GPT-OSS-120B | Generic small chat models; burning OR free pool |
| **Agent / tool / multi-step** | Agnes 2.0 Flash (Claw-Eval strong); GPT-OSS-120B tool-use often solid | Models without tool training |
| **Reasoning / debug** | GPT-OSS-120B (Groq); Gemma 4 31B (Cerebras); Gemini Flash | Ultra-light Flash-Lite alone for hard bugs |
| **Structured JSON** | Gemini Flash; Agnes; Mistral Small; GPT-OSS | Verbose ungrounded chat models |
| **RAG / anti-hallucination** | Cohere Command A+ / R+ (native documents path) | Pure generative synth without search |
| **Safety classify** | GPT-OSS Safeguard 20B | Random general chat for policy |
| **Live web search** | **Only** `groq/compound-mini` in this free stack | Models that “pretend” to search |
| **Long report synthesis** | GPT-OSS-120B; Agnes (large context); Gemini Flash | Models with tiny max output |

**Agnes 2.0 Flash:** free multimodal gateway text model; strong agent/coding/tool story at $0; ~20 RPM free — ideal volume primary.  
**GPT-OSS-120B:** open frontier-class reasoning on Groq at ~1k RPD/model — ideal debug + synthesizer primary.  
**Gemma 4 31B:** competitive open intelligence/coding indices vs GPT-OSS in independent tables; great Cerebras fallback when quality needed under low RPM.  
**Codestral:** purpose-built code model on Mistral free Experiment.  
**Command A+:** best trial-tier grounding partner for System B.

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
6. `source_url_is_verified` + `scrub_ungrounded_claims` drop invented sources and strip ungrounded contacts.


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
| Relative model quality | Artificial Analysis comparisons, Claw-Eval mentions, independent coding scorecards 2026 |

Re-validate limits in each provider console before production-ish unattended runs; update this file and YAML soft-caps together when free tiers change.
