# Free-Multi-Agent

Local multi-agent tooling on **free/trial LLM APIs**. One install, one `.env`, no config files in other repos.

| Piece | What it does |
|-------|----------------|
| **Interactive TUI** (`multiagent`) | Chat with host tools, graphify context, model/keys config |
| **System A — Vibe Coding** | Architect → Coder → tests → Debugger + Git checkpoint/rollback |
| **System B — Deep Research** | Safety → compress (+ research typology) → web search → ground → synthesize |
| **Planner** (`/do`) | Splits a task into ordered vibe and/or research steps |
| **Terminal toolbox** | Curated modern CLI catalog: doctor, suggest, runtime backends (`eza`/`rg`/`fd`/…) |
| **Smart model routing** | Difficulty scores → primary/fallback + reasoning effort on capable models |
| **Swarm-style handoffs** | Explicit control transfer with full audit trail (`handoff_history`) |

**Orchestration rationale** (benchmarks, rate limits, selection rules, reasoning policy, why each model per role): **[`systems.md`](systems.md)**.

| Config / docs | Purpose |
|---------------|---------|
| `config/model_router.yaml` | Live provider/model/fallback per role |
| `config/defaults_model_router.yaml` | Factory reset snapshot |
| `config/model_benchmarks.yaml` | Scores 0–100, selection thresholds, reasoning effort bands |
| `config/cli_toolbox.yaml` | Terminal toolbox catalog |
| `docs/handoff_protocol.md` | Agent handoff protocol + diagrams |
| `systems.md` | Full free-durable design source of truth |

Agents load provider/model/fallback at runtime via `core/agent_config.py` — edit YAML (or `/config`) and the next run uses it. Soft daily call caps live in `core/quotas.py` (must stay ≤ real provider limits).

---

## Quick start

```bash
git clone <repo-url> && cd MultiAgent
python3 -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
# or: pip install -e ".[dev]"
cp .env.example .env                               # fill keys (or use TUI /keys)

./bin/install-launcher.sh                          # optional: multiagent on PATH
multiagent                                         # TUI from any directory
# or: python cli.py chat
```

### Free-durable keys (defaults)

| Env | Needed for |
|-----|------------|
| `AGNES_API_KEY` | chat, planner, architect, compressor (+ many fallbacks) |
| `MISTRAL_API_KEY` | coder (`codestral-latest`); grounding fallback |
| `GROQ_API_KEY` | debugger, safety, web search, synthesizer |
| `COHERE_API_KEY` | research grounding only |
| `GEMINI_API_KEY` | cascade / role fallbacks |
| `CEREBRAS_API_KEY` | quality cascade leaf (~5 RPM) |
| `OPENROUTER_API_KEY` | optional catalog only (off hot path) |
| Ollama | no key (optional local override) |

```bash
multiagent keys set agnes    # https://platform.agnes-ai.com
multiagent keys set mistral
multiagent keys set groq
multiagent keys set cohere
multiagent config show
multiagent providers
multiagent quota             # usage + estimated remaining runs
```

**Keys stay only in MultiAgent’s `.env`.** Consumer projects do not need MultiAgent files.

System A commits/rollbacks use the **Git repo of your current working directory**. Chat file tools also target that **launch cwd**, not the MultiAgent install tree.

Optional (better chat UX): install CLIs from the **core** toolbox profile (`eza`, `bat`, `rg`, `fd`, …):

```bash
multiagent tools doctor --profile core
```

---

## Interactive TUI

```bash
multiagent                 # chat (default)
multiagent --help
multiagent providers
multiagent keys set groq
multiagent config show
multiagent quota
multiagent tools doctor
```

### Keys & chrome

| Action | Binding / UI |
|--------|----------------|
| Send | Enter |
| Newline in prompt | Shift+Enter |
| Compact session | Ctrl+K |
| Config side panel | Ctrl+O (or Ctrl+P); Esc closes |
| Help panel | F1 |
| Copy selection | drag text → Ctrl+C (no selection → quit) |
| Quit | Ctrl+Q |

Config and help are mutually exclusive side panels; they **resize the chat** (push content). Drag the left edge to change width (max ½ screen).

