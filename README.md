# Free-Multi-Agent

Two independent multi-agent pipelines sharing a common infrastructure layer, powered by three LLM providers on their free/trial tiers: **Groq**, **OpenRouter**, and **Cohere**.

`config/model_router.yaml` is the single source of truth for provider/model/fallback assignments. It is loaded at runtime by `core/agent_config.py`, and every agent (`architect`, `coder`, `debugger`, `safety_filter`, `context_compressor`, `web_search`, `grounding`, `synthesizer`) reads its provider/model/fallback from it via `get_agent_config(...)` instead of hardcoding them in Python. **Editing the YAML now changes real behavior on the next run.**

## Systems

### System A — Vibe Coding
An automated coding pipeline: **Architect → Coder → Test Executor → Debugger** with unit tests as quality gates and real Git rollback if 3 fix cycles are exhausted.

| Role       | Provider   | Model                          | Notes                                   |
|------------|------------|--------------------------------|------------------------------------------|
| Architect  | Cohere     | `command-a-plus-05-2026`       | Command A+, Apache 2.0, 128K context     |
| Coder      | OpenRouter | `cohere/north-mini-code:free`  | Stable free tier                         |
| Debugger   | OpenRouter | `tencent/hy3:free`             | **Free until 2026-07-21** → fallback: `openai/gpt-oss-120b` on Groq |

> Provider/model values above reflect the current `config/model_router.yaml`. Since the YAML is now the live source of truth, treat this table as a snapshot — check the YAML directly for the values actually in effect.

### System B — Deep Research
A research pipeline: **Safety Filter → Context Compression → Web Search → Grounding/Citations → Final Synthesis** with SQLite checkpointing for mid-pipeline resumption.

| Role                | Provider   | Model                           | Notes                                       |
|---------------------|------------|----------------------------------|---------------------------------------------|
| Safety Filter       | Groq       | `openai/gpt-oss-safeguard-20b`  |                                               |
| Context Compressor  | OpenRouter | `tencent/hy3:free`               | Fallback: `openai/gpt-oss-120b` on Groq      |
| Web Search          | Groq       | `groq/compound-mini`            | Tavily-integrated, no extra config           |
| Grounding/Citations | Cohere     | `command-a-plus-05-2026`         | Uses `documents=` param — **NOT** connectors |
| Synthesizer         | Cohere     | `command-r-plus-08-2024`         | Command R+ — chosen specifically for reliable structured citations, distinct from Grounding's model to avoid concentrating 3+ pipeline stages on the same model/quota |

## Tech Stack

- **Python 3.11+**
- **PydanticAI** — typed agent definitions with `result_type` validation
- **LangGraph** — state-graph orchestration (checkpoints, rollback, retries)
- **langgraph-checkpoint-sqlite** — persistent checkpoint storage for System B
- **GitPython** — real Git operations (commit/rollback) for System A
- **Cohere SDK v2** (`cohere.ClientV2`) — no v1 `connectors`
- **OpenAI SDK** — for Groq and OpenRouter (OpenAI-compatible APIs)
- **`core/agent_config.py`** — central loader that reads every agent's provider/model/fallback from `config/model_router.yaml` at runtime. The YAML is the single source of truth: editing it changes real behaviour on the next run, nothing is hardcoded per-agent in Python anymore.

## Quota Limits (safe margins applied)

| Provider   | Daily Limit                                  | Scope              |
|------------|----------------------------------------------|---------------------|
| Groq       | ~800 calls/day per model                     | Independent/model   |
| OpenRouter | ~45 calls/day                                | Shared across `:free` models |
| Cohere     | ~25-30 calls/day (from 1,000/month)          | Shared across all endpoints  |

> ⚠️ **Cohere trial tier is contractually non-commercial use only.**

The numeric limits above are enforced in `core/quotas.py` and must match the values documented in `config/model_router.yaml` — the YAML carries inline comments (`MUST match ... in core/quotas.py`) as a guard against the two drifting apart.

## Reliability Safeguards (System B — Deep Research)

The Deep Research pipeline talks to free/trial-tier models that occasionally misbehave in ways that are easy to miss if you only look at whether the pipeline "completed." Three safeguards were added specifically to catch that:

1. **Query size guard** (`web_search.py`, `context_compressor.py`) — the search query sent to `groq/compound-mini` is capped at 6 terms / 150 characters regardless of what upstream produces, to prevent HTTP 413 (payload too large) when a long research prompt accidentally leaks into what should be a short search query.
2. **No-live-search hard abort** (`web_search.py`, `graphs/deep_research_graph.py`) — if the search step's own output admits it didn't perform a real search (e.g. "no live web-search was performed," a known failure mode of some free-tier models when they can't reach their search tool), the pipeline stops immediately with an explicit error instead of letting that unverified content flow into grounding/synthesis looking like a verified report.
3. **Source verification against raw search results** — every URL in the final report's reference list is checked against the URLs that actually appeared in that run's raw search results. Any citation that doesn't match is flagged inline as `⚠️ fuente no verificada en esta ejecución` rather than presented as a confirmed source.

Additionally, `core/router.py` treats an HTTP-200-but-empty completion (`EmptyCompletionError`) as a cascadable failure rather than a silent success, and skips redundant retries on Cohere's semantic 422 (`NO_VALID_RESPONSE_GENERATED`) to avoid burning its scarce daily quota on a request that will fail identically three times in a row.

None of this guarantees the final report is 100% accurate — it guarantees the pipeline won't *silently* present unverified or fabricated content as if it were grounded. Manually spot-checking specific figures/dates in any final report (especially case-study sections) is still recommended before using it for anything formal.

## Reliability Safeguards (System A — Vibe Coding)

`coder_node` (`graphs/vibe_coding_graph.py`) writes files produced by an untrusted, free-tier LLM directly to disk, so it carries its own guardrails:

1. **Path-traversal protection** — every file path returned by the Coder agent is resolved against the repo root and rejected (`UnsafeFilePathError`) if it's absolute or escapes the root via `..`, so a malformed or adversarial path can't write outside the project.
2. **All-or-nothing writes** — every path is validated *before* any file is touched. A single bad path aborts the whole batch instead of leaving a half-written set of files on disk.
3. **Atomic per-file writes** — each file is written to a temp path in the same directory and then atomically renamed into place, so a crash mid-write can't leave a truncated file behind.

## opencode Integration (MCP)

The Vibe Coding pipeline is also exposed as an MCP tool (`run_vibe_coding`) so it can be driven from [opencode](https://opencode.ai) instead of (or alongside) the CLI.

| File | Purpose |
|------|---------|
| `mcp_server.py` | MCP server (stdio transport) wrapping `graphs/vibe_coding_graph.py`. Loads its own `.env` (same folder) on startup via `python-dotenv`, so API keys don't need to be exported in the parent shell. |
| `opencode.json.example` | Template for opencode's MCP config. Copy to `opencode.json` and fill in the absolute path to `mcp_server.py` for your machine. |
| `opencode.json` | **Git-ignored.** Your local, machine-specific config — contains the absolute path to `mcp_server.py`, which differs per clone/machine. |

### Setup
1. `cp opencode.json.example opencode.json`
2. Edit `opencode.json`, replacing the placeholder path with the absolute path to your local `mcp_server.py`.
3. Make sure `.env` (same folder as `mcp_server.py`) has your API keys.
4. Register `opencode.json` as a **global** opencode config (`~/.config/opencode/opencode.json`) if you want `run_vibe_coding` available from any directory, not just this repo's folder — opencode only auto-loads project-scoped configs when launched from inside (or below) the folder that contains them.

### Important: this is a repo-agnostic tool
`run_vibe_coding` operates on whatever Git repository is the current working directory when opencode invokes it (`coder_node` resolves the repo root via `get_git_repo(".")`), **not necessarily this `MultiAgent` repo**. This is intentional — it lets you use the same registered MCP server as a general-purpose vibe-coding tool across any of your projects. Be mindful of this: invoking `run_vibe_coding` from inside a different Git repo will write files and create commits/rollbacks *there*, using this pipeline's models and logic.

## Installation

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd MultiAgent
```

### 2. Create a virtual environment

```bash
python3.11 -m venv venv
source venv/bin/activate  # Linux/macOS
# or: venv\Scripts\activate  # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your actual API keys:
#   GROQ_API_KEY=...
#   OPENROUTER_API_KEY=...
#   COHERE_API_KEY=...
```

> Also add `opencode.json` to `.gitignore` if you set up the opencode MCP integration below — it contains an absolute, machine-specific path and shouldn't be committed. Use `opencode.json.example` as the tracked template instead.

### 5. Initialize Git (required for System A rollback)

```bash
git init
git add -A
git commit -m "Initial commit"
```

## Usage

```bash
# System A — Vibe Coding
python cli.py run vibe-coding "Build a REST API for a todo app"

# System B — Deep Research
python cli.py run deep-research "Latest advances in quantum computing"
```

## Running Tests

All tests use mocked HTTP responses — **zero real API quota consumed**.

```bash
pytest tests/ -v
```

## Project Structure

```
MultiAgent/
├── .env.example                  # API key template
├── .gitignore
├── requirements.txt
├── README.md
├── opencode.json.example         # Template for opencode MCP config (copy to opencode.json, not tracked in git)
├── mcp_server.py                 # MCP server exposing run_vibe_coding to opencode/any MCP client
├── config/
│   └── model_router.yaml         # Model assignments, fallbacks, quotas, dates — live config, read at runtime
├── core/
│   ├── __init__.py
│   ├── clients.py                # Groq/OpenRouter/Cohere client initialization
│   ├── quotas.py                 # SQLite-backed quota counters (daily reset)
│   ├── router.py                 # call_agent() with fallback cascade + empty-completion guard
│   └── agent_config.py           # Loads provider/model/fallback per agent role from model_router.yaml
├── schemas/
│   ├── __init__.py
│   ├── vibe_coding.py            # TechnicalSpec, CodeArtifact, DebugReport
│   └── deep_research.py          # SafetyClassification, CondensedTrends, GroundedReport
├── agents/
│   ├── __init__.py
│   ├── vibe_coding/
│   │   ├── __init__.py
│   │   ├── architect.py          # Cohere command-a-plus-05-2026 (via model_router.yaml)
│   │   ├── coder.py              # OpenRouter north-mini-code:free (via model_router.yaml)
│   │   └── debugger.py           # OpenRouter hy3:free → fallback gpt-oss-120b (via model_router.yaml)
│   └── deep_research/
│       ├── __init__.py
│       ├── safety_filter.py      # Groq gpt-oss-safeguard-20b (via model_router.yaml)
│       ├── context_compressor.py # OpenRouter hy3:free → fallback gpt-oss-120b (via model_router.yaml)
│       ├── web_search.py         # Groq compound-mini (Tavily) + query-size guard + no-live-search abort (via model_router.yaml)
│       ├── grounding.py          # Cohere documents= grounding, builds GroundedReport in Python (not model-authored JSON)
│       └── synthesizer.py        # Cohere command-r-plus-08-2024 final synthesis (via model_router.yaml)
├── graphs/
│   ├── __init__.py
│   ├── vibe_coding_graph.py      # LangGraph: Architect→Coder→Test Executor→Debugger + safe atomic writes + Git rollback
│   └── deep_research_graph.py    # LangGraph: 5-stage pipeline + SQLite checkpoints + search-abort routing
├── cli.py                        # Click CLI entry point
└── tests/
    ├── __init__.py
    ├── test_router_fallback.py   # Fallback cascade tests (incl. quota isolation, empty-completion cascade)
    ├── test_schemas.py           # Schema validation (positive + negative)
    └── test_graphs_mocked.py     # Git rollback + checkpoint resumption tests
```

## Important Dates

| Event                              | Date           |
|------------------------------------|----------------|
| `tencent/hy3:free` expires         | **2026-07-21** |
| Groq model deprecations effective  | 2026-06-17     |

The CLI will warn you when the current date is ≤3 days from the Hy3 expiration.

## Deprecated Models (DO NOT USE)

These were deprecated by Groq on 2026-06-17:
- `llama-3.1-8b-instant`
- `llama-3.3-70b-versatile`
- `qwen/qwen3-32b`
- `llama-4-scout-17b-16e-instruct`
