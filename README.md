# Free-Multi-Agent

Local multi-agent tooling on **free/trial LLM APIs**. One install, one `.env` — no MultiAgent config needed in other projects.

| Piece | What it does |
|-------|----------------|
| **TUI** (`multiagent`) | Chat with host tools (files, terminal, graphify, toolbox) |
| **`/do <task>`** | Planner splits work into **vibe-coding** and/or **deep-research** |
| **System A — Vibe** | Architect → Coder → tests → Debugger (Git checkpoint / rollback) |
| **System B — Research** | Safety → compress → web search → ground → synthesize |
| **Toolbox** | Suggest / doctor modern CLIs (`eza`, `rg`, `fd`, …) when installed |
| **Skills** | Optional `SKILL.md` packs (registered globally; **off by default**) |

**Why each model is assigned, quotas, selection rules, and reasoning policy:**  
see **[`systems.md`](systems.md)** (design source of truth — not required for daily use).

---

## Quick start

```bash
git clone <repo-url> && cd MultiAgent
python3 -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -e ".[dev]"                            # or: pip install -r requirements.txt
cp .env.example .env                               # then fill keys (or use multiagent keys set)

./bin/install-launcher.sh                          # optional: multiagent on PATH
multiagent                                         # opens the TUI
```

### API keys

Keys live only in this install’s `.env` (never print full values).

| Env | Used for (free-durable defaults) |
|-----|----------------------------------|
| `AGNES_API_KEY` | Chat, planner, architect, compressor (+ many fallbacks) |
| `MISTRAL_API_KEY` | Coder (`codestral-latest`); grounding fallback |
| `GROQ_API_KEY` | Debugger, safety, web search, synthesizer |
| `COHERE_API_KEY` | Research **grounding only** (scarce trial bucket) |
| `GEMINI_API_KEY` | Role / cascade fallbacks |
| `CEREBRAS_API_KEY` | Cascade leaf (~5 RPM) — optional |
| `OPENROUTER_API_KEY` | Optional catalog only (not on the default hot path) |
| Ollama | No key — optional local override |

```bash
multiagent keys set agnes      # https://platform.agnes-ai.com
multiagent keys set mistral
multiagent keys set groq
multiagent keys set cohere     # if you run research
multiagent providers
multiagent config show
multiagent quota               # usage + estimated remaining full A/B runs
```

**Working directory:** Git commits/rollbacks for vibe and chat file tools use the directory where you launched `multiagent`, not the install tree.

Optional better host UX:

```bash
multiagent tools doctor --profile core   # eza, bat, rg, fd, …
```

---

## Using the TUI

```bash
multiagent                 # default command = chat TUI
```

| Action | Binding |
|--------|---------|
| Send | Enter |
| Newline | Shift+Enter |
| Compact session | Ctrl+K |
| Config panel | Ctrl+O (or Ctrl+P); Esc closes |
| Help | F1 |
| Quit | Ctrl+Q |

Free-text chat can list/read/edit files, run terminal commands, and query the local knowledge graph. **Mutating** tools ask for approval (`accept` / `reject` / `always`, or `/approve always` · `/approve off`).

### Slash commands

```text
/do <task>                 Run the planner (vibe and/or research)
/planner | /planner set    Show / set planner model
/research-resume <id> …    Resume a research checkpoint

/config …                  Models, fallbacks, cycles, reset
/keys | /providers
/skills …                  External skill packs (see below)
/tools …                   Terminal toolbox
/approve [always|off]

/compact | /clear | /status
/quota | /history [N]
/graphify [question]
/help | /exit
```

There are no standalone `/vibe` or `/research` commands — use **`/do`**.

### Outer CLI (no TUI)

```bash
multiagent config show|set|reset
multiagent keys set|status
multiagent providers
multiagent skills list|add|enable|disable|…
multiagent tools doctor|suggest|search|…
multiagent quota
multiagent history --limit 20
```

---

## Pipelines (`/do`)

### Vibe coding

Implements code in the **current Git repo**: Architect → Coder → scoped tests → Debugger (retry cycles from config). On success it can commit; on exhaustion it rolls back (after stashing any pre-existing dirty work).