Session meter (ctx / graphify / skills) lives under **config → models**, not in the chat footer.

### Chat (tool-using agent)

Free-text chat is **not** pure autocomplete. The host:

1. Seeds context (graphify + directory/file hits when relevant; toolbox brief when relevant).
2. Lets the model call host tools (`list_dir`, `read_file`, `write_file`, `edit_file`, `run_terminal` / `bash`, `grep`, `glob`, `create_venv`, `pip_install`, `graphify_query`, `graphify_update`, `toolbox_query`, …).
3. Asks approval for **mutating** tools **one command at a time**.

You do **not** need to name tools. Example: *“mira `docs/` y edita el tercer `.txt`”* → `list_dir` → `read_file` → `edit_file` (edit needs approval unless `/approve always`).

Approval bar (compact vertical list):

```text
**ls -la agents**     ← command header
`accept`
`reject`
`always`              ← always-approve until /approve off
```

Also: `a` / `r` / `!`, or `/approve always` · `/approve off`.

Important paths:

- **`agents/`** — Python package (planner, deep_research, vibe_coding)
- **`.agents/`** — editor rules only (not the package)
- Writes go to **launch cwd**; MultiAgent package graph lives under the install’s `graphify-out/`

### Slash commands (inside TUI)

```text
/do <task>                      Planner chooses vibe-coding and/or deep-research
/planner | /planner set <p> <m> Show / set planner model
/research-resume <id> <topic>   Resume System B checkpoint

/config                         Open config panel
/config set <sys.role> <prov> <model>
/config fallback <sys.role> <provider> <model>
/config clear-fallback <sys.role>
/config cycles <N> | limit <tokens> | reset | text

/keys | /keys set <provider> <key>
/providers
/skills …                       Global SKILL.md packs (~/.config/multiagent/)
/tools …                        Terminal toolbox (doctor / suggest / search / alt)
/approve [always|off]

/compact [--llm] | /clear | /status
/quota | /history [N]
/graphify [question]
/help | /exit
```

Direct `/vibe` and `/research` were removed; use **`/do`** so the planner picks pipelines.

### Outer CLI

```bash
multiagent config show|set|reset
multiagent keys set|status
multiagent providers
multiagent skills list|add|enable|…
multiagent tools doctor [--profile core] [--missing-only]
multiagent tools suggest "search code"
multiagent tools search yaml
multiagent tools show eza
multiagent tools list [--check] [category]
multiagent tools alt ls
multiagent tools profiles
multiagent quota                 # live usage + estimated remaining A/B runs
multiagent history --limit 20
```

Pipelines run **inside the TUI** via `/do` (not as outer `vibe`/`research` subcommands).

---

## Terminal toolbox

Catalog: `config/cli_toolbox.yaml` · Logic: `core/toolbox.py` · Tests: `tests/test_toolbox.py`

### Surfaces

| Surface | Examples |
|---------|----------|
| Slash (TUI) | `/tools`, `/tools doctor git`, `/tools suggest safe delete`, `/tools alt ls` |
| Outer CLI | `multiagent tools doctor -p core`, `multiagent tools search yaml` |
| Chat host tool | `toolbox_query` with `mode`: `suggest` · `doctor` · `search` · `show` · `alt` · `runtime` |

When a tool is on `PATH`, host tools prefer it automatically.

### Runtime (automatic)

| Host tool | Prefers if installed | Fallback |
|-----------|----------------------|----------|
| `list_dir` | `eza` / `tre` | Python listing |
| `grep` | `rg` (ripgrep) | Python walk |
| `glob` | `fd` | `pathlib.glob` |
| `read_file` | `bat -p` (no ANSI) | plain read |
| `run_terminal` | soft-upgrade `ls`→`eza`, `cat`→`bat`, `grep`→`rg`, … | original command |

Outputs are tagged, e.g. `[via eza]`. Disable upgrades with `"raw": true` / `"no_upgrade": true` on `run_terminal`. Destructive classics such as `rm` are **not** auto-rewritten.

### Doctor profiles

`core` · `git` · `docker` · `k8s` · `disk` · `net` · `monitor` · `data` · `security` · `ai` · `modern-rust` · `all`

