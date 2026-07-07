# Free-Multi-Agent

Two independent multi-agent pipelines sharing a common infrastructure layer, powered by three LLM providers on their free/trial tiers: **Groq**, **OpenRouter**, and **Cohere**.

```
At the moment model_router.yaml isnt connected to the system so a change in it should not change results or which model or provider is used.
```
## Systems

### System A — Vibe Coding
An automated coding pipeline: **Architect → Coder → Debugger** with unit tests as quality gates and real Git rollback if 3 fix cycles are exhausted.

| Role       | Provider   | Model                          | Notes                                   |
|------------|------------|--------------------------------|------------------------------------------|
| Architect  | Cohere     | `command-a-plus-05-2026`       | Command A+, Apache 2.0, 128K context     |
| Coder      | OpenRouter | `cohere/north-mini-code:free`  | Stable free tier                         |
| Debugger   | OpenRouter | `tencent/hy3:free`             | **Free until 2026-07-21** → fallback: `openai/gpt-oss-120b` on Groq |

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
│   │   ├── architect.py          # Cohere command-a-plus-05-2026
│   │   ├── coder.py              # OpenRouter north-mini-code:free
│   │   └── debugger.py           # OpenRouter hy3:free → fallback gpt-oss-120b
│   └── deep_research/
│       ├── __init__.py
│       ├── safety_filter.py      # Groq gpt-oss-safeguard-20b
│       ├── context_compressor.py # OpenRouter hy3:free → fallback gpt-oss-120b
│       ├── web_search.py         # Groq compound-mini (Tavily) + query-size guard + no-live-search abort
│       ├── grounding.py          # Cohere documents= grounding, builds GroundedReport in Python (not model-authored JSON)
│       └── synthesizer.py        # Cohere command-r-plus-08-2024 final synthesis
├── graphs/
│   ├── __init__.py
│   ├── vibe_coding_graph.py      # LangGraph: Architect→Coder→Debugger + Git rollback
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
