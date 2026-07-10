# Free-Multi-Agent

Local multi-agent tooling on free/trial LLM APIs. One install, one `.env`, no config files in other repos.

| Piece | What it does |
|-------|----------------|
| **Interactive TUI** (`multiagent`) | Chat with tools, graphify context, model/keys config |
| **System A — Vibe Coding** | Architect → Coder → tests → Debugger + Git checkpoint/rollback |
| **System B — Deep Research** | Safety → compress → web search → ground → synthesize (+ SQLite resume) |
| **Planner** (`/do`) | Splits a task into ordered vibe and/or research steps |

Config lives in `config/model_router.yaml` (live) and `config/defaults_model_router.yaml` (factory reset). Agents load provider/model/fallback at runtime via `core/agent_config.py` — edit YAML (or `/config`) and the next run uses it.

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

**Keys stay only in MultiAgent’s `.env`.** Consumer projects do not need MultiAgent files.

System A commits/rollbacks use the **Git repo of your current working directory** (where you launched the command). Chat file tools (`write_file`, shell, venv, pip) also target that **launch cwd**, not the MultiAgent install tree.

---

## Interactive TUI

```bash
multiagent                 # chat
multiagent --help
multiagent providers
multiagent keys set groq
multiagent config show
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

Config and help are mutually exclusive side panels; they **resize the chat** (push content), drag the left edge to change width (max ½ screen).

Session meter (ctx / graphify / skills) lives under **config → models**, not in the chat footer.

### Chat (tool-using agent)

Free-text chat is **not** pure autocomplete. The host:

1. Seeds context (graphify query + directory/file hits when relevant).
2. Lets the model call tools (`write_file`, `read_file`, `run_terminal` / `bash`, `grep`, `glob`, `create_venv`, `pip_install`, `graphify_query`, `graphify_update`, …).
3. Asks approval for **mutating** tools **one command at a time**.

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

Markdown is rendered in the history; user prompts appear as fenced code blocks.

### Slash commands (inside TUI)

```text
/do <task>                      Planner chooses vibe and/or research steps
/planner | /planner set <p> <m> Show / set planner model
/research-resume <id> <topic>   Resume System B checkpoint

/config                         Open config panel
/config set <sys.role> <prov> <model>
/config fallback <sys.role> <prov> <model>
/config clear-fallback <sys.role>
/config cycles <N> | limit <tokens> | reset | text

/keys | /keys set <provider> <key>
/providers
/skills …                       Global SKILL.md packs (~/.config/multiagent/)
/approve [always|off]

/compact [--llm] | /clear | /status
/quota | /history [N]
/graphify [question]
/help | /exit
```

Direct `/vibe` and `/research` were removed; use **`/do`** so the planner picks pipelines.

### Outer CLI (no pipelines)

```bash
multiagent config show|set|reset|…
multiagent keys set|status
multiagent providers
multiagent skills list|add|enable|…
multiagent quota
multiagent history --limit 20
```

---

## Pipelines

### System A — Vibe Coding

**Architect → Coder → Test Executor → Debugger** (YAML: `vibe_coding.*`, `max_fix_cycles`).

Safeguards (see `graphs/vibe_coding_graph.py`):

- Path traversal blocked; all-or-nothing + atomic writes  
- Dirty tree: pre-run WIP stash, restore after commit/rollback  
- Merge into existing files when possible (preserve helpers)

### System B — Deep Research

**Safety → Context compress → Web search → Grounding → Synthesis** (+ SQLite checkpoints).

Safeguards:

- Query size limits; abort if search admits “no live search”  
- Citation URLs checked against that run’s search hits  
- Router treats empty HTTP 200 as failure and cascades fallbacks  

### Planner (`/do`)

User-chosen model (`cli.planner` or `/planner set`). Non-English tasks can be translated to English for A/B; chat still answers in the user’s language.

---

## Providers & quotas

| Provider | Env | Notes |
|----------|-----|--------|
| Groq | `GROQ_API_KEY` | Fast; per-model daily caps in YAML/quotas |
| OpenRouter | `OPENROUTER_API_KEY` | Shared free-tier pool for `:free` models |
| Cohere | `COHERE_API_KEY` | Trial often non-commercial |
| Mistral | `MISTRAL_API_KEY` | Studio free / codestral |
| Gemini | `GEMINI_API_KEY` | AI Studio OpenAI-compat endpoint |
| Cerebras | `CEREBRAS_API_KEY` | Fast free developer models |

```bash
multiagent providers
multiagent keys set mistral
multiagent config set vibe_coding.coder mistral codestral-latest
```

Live roles/models: **`config/model_router.yaml`**. Safe daily limits: `core/quotas.py` (must stay aligned with YAML comments).

Hy3 free window (if still used as debugger): check `free_until` in YAML; CLI warns near expiry.

---

## Tech stack

- Python 3.11+ · Pydantic v2 · LangGraph + SQLite checkpoints  
- GitPython · Cohere SDK v2 · OpenAI SDK (Groq/OpenRouter/compat)  
- Click + Textual + Rich (TUI) · PyYAML · python-dotenv  

---

## Project layout

```text
MultiAgent/
├── cli.py                 # Click entry (chat default, config, keys, …)
├── bin/multiagent         # PATH launcher (preserves caller cwd)
├── config/
│   ├── model_router.yaml
│   └── defaults_model_router.yaml
├── cli_app/               # TUI + slash commands + agent tools
│   ├── tui.py
│   ├── commands.py
│   ├── agent_chat.py      # tool loop + approvals
│   ├── tools.py           # write/read/bash/grep/glob/venv/pip/graphify
│   ├── graph_rag.py
│   └── session.py
├── core/                  # router, quotas, clients, keys, skills, runs
├── agents/                # vibe_coding + deep_research agents
├── graphs/                # LangGraph pipelines
├── schemas/
├── skills/README.md       # SKILL.md format for global skills
├── data/                  # local SQLite (quotas, runs, checkpoints)
├── graphify-out/          # knowledge graph (rebuild with graphify)
└── tests/                 # mocked HTTP — no live quota
```

---

## Tests

```bash
pytest tests/ -v
```

All tests mock HTTP; no real API usage.

---

## Notes

- Prefer short free-tier models for chat; heavy work through `/do`.  
- Rebuild the package graph after large code changes: `graphify update .` (or ask chat to update the graph).  
- Global skills: `~/.config/multiagent/skills.yaml` — see `skills/README.md`.  
- Deprecated Groq models (do not use): `llama-3.1-8b-instant`, `llama-3.3-70b-versatile`, legacy qwen/scout ids listed in YAML `deprecated:`.