```bash
multiagent tools doctor -p core
multiagent tools doctor -p git
multiagent tools suggest "docker image layers"
multiagent tools alt grep
```

---

## Pipelines

### System A — Vibe Coding

**Architect → Coder → Test Executor → Debugger** (YAML: `vibe_coding.*`, `max_fix_cycles`).

Safeguards (`graphs/vibe_coding_graph.py`):

- Path traversal blocked; all-or-nothing + atomic writes  
- Dirty tree: pre-run WIP stash, restore after commit/rollback  
- Merge into existing files when possible (preserve helpers)  
- Difficulty plan up front; coder/debugger may handoff model switches into `handoff_history`  
- Failed run snapshot under `data/vibe_last_failed/` (gitignored)

### System B — Deep Research

**Safety → Context compress (+ research typology) → Web search → Grounding → Synthesis** (+ SQLite checkpoints under `data/checkpoints.db`).

Each topic is classified by **purpose** (basic/applied), **depth** (exploratory/descriptive/explanatory), **data approach** (quant/qual/mixed), and **design** (experimental/non-experimental). Search facets and report structure adapt to that profile (see **[systems.md](systems.md)**).

Safeguards:

- Query size limits; abort if search admits “no live search”  
- Primary URL fetch when the user names a domain + multi-facet open-web search  
- Citation URLs verified against that run’s search/primary corpus  
- Router treats empty HTTP 200 as failure and cascades fallbacks  
- Entity-focused multi-facet search to reduce subject bleed  
- Formal handoffs between nodes (query + intermediates preserved)

### Planner (`/do`)

User-chosen model (`cli.planner` or `/planner set`). Non-English tasks can be translated to English for A/B; chat still answers in the user’s language. Planner path also gets difficulty-aware **reasoning effort** when the selected model supports it (e.g. Groq GPT-OSS).

Full role rationale → **[systems.md](systems.md)**.

---

## Model selection, difficulty & reasoning

Free-tier limits in this stack are almost always **per call (RPD)**, not per token. Raising reasoning effort on a supported model does **not** burn an extra daily call; cascading to another model does.

### Runtime flow

```text
task text
  → DifficultyAssessment (core/difficulty_scorer.py)
  → select_for_role (core/model_selector.py)  # primary vs fallback
  → [if switch] record_model_selection_handoff → transfer_control
  → resolve_reasoning_kwargs (core/reasoning_params.py)  # same call
  → router.call_agent  # 1 quota tick on success; sanitize kwargs on cascade
```

| Module | Responsibility |
|--------|----------------|
| `core/difficulty_scorer.py` | Structured 0–100 scores: `code`, `reason`, `ground`, `synth`, `safety` |
| `core/model_selector.py` | Primary vs fallback from YAML scores + health signals |
| `core/reasoning_params.py` | `reasoning_effort` / `include_reasoning` for capable models |
| `core/agent_runtime.py` | Wires selection + reasoning into every agent call |
| `core/handoff.py` | Official node-to-node transfer API |
| `config/model_benchmarks.yaml` | Editable scores, thresholds, effort bands |

### When does fallback win?

Prefer fallback only if:

1. Primary **expired** (`free_until`, e.g. `tencent/hy3:free` after **2026-07-21**), or  
2. Primary **degraded** (`quota_exhausted`, `rate_limited_429`, `empty_completion`, …), or  
3. Primary **mis-specialized**: `score_fallback(area) − score_primary(area) ≥ 8` **and** primary score ≤ 49 on a relevant area  

Healthy primary + easy/adequate task → **stay on primary** even if the fallback edges higher by a few points. Details → **[systems.md §4.3–4.5](systems.md)**.

### Reasoning effort (same call)

| Difficulty (role-relevant max) | Abstract effort |
|--------------------------------|-----------------|
| &lt; 50 | low |
| 50–74 | medium |
| ≥ 75 | high |

Role clamps (examples): debugger/synthesizer/planner min **medium**; safety/web_search max **low**.

