# Free-Multi-Agent

Local multi-agent tooling on **free/trial LLM APIs**. One install, one `.env`, no config files in other repos.

| Piece | What it does |
|-------|----------------|
| **Interactive TUI** (`multiagent`) | Chat with host tools, graphify context, model/keys config |
| **System A — Vibe Coding** | Architect → Coder → tests → Debugger + Git checkpoint/rollback |
| **System B — Deep Research** | Safety → compress (+ research typology) → web search → ground → synthesize |
| **Planner** (`/do`) | Splits a task into ordered vibe and/or research steps |
| **Terminal toolbox** | Curated modern CLI catalog: doctor, suggest, runtime backends (`eza`/`rg`/`fd`/…) |

**Orchestration rationale** (benchmarks, rate limits, why each model per role): **[`systems.md`](systems.md)**.

Config lives in `config/model_router.yaml` (live) and `config/defaults_model_router.yaml` (factory reset). Agents load provider/model/fallback at runtime via `core/agent_config.py` — edit YAML (or `/config`) and the next run uses it.

The terminal toolbox catalog is `config/cli_toolbox.yaml`. PATH probes and suggestions: `core/toolbox.py`.

---

## Quick start

```bash
git clone <repo-url> && cd MultiAgent
python3 -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                               # fill keys (or use TUI /keys)

./bin/install-launcher.sh                          # optional: multiagent on PATH
multiagent                                         # TUI from any directory
# or: python cli.py chat
```

### Free-durable keys (defaults)

| Env | Needed for |
|-----|------------|
| `AGNES_API_KEY` | chat, planner, architect, compressor (+ many fallbacks) |
| `MISTRAL_API_KEY` | coder (`codestral-latest`) |
| `GROQ_API_KEY` | debugger, safety, web search, synthesizer |
| `COHERE_API_KEY` | research grounding only |
| `GEMINI_API_KEY` / `CEREBRAS_API_KEY` | cascade fallbacks |
| Ollama | no key (optional local override) |