For marketing / brand landings after research, the host prefers **static HTML/CSS/JS** + pytest content checks (not Next/Jest unless you ask). Research is chained as **grounded facts** so contact/brand details are not invented. Details: [`docs/vibe_web_failures.md`](docs/vibe_web_failures.md).

### Deep research

Safety gate → context compress (with research typology) → live web search → grounding → synthesis. Checkpoints live under `data/` (gitignored). User-named official domains are fetched as primary sources when present in the task.

### Planner

Chooses step order (often research, then vibe with prior context). Non-English tasks may be translated for the pipelines; chat still answers in your language.

---

## Default roles

Live config: `config/model_router.yaml` · factory reset: `multiagent config reset` (from `config/defaults_model_router.yaml`).

| Role | Primary | Fallback |
|------|---------|----------|
| vibe architect | `agnes` / `agnes-2.0-flash` | `gemini` / `gemini-2.0-flash` |
| vibe coder | `mistral` / `codestral-latest` | `agnes` / `agnes-2.0-flash` |
| vibe debugger | `groq` / `openai/gpt-oss-120b` | `agnes` / `agnes-2.0-flash` |
| research safety | `groq` / `openai/gpt-oss-safeguard-20b` | `gemini` / `gemini-2.0-flash` |
| research compressor | `agnes` / `agnes-2.0-flash` | `gemini` / `gemini-2.0-flash` |
| research web_search | `groq` / `groq/compound-mini` | — (hard fail if no live search) |
| research grounding | `cohere` / `command-a-plus-05-2026` | `mistral` / `mistral-small-latest` |
| research synthesizer | `groq` / `openai/gpt-oss-120b` | `agnes` / `agnes-2.0-flash` |
| chat / planner | `agnes` / `agnes-2.0-flash` | `groq` / `openai/gpt-oss-120b` |

```bash
multiagent config set vibe_coding.coder mistral codestral-latest
multiagent config reset
# optional local model:
# ollama pull llama3.2 && multiagent config set cli.chat ollama llama3.2
```

Soft daily call caps and remaining-run estimates: `multiagent quota`.  
Full cascade, benchmarks, and “when fallback wins” rules: **[`systems.md`](systems.md)**.

---

## Skills

Optional instruction packs (`SKILL.md`). Registry: `~/.config/multiagent/skills.yaml`.

**New skills are registered disabled.** Nothing injects until you enable them.

```bash
multiagent skills add ./skills/vibe-landing      # still off
multiagent skills enable vibe-landing
multiagent skills list
```

Bundled examples (landing quality + safe content tests): `skills/vibe-landing`, `skills/vibe-content-tests`.  
Format and pipelines (`chat` / `vibe_coding`): [`skills/README.md`](skills/README.md).

---

## Terminal toolbox

```bash
multiagent tools doctor -p core
multiagent tools suggest "search code"
multiagent tools alt ls
```

When tools are on `PATH`, chat host helpers prefer them (`eza`, `rg`, `fd`, `bat`, …). Catalog: `config/cli_toolbox.yaml`.

---

## Tests

```bash
pytest tests/ -v
```

Network tests mock HTTP; no real API calls in normal CI-style runs.

---

## Technical reference

For operators and contributors. Live design narrative and full tables: **[`systems.md`](systems.md)**. Machine-readable scores/thresholds: `config/model_benchmarks.yaml`. Live roles: `config/model_router.yaml`.

### Project structure