**Models with API reasoning** (Groq GPT-OSS family, Qwen 3.6 on Groq, …): kwargs injected automatically; default `include_reasoning=false` so JSON agents get clean `content`.  
**Others** (Agnes, Codestral, Gemini, Cohere, compound-mini): no effort kwargs — quality is model choice only. Cascade hops **strip** unsupported reasoning params so Agnes never sees `reasoning_effort`.

---

## Agent handoffs

Nodes pass control via `core.handoff.transfer_control` (Swarm-style): original user input (`idea` / `query`), intermediate artifacts (`TechnicalSpec`, `GroundedReport`, …), and an audit trail in `handoff_history` are preserved on every transfer. Model switches use the same path via `record_model_selection_handoff`.

Protocol + Mermaid diagrams → **[docs/handoff_protocol.md](docs/handoff_protocol.md)**.

---

## Providers, quotas & free-durable defaults

| Provider | Env | Free-tier notes (summary) |
|----------|-----|---------------------------|
| **Agnes AI** | `AGNES_API_KEY` | Default text model `agnes-2.0-flash` (~20 RPM fair-use, $0/M). Image/video models exist but are not chat roles. |
| **Groq** | `GROQ_API_KEY` | ~1 000 RPD/model; `groq/compound-mini` ~250 RPD + live search; GPT-OSS supports `reasoning_effort` |
| **Mistral** | `MISTRAL_API_KEY` | Experiment free; Codestral for coding |
| **Cohere** | `COHERE_API_KEY` | Trial ~1 000/mo, non-commercial — **grounding only** |
| **Gemini** | `GEMINI_API_KEY` | AI Studio Flash free; used as fallback |
| **Cerebras** | `CEREBRAS_API_KEY` | ~5 RPM, ~1M TPD; quality cascade leaf |
| **OpenRouter** | `OPENROUTER_API_KEY` | `:free` ~50 RPD shared — **off hot path** (hy3 promo expires **2026-07-21**) |
| **Ollama** | *(none)* | Local; models = only `ollama list` |

Quota soft-caps count **calls/day**, not tokens (`core/quotas.py` + `data/quotas.db`). Estimate remaining A/B runs:

```bash
multiagent quota
```

### Default roles (free-durable)

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
| cli chat / planner | `agnes` / `agnes-2.0-flash` | `groq` / `openai/gpt-oss-120b` |

**Cascade (simplified):**  
`cohere → mistral → agnes → groq → gemini → cerebras → groq`  
OpenRouter failures hop to **Agnes**, not deeper `:free` models.

```bash
multiagent config show
multiagent config set vibe_coding.coder mistral codestral-latest
multiagent config reset                 # restore factory free-durable defaults

# Optional local Ollama
ollama pull llama3.2
multiagent config set cli.chat ollama llama3.2
```

- Live: `config/model_router.yaml`  
- Factory: `config/defaults_model_router.yaml`  
- Benchmarks + selection + reasoning: `config/model_benchmarks.yaml`  
- Soft daily limits: `core/quotas.py`  
- Remaining-run estimates: `core/quota_estimate.py`  
- Full tables & rationale: **[systems.md](systems.md)**

---

## Production hardening

Built to run on free-tier APIs without burning quota or corrupting the user’s repo:

- **Quota gating + cascading fallback** (`core/router.py`) — refuses calls past a provider’s soft daily limit and walks the fallback chain (skip-visited, no infinite loops).
- **Empty-completion guard** — HTTP 200 with empty content cascades instead of breaking Pydantic validation.
- **Difficulty-aware model + reasoning** — hard tasks raise effort on GPT-OSS without an extra call; degraded primaries hand off via audited fallback.
- **Swarm-style handoffs** — refuse transfers that would drop the original user input.
- **System A safety rails** — path-traversal blocked, atomic writes, pre-run WIP stash + git rollback.
- **System B safety rails** — unsafe queries terminate; fake “no live search” hard-aborts before grounding.
- **Rotating logs** — under `data/logs/` (gitignored); never logs keys or full message bodies.
- **Tool sandbox** — `run_terminal` blocks classic dangerous commands and soft-upgrades `ls`→`eza`, etc. when available.
- **KeyboardInterrupt-safe** — TUI and pipelines exit cleanly on Ctrl-C.
- **hy3 temporal** — catalog-only; auto-skip after `free_until` (2026-07-21) with score cap ≤49.