```bash
multiagent keys set agnes    # https://platform.agnes-ai.com
multiagent keys set mistral
multiagent keys set groq
multiagent keys set cohere
multiagent config show
multiagent providers
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
multiagent quota
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

### System B — Deep Research

**Safety → Context compress (+ research typology) → Web search → Grounding → Synthesis** (+ SQLite checkpoints).

Each topic is classified by **purpose** (basic/applied), **depth** (exploratory/descriptive/explanatory), **data approach** (quant/qual/mixed), and **design** (experimental/non-experimental). Search facets and report structure adapt to that profile (see **[systems.md](systems.md)**).

Safeguards:

- Query size limits; abort if search admits “no live search”  
- Primary URL fetch when the user names a domain + multi-facet open-web search  
- Citation URLs verified against that run’s search/primary corpus  
- Router treats empty HTTP 200 as failure and cascades fallbacks  
- Entity-focused multi-facet search to reduce subject bleed  

### Planner (`/do`)

User-chosen model (`cli.planner` or `/planner set`). Non-English tasks can be translated to English for A/B; chat still answers in the user’s language.

Full role rationale → **[systems.md](systems.md)**.

---

## Providers, quotas & free-durable defaults

| Provider | Env | Free-tier notes (summary) |
|----------|-----|---------------------------|
| **Agnes AI** | `AGNES_API_KEY` | Default text model `agnes-2.0-flash` (~20 RPM fair-use, $0/M). Image/video models exist but are not chat roles. |
| **Groq** | `GROQ_API_KEY` | ~1 000 RPD/model; `compound-mini` ~250 RPD + live search |
| **Mistral** | `MISTRAL_API_KEY` | Experiment free; Codestral for coding |
| **Cohere** | `COHERE_API_KEY` | Trial ~1 000/mo, non-commercial — **grounding only** |
| **Gemini** | `GEMINI_API_KEY` | AI Studio Flash free; used as fallback |
| **Cerebras** | `CEREBRAS_API_KEY` | ~5 RPM, ~1M TPD; quality cascade leaf |
| **OpenRouter** | `OPENROUTER_API_KEY` | `:free` ~50 RPD shared — **off hot path** |
| **Ollama** | *(none)* | Local; models = only `ollama list` |

### Default roles (free-durable)

| Role | Primary | Fallback |
|------|---------|----------|
| vibe architect | `agnes` / `agnes-2.0-flash` | Gemini 2.0 Flash |
| vibe coder | `mistral` / `codestral-latest` | Agnes |
| vibe debugger | `groq` / `gpt-oss-120b` | Agnes |
| research safety | `groq` / `gpt-oss-safeguard-20b` | Gemini |
| research compressor | `agnes` / `agnes-2.0-flash` | Gemini |
| research web_search | `groq` / `compound-mini` | — (hard fail if no live search) |
| research grounding | `cohere` / `command-a-plus` | Mistral small |
| research synthesizer | `groq` / `gpt-oss-120b` | Agnes |
| cli chat / planner | `agnes` / `agnes-2.0-flash` | Groq gpt-oss-120b |

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
- Soft daily limits: `core/quotas.py`  
- Full tables & rationale: **[systems.md](systems.md)**

---

## Production hardening

Built to run on free-tier APIs without burning quota or corrupting the user’s repo:

- **Quota gating + cascading fallback** (`core/router.py`) — refuses calls past a provider’s soft daily limit and walks the fallback chain (skip-visited, no infinite loops).
- **Empty-completion guard** — HTTP 200 with empty content cascades instead of breaking Pydantic validation.
- **System A safety rails** — path-traversal blocked, atomic writes, pre-run WIP stash + git rollback.
- **System B safety rails** — unsafe queries terminate; fake “no live search” hard-aborts before grounding.
- **Rotating logs** — under `data/logs/` (gitignored); never logs keys or full message bodies.
- **Tool sandbox** — `run_terminal` blocks classic dangerous commands and soft-upgrades `ls`→`eza`, etc. when available.
- **KeyboardInterrupt-safe** — TUI and pipelines exit cleanly on Ctrl-C.

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
├── cli.py                 # Click entry (chat default, config, keys, skills, tools, …)
├── systems.md             # Free-tier limits, benchmarks, role rationale
├── pyproject.toml
├── .env.example
├── bin/multiagent         # PATH launcher (preserves caller cwd)
├── config/
│   ├── model_router.yaml              # live provider/model roles
│   ├── defaults_model_router.yaml     # factory reset snapshot
│   └── cli_toolbox.yaml               # modern terminal tool catalog
├── cli_app/               # TUI + slash commands + agent tools
│   ├── tui.py
│   ├── commands.py
│   ├── agent_chat.py
│   ├── tools.py
│   ├── graph_rag.py
│   └── session.py
├── core/
│   ├── toolbox.py
│   ├── router.py, quotas.py, clients.py, keys.py, skills.py, …
│   ├── agent_config.py, config_editor.py
│   └── runs.py
├── agents/                # vibe_coding + deep_research + planner
├── graphs/                # LangGraph pipelines
├── schemas/
├── skills/README.md
├── data/                  # local SQLite — gitignored
├── graphify-out/          # knowledge graph — gitignored
└── tests/
```

User-global state (not in this repo):

- `~/.config/multiagent/skills.yaml` — external skill registry  
- MultiAgent `.env` — API keys only in the install tree  

---

## Tests

```bash
pytest tests/ -v
pytest tests/test_toolbox.py -v
pytest tests/test_router_fallback.py tests/test_graphs_mocked.py -v
```

Network-facing tests mock HTTP; no real API usage in CI-style runs. Toolbox tests probe real `PATH` for optional binaries.

---

## Notes

- Prefer **Agnes / Groq** for volume; send heavy multi-step work through **`/do`**.  
- Rebuild the package graph after large code changes: `graphify update .` (or ask chat). Artifacts → `graphify-out/` (gitignored).  
- Global skills: `~/.config/multiagent/skills.yaml` — see `skills/README.md`.  
- Keep the toolbox catalog honest: prefer `config/cli_toolbox.yaml` over hard-coded tool lists in prompts.  
- When free-tier limits or catalogs change, update **`systems.md`**, YAML notes, and `core/quotas.py` together.  