```text
MultiAgent/
├── cli.py                 # Click entry: multiagent → TUI by default
├── systems.md             # Free-durable design: limits, benchmarks, selection
├── config/
│   ├── model_router.yaml          # live provider/model/fallback per role
│   ├── defaults_model_router.yaml # factory reset snapshot
│   ├── model_benchmarks.yaml      # 0–100 scores, selection + reasoning policy
│   └── cli_toolbox.yaml           # terminal tool catalog
├── docs/                  # handoffs, vibe web quality notes
├── cli_app/               # TUI, slash commands, host tools, /do orchestrator
├── core/
│   ├── router.py          # provider cascade, empty-completion, quota tick
│   ├── quotas.py          # soft daily caps (calls, not tokens)
│   ├── difficulty_scorer.py  # task → DifficultyAssessment (0–100 areas)
│   ├── model_selector.py  # primary vs fallback from scores + health
│   ├── reasoning_params.py   # reasoning_effort on capable models (same call)
│   ├── agent_runtime.py   # wires selection + reasoning into agent calls
│   ├── handoff.py         # Swarm-style transfer + audit trail
│   ├── skills.py · toolbox.py · search_guards.py · …
├── agents/                # planner, vibe_coding/*, deep_research/*
├── graphs/                # LangGraph: vibe_coding_graph, deep_research_graph
├── schemas/               # Pydantic domain + handoff models
├── skills/                # bundled SKILL.md (opt-in)
├── data/                  # quotas/runs/checkpoints/logs — gitignored
├── graphify-out/          # package knowledge graph — gitignored
└── tests/
```

**Control flow (one agent call):**

```text
task / role
  → DifficultyAssessment          (code, reason, ground, synth, safety)
  → select_for_role               (primary vs fallback; optional handoff audit)
  → resolve_reasoning_kwargs      (effort on GPT-OSS family only; same RPD call)
  → router.call_agent             (1 soft-quota tick on success; cascade on fail)
  → structured domain schema
```

| Pipeline | Typical LLM steps | Notes |
|----------|-------------------|--------|
| Vibe (A) | 2–5 | Architect + Coder + Debugger (0–3 fix cycles) |
| Research (B) | 5 | Safety → compress → web_search → grounding → synth |
| `/do` | +1 planner | Then N× A and/or B |

### Reasoning used for model placement

Design goals (free-durable profile):

1. **Survive a workday** on free/trial APIs without early hard-stop.
2. **One scarce bucket = one critical role** (e.g. Cohere only on grounding).
3. **Spread Groq load across model IDs** (independent ~1 000 RPD counters).
4. **Reserve live web search** (`groq/compound-mini` ~250 RPD) for research only.
5. Prefer **durable free** models over expiring promos; OpenRouter `:free` stays catalog-only.
6. **Specialize**: Codestral → code; Safeguard → safety; Command A+ → RAG; 120b → debug/synth.

**Runtime primary vs fallback** (`model_selector` + `model_benchmarks.yaml`):

| Prefer fallback when… | Keep primary when… |
|-----------------------|--------------------|
| Primary expired (`free_until`), or degraded (429 / soft quota / empty completion) | Healthy primary on an easy/adequate task |
| Mis-specialized: fallback score − primary ≥ **8** **and** primary ≤ **49** on a relevant area | Fallback only edges higher by a few points on a secondary area |

**Reasoning effort** (not an extra daily call): difficulty bands map to low / medium / high. Injected only for models that support it (Groq GPT-OSS family). Debugger / synthesizer / planner floor at **medium**. Raising effort is preferred over cascading models on hard fix/report work.

**Provider cascade** (after role fallback fails):  
`cohere → mistral → agnes → groq → gemini → cerebras → groq`  
(OpenRouter failures hop to Agnes — not deeper `:free` models.)

---

### Provider rate limits (API keys)

Public free/trial **reference** values (~mid-2026). Providers change tiers without notice. MultiAgent soft-caps are **conservative** and enforced locally in `core/quotas.py` (must stay ≤ real limits).