---

## Tech stack

- Python 3.11+ · Pydantic v2 · LangGraph + SQLite checkpoints  
- GitPython · Cohere SDK v2 · OpenAI SDK (Groq / OpenRouter / Mistral / Gemini / Cerebras / Agnes / Ollama)  
- Click + Textual + Rich (TUI) · PyYAML · python-dotenv  
- Optional host CLIs from the toolbox (eza, ripgrep, fd, bat, …) — not Python deps  
- Packaged via `pyproject.toml` (`pip install -e .` exposes the `multiagent` command)

---

## Project layout

```text
MultiAgent/
├── cli.py                 # Click entry (chat default, config, keys, skills, tools, quota, …)
├── systems.md             # Free-tier limits, benchmarks, selection & reasoning policy
├── pyproject.toml
├── .env.example
├── bin/multiagent         # PATH launcher (preserves caller cwd)
├── config/
│   ├── model_router.yaml              # live provider/model roles
│   ├── defaults_model_router.yaml     # factory reset snapshot
│   ├── model_benchmarks.yaml          # scores, thresholds, reasoning effort
│   └── cli_toolbox.yaml               # modern terminal tool catalog
├── docs/
│   └── handoff_protocol.md            # Swarm-style transfer protocol
├── cli_app/               # TUI + slash commands + agent tools
│   ├── tui.py
│   ├── commands.py
│   ├── agent_chat.py
│   ├── tools.py
│   ├── graph_rag.py
│   └── session.py
├── core/
│   ├── router.py          # cascade, empty-completion, reasoning via extra_body
│   ├── quotas.py          # per-call soft daily caps (SQLite)
│   ├── quota_estimate.py  # remaining A/B run estimates for CLI
│   ├── difficulty_scorer.py
│   ├── model_selector.py
│   ├── reasoning_params.py
│   ├── handoff.py
│   ├── agent_runtime.py   # selection + reasoning injection for all agents
│   ├── agent_config.py, config_editor.py, clients.py, keys.py
│   ├── toolbox.py, skills.py, search_guards.py, runs.py
│   └── …
├── agents/                # vibe_coding + deep_research + planner
├── graphs/                # LangGraph pipelines (handoffs + difficulty)
├── schemas/               # domain + handoff Pydantic models
├── skills/README.md
├── data/                  # local SQLite / logs / failed vibe snaps — gitignored
├── graphify-out/          # knowledge graph — gitignored
└── tests/                 # offline mocks; handoff / selector / reasoning / quota
```

User-global state (not in this repo):

- `~/.config/multiagent/skills.yaml` — external skill registry  
- MultiAgent `.env` — API keys only in the install tree  

---

## Tests

```bash
pytest tests/ -v
pytest tests/test_toolbox.py -v
pytest tests/test_handoff.py tests/test_model_selector.py tests/test_reasoning_params.py -v
pytest tests/test_quota_estimate.py tests/test_router_fallback.py tests/test_graphs_mocked.py -v
```

Network-facing tests mock HTTP; no real API usage in CI-style runs. Toolbox tests probe real `PATH` for optional binaries.

---

## Notes

- Prefer **Agnes / Groq** for volume; send heavy multi-step work through **`/do`**.  
- On hard debug/synth tasks, the stack raises **reasoning effort** on GPT-OSS first (same call / same RPD).  
- Rebuild the package graph after large code changes: `graphify update .` (or ask chat). Artifacts → `graphify-out/` (gitignored).  
- Global skills: `~/.config/multiagent/skills.yaml` — see `skills/README.md`.  
- Keep the toolbox catalog honest: prefer `config/cli_toolbox.yaml` over hard-coded tool lists in prompts.  
- When free-tier limits or catalogs change, update **`systems.md`**, `config/model_benchmarks.yaml`, YAML notes, and `core/quotas.py` together.  
- Temporal OpenRouter promos (e.g. `tencent/hy3:free` → **2026-07-21**) stay catalog-only on free-durable defaults.  
