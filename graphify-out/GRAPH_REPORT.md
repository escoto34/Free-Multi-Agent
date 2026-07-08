# Graph Report - MultiAgent  (2026-07-08)

## Corpus Check
- 37 files · ~16,477 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 345 nodes · 628 edges · 23 communities (21 shown, 2 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 61 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `0b1e5cd7`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 22|Community 22]]

## God Nodes (most connected - your core abstractions)
1. `QuotaTracker` - 26 edges
2. `TechnicalSpec` - 22 edges
3. `CodeArtifact` - 22 edges
4. `GroundedReport` - 19 edges
5. `DebugReport` - 19 edges
6. `VibeCodingState` - 17 edges
7. `ModelRouter` - 16 edges
8. `call_agent()` - 14 edges
9. `DeepResearchState` - 14 edges
10. `run_grounding()` - 13 edges

## Surprising Connections (you probably didn't know these)
- `CondensedTrends` --uses--> `CondensedTrends`  [INFERRED]
  agents/deep_research/context_compressor.py → schemas/deep_research.py
- `Any` --uses--> `GroundedReport`  [INFERRED]
  agents/deep_research/grounding.py → schemas/deep_research.py
- `GroundedReport` --uses--> `GroundedReport`  [INFERRED]
  agents/deep_research/grounding.py → schemas/deep_research.py
- `Any` --uses--> `VibeCodingState`  [INFERRED]
  mcp_server.py → graphs/vibe_coding_graph.py
- `VibeCodingState` --uses--> `VibeCodingState`  [INFERRED]
  mcp_server.py → graphs/vibe_coding_graph.py

## Import Cycles
- 1-file cycle: `core/router.py -> core/router.py`
- 1-file cycle: `core/clients.py -> core/clients.py`

## Communities (23 total, 2 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.07
Nodes (53): BaseModel, Run the Safety Filter agent to classify if the research query is safe., run_safety_filter(), NoLiveSearchError, Raised when the search step's own output admits it did not search live., context_compressor_node(), DeepResearchState, get_deep_research_graph() (+45 more)

### Community 1 - "Community 1"
Cohesion: 0.07
Nodes (54): TechnicalSpec, CodeArtifact, TechnicalSpec, CodeArtifact, DebugReport, architect_node(), coder_node(), debugger_node() (+46 more)

### Community 2 - "Community 2"
Cohesion: 0.06
Nodes (38): Connection, Path, QuotaTracker, Persistent SQLite-backed quota counters with automatic daily reset.  Limits are, Open a connection to the quota database., ISO-formatted current date for partitioning., Determine the tracking key for a (provider, model) pair.          * **Groq** — e, Return the daily limit for *provider*.          Reads from ``config/model_router (+30 more)

### Community 3 - "Community 3"
Cohesion: 0.06
Nodes (28): Any, GroundedReport, _extract_sources_from_citations(), _extract_sources_from_search_text(), Grounding agent using PydanticAI definition. Performs native grounding and citat, Best-effort extraction of source URLs from Cohere's native citations., Fallback: pull raw URLs directly out of the search-results text., Run the Grounding step using the provider/model configured in     config/model_r (+20 more)

### Community 4 - "Community 4"
Cohesion: 0.10
Nodes (20): _isolate_clients(), Path, Root conftest — sets up fake API keys so that imports of core.clients don't rais, Clear cached LLM clients between tests to avoid cross-contamination., Provide a temporary SQLite path for QuotaTracker in tests., tmp_quota_db(), clear_client_cache(), get_client() (+12 more)

### Community 5 - "Community 5"
Cohesion: 0.09
Nodes (22): 1. Clone the repository, 2. Create a virtual environment, 3. Install dependencies, 4. Configure environment variables, 5. Initialize Git (required for System A rollback), Deprecated Models (DO NOT USE), Free-Multi-Agent, Important Dates (+14 more)

### Community 6 - "Community 6"
Cohesion: 0.20
Nodes (13): check_hy3_expiration(), main(), Command Line Interface for running Multi-Agent pipelines.  Commands:   - run vib, Read expiration dates from model_router.yaml and print warnings if near., Multi-Agent Ecosystem Command Line Interface., Run a multi-agent orchestration graph., Execute System A: Architect -> Coder -> Test Executor -> Debugger with Git rollb, Validate that required API keys are configured and not placeholders. (+5 more)

### Community 7 - "Community 7"
Cohesion: 0.17
Nodes (11): Definition of Done, Fase 0 — Andamiaje del repositorio, Fase 1 — Capa de clientes y cuotas (`core/`), Fase 2 — Esquemas Pydantic (`schemas/`), Fase 3 — Agentes PydanticAI, Fase 4 — Grafo LangGraph, Sistema A (Vibe Coding), Fase 5 — Grafo LangGraph, Sistema B (Deep Research), Fase 6 — CLI y observabilidad (+3 more)

### Community 8 - "Community 8"
Cohesion: 0.24
Nodes (10): GroundedReport, clean_and_parse_synthesizer_report(), extract_urls(), Synthesizer agent using PydanticAI definition. Synthesizes grounded reports into, Clean markdown code blocks and parse content as GroundedReport., Helper to extract clean http/https URLs from text., Run the Synthesizer agent to compile the final publication-grade document., run_synthesizer() (+2 more)

### Community 9 - "Community 9"
Cohesion: 0.12
Nodes (20): CondensedTrends, get_agent_config(), _load(), Any, Path, Central loader for per-agent provider/model assignments.  ``config/model_router., Load (and cache) the full YAML config.      A custom ``config_path`` bypasses th, Force the next ``get_agent_config`` call to re-read the YAML from disk.      Use (+12 more)

### Community 22 - "Community 22"
Cohesion: 0.24
Nodes (9): _initial_state(), _invoke_graph(), Any, MCP server for the "vibe_coding" pipeline (architect -> coder -> test_executor -, Build a fresh initial state matching VibeCodingState's TypedDict shape., Run the compiled StateGraph end-to-end and normalize the final state     into a, Run the full vibe-coding pipeline (architect -> coder -> test_executor     -> de, run_vibe_coding() (+1 more)

## Knowledge Gaps
- **35 isolated node(s):** `Path`, `Any`, `ClientV2`, `LLMClient`, `Path` (+30 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `QuotaTracker` connect `Community 2` to `Community 3`?**
  _High betweenness centrality (0.130) - this node is a cross-community bridge._
- **Why does `GroundedReport` connect `Community 0` to `Community 8`, `Community 3`?**
  _High betweenness centrality (0.093) - this node is a cross-community bridge._
- **Why does `VibeCodingState` connect `Community 1` to `Community 0`, `Community 6`, `Community 22`?**
  _High betweenness centrality (0.049) - this node is a cross-community bridge._
- **Are the 9 inferred relationships involving `QuotaTracker` (e.g. with `EmptyCompletionError` and `LLMResponse`) actually correct?**
  _`QuotaTracker` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 11 inferred relationships involving `TechnicalSpec` (e.g. with `TechnicalSpec` and `CodeArtifact`) actually correct?**
  _`TechnicalSpec` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `CodeArtifact` (e.g. with `CodeArtifact` and `TechnicalSpec`) actually correct?**
  _`CodeArtifact` has 12 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `GroundedReport` (e.g. with `Any` and `GroundedReport`) actually correct?**
  _`GroundedReport` has 6 INFERRED edges - model-reasoned connections that need verification._