| Provider / env key | Free-tier reference | Soft-cap (YAML) | Stack use |
|--------------------|---------------------|-----------------|-----------|
| **Groq** `GROQ_API_KEY` | ~**30 RPM**; most models ~**1 000 RPD each**; `compound-mini` ~**250 RPD** + live search | **800** RPD/model | Debugger, safety, web_search, synthesizer |
| **Agnes** `AGNES_API_KEY` | ~**20 RPM** fair-use; large context; $0/M promo text | **2 000** calls/day (local) | Chat, planner, architect, compressor, fallbacks |
| **Mistral** `MISTRAL_API_KEY` | Experiment free (rate-limited; ~1 RPS class community) | **200**/day | Coder (Codestral); grounding fallback |
| **Cohere** `COHERE_API_KEY` | Trial ~**1 000/month** (~25–30/day), ~20 RPM; **non-commercial** trial ToS | **28**/day | **Grounding only** |
| **Gemini** `GEMINI_API_KEY` | Flash ~**10–15 RPM**; RPD varies (~250–1 500 class) | **400**/day shared soft | Role / cascade fallbacks |
| **Cerebras** `CEREBRAS_API_KEY` | ~**5 RPM**, ~1M TPD | **150**/day | Cascade **leaf** (quality burst, not volume) |
| **OpenRouter** `OPENROUTER_API_KEY` | `:free` **20 RPM**, **50 RPD shared** (&lt;$10 credits); 1 000 free RPD after credits | **45**/day shared | Catalog only (not hot path) |
| **Ollama** *(none)* | Hardware only | Local tracker only | Optional privacy/offline override |

Quota unit in this stack is almost always **calls/day**, not tokens. Cascading after 429 **costs another call** on the next model; raising `reasoning_effort` on the same model does **not**.

```bash
multiagent quota    # live usage + estimated remaining full System A/B runs
```

---

### Model benchmarks (0–100) and intended use

Scores are **relative within this free-durable stack** (snapshot mid-2026 in `config/model_benchmarks.yaml`) — not absolute frontier rank vs paid models.

**Rubric areas:** **code** · **reason** · **ground** · **synth** · **safety**  
**Bands:** 0–30 unreliable · 31–49 weak · 50–69 adequate · 70–84 strong · 85–100 best-in-stack (free/trial).

| Model | code | reason | ground | synth | safety | Use as… |
|-------|-----:|-------:|-------:|------:|-------:|---------|
| `mistral` / `codestral-latest` | **88** | 62 | 40 | 55 | 35 | **Coder primary** — best free coding specialist |
| `groq` / `openai/gpt-oss-120b` | **82** | **90** | 48 | **85** | 45 | **Debugger / synthesizer primary** — hard reason + long reports |
| `agnes` / `agnes-2.0-flash` | **78** | **76** | 42 | **80** | 40 | **Chat, planner, architect, compressor** — high-volume free agents |
| `gemini` / `gemini-2.0-flash` | 70 | **78** | 55 | 75 | 50 | Structured JSON / plan **fallback** |
| `cohere` / `command-a-plus-05-2026` | 58 | 72 | **93** | 78 | 48 | **Grounding only** — RAG / citations (scarce trial) |
| `mistral` / `mistral-small-latest` | 58 | 62 | 55 | 65 | 40 | Grounding **fallback** |
| `groq` / `groq/compound-mini` | 50 | 58 | **88** | 52 | 30 | **Web search only** — only free live-search path |
| `groq` / `openai/gpt-oss-safeguard-20b` | 35 | 55 | 30 | 40 | **92** | **Safety filter only** — not a general coder |
| `openrouter` / `tencent/hy3:free` ⚠ | 55 | 60 | 38 | 58 | 35 | Catalog / temporal (**expires 2026-07-21**); auto-skip when expired |

| Capability | Prefer | Avoid as primary |
|------------|--------|------------------|
| Coding | Codestral; Agnes; GPT-OSS-120b | Safeguard; compound-mini alone |
| Plan / reason | GPT-OSS-120b; Gemini; Agnes | Expired promos |
| Live search | **compound-mini only** | Models that invent “search” |
| Citations / RAG | Command A+ | General chat without corpus |
| Long report write-up | GPT-OSS-120b; Agnes | Mini search system as sole writer |
| Safety gate | Safeguard-20b | Random general chat |

When free-tier catalogs or limits change, update **`systems.md`**, `config/model_benchmarks.yaml`, and soft caps in the router YAML together.

---

## Notes

- Prefer **Agnes / Groq** for volume; send multi-step work through **`/do`**.
- After large code changes, refresh the package graph: `graphify update .` (or ask chat) → `graphify-out/`.
- Full handoff protocol diagrams: [`docs/handoff_protocol.md`](docs/handoff_protocol.md).
