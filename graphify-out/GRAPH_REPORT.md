# Graph Report - MultiAgent  (2026-07-07)

## Corpus Check
- 35 files · ~13,969 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 310 nodes · 552 edges · 22 communities (20 shown, 2 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 50 edges (avg confidence: 0.51)
- Token cost: 0 input · 0 output

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

## God Nodes (most connected - your core abstractions)
1. `QuotaTracker` - 26 edges
2. `GroundedReport` - 19 edges
3. `TechnicalSpec` - 19 edges
4. `CodeArtifact` - 19 edges
5. `ModelRouter` - 16 edges
6. `DebugReport` - 16 edges
7. `call_agent()` - 14 edges
8. `DeepResearchState` - 14 edges
9. `VibeCodingState` - 13 edges
10. `SafetyClassification` - 13 edges

## Surprising Connections (you probably didn't know these)
- `CondensedTrends` --uses--> `CondensedTrends`  [INFERRED]
  agents/deep_research/context_compressor.py → schemas/deep_research.py
- `Any` --uses--> `GroundedReport`  [INFERRED]
  agents/deep_research/grounding.py → schemas/deep_research.py
- `GroundedReport` --uses--> `GroundedReport`  [INFERRED]
  agents/deep_research/grounding.py → schemas/deep_research.py
- `SafetyClassification` --uses--> `SafetyClassification`  [INFERRED]
  agents/deep_research/safety_filter.py → schemas/deep_research.py
- `GroundedReport` --uses--> `GroundedReport`  [INFERRED]
  agents/deep_research/synthesizer.py → schemas/deep_research.py

## Import Cycles
- 1-file cycle: `core/router.py -> core/router.py`
- 1-file cycle: `core/clients.py -> core/clients.py`

## Communities (22 total, 2 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (57): Any, GroundedReport, BaseModel, CondensedTrends, Context Compressor agent using PydanticAI definition. Extracts search parameters, Run the Context Compressor agent to identify trends and guide web search.     Us, run_context_compressor(), _extract_sources_from_citations() (+49 more)

### Community 1 - "Community 1"
Cohesion: 0.07
Nodes (55): TechnicalSpec, CodeArtifact, TechnicalSpec, CodeArtifact, DebugReport, architect_node(), coder_node(), debugger_node() (+47 more)

### Community 2 - "Community 2"
Cohesion: 0.06
Nodes (36): Connection, Path, QuotaTracker, Persistent SQLite-backed quota counters with automatic daily reset.  Limits (saf, Return the daily limit for *provider*.          For Groq the limit is *per model, Return today's call count for *provider*/*model*., Return how many calls remain today for *provider*/*model*., Check whether a call is allowed within today's quota. (+28 more)

### Community 3 - "Community 3"
Cohesion: 0.08
Nodes (19): custom_tracker(), Tests for ModelRouter, QuotaTracker, and fallback cascade. These tests mock HTTP, Provide an isolated QuotaTracker using a temp database., Test cohere routing through ClientV2 mock/interceptor., Verify that OpenRouter uses a single SHARED counter for all :free models.      C, Provide a ModelRouter bound to the isolated QuotaTracker., Verify that OpenRouter and Cohere quotas are isolated from each other.      Open, Verify that run_grounding raises a ValueError if search_results is empty/whitesp (+11 more)

### Community 4 - "Community 4"
Cohesion: 0.10
Nodes (20): _isolate_clients(), Path, Root conftest — sets up fake API keys so that imports of core.clients don't rais, Clear cached LLM clients between tests to avoid cross-contamination., Provide a temporary SQLite path for QuotaTracker in tests., tmp_quota_db(), clear_client_cache(), get_client() (+12 more)

### Community 5 - "Community 5"
Cohesion: 0.11
Nodes (17): 1. Clone the repository, 2. Create a virtual environment, 3. Install dependencies, 4. Configure environment variables, 5. Initialize Git (required for System A rollback), Deprecated Models (DO NOT USE), Important Dates, Installation (+9 more)

### Community 6 - "Community 6"
Cohesion: 0.19
Nodes (13): check_hy3_expiration(), main(), Command Line Interface for running Multi-Agent pipelines.  Commands:   - run vib, Multi-Agent Ecosystem Command Line Interface., Run a multi-agent orchestration graph., Execute System A: Architect -> Coder -> Test Executor -> Debugger with Git rollb, Execute System B: Safety -> Context Compression -> Web Search -> Grounding -> Sy, Validate that required API keys are configured and not placeholders. (+5 more)

### Community 7 - "Community 7"
Cohesion: 0.17
Nodes (11): Definition of Done, Fase 0 — Andamiaje del repositorio, Fase 1 — Capa de clientes y cuotas (`core/`), Fase 2 — Esquemas Pydantic (`schemas/`), Fase 3 — Agentes PydanticAI, Fase 4 — Grafo LangGraph, Sistema A (Vibe Coding), Fase 5 — Grafo LangGraph, Sistema B (Deep Research), Fase 6 — CLI y observabilidad (+3 more)

### Community 8 - "Community 8"
Cohesion: 0.24
Nodes (10): GroundedReport, clean_and_parse_synthesizer_report(), extract_urls(), Synthesizer agent using PydanticAI definition. Synthesizes grounded reports into, Clean markdown code blocks and parse content as GroundedReport., Helper to extract clean http/https URLs from text., Run the Synthesizer agent to compile the final publication-grade document., run_synthesizer() (+2 more)

### Community 9 - "Community 9"
Cohesion: 0.32
Nodes (7): _build_safe_query(), raise_if_no_live_search(), Web Search agent using PydanticAI definition. Queries the web using groq/compoun, Build a short, bounded query string from a list of search terms.      Truncates, Raise ``NoLiveSearchError`` if the result admits it wasn't a real search.      C, Run a web search using groq/compound-mini (Tavily-integrated).      Returns the, run_web_search()

## Knowledge Gaps
- **30 isolated node(s):** `Path`, `ClientV2`, `LLMClient`, `Path`, `Connection` (+25 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `QuotaTracker` connect `Community 2` to `Community 3`?**
  _High betweenness centrality (0.149) - this node is a cross-community bridge._
- **Why does `GroundedReport` connect `Community 0` to `Community 8`, `Community 1`, `Community 3`?**
  _High betweenness centrality (0.107) - this node is a cross-community bridge._
- **Why does `ModelRouter` connect `Community 2` to `Community 3`?**
  _High betweenness centrality (0.049) - this node is a cross-community bridge._
- **Are the 9 inferred relationships involving `QuotaTracker` (e.g. with `EmptyCompletionError` and `LLMResponse`) actually correct?**
  _`QuotaTracker` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `GroundedReport` (e.g. with `Any` and `GroundedReport`) actually correct?**
  _`GroundedReport` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `TechnicalSpec` (e.g. with `TechnicalSpec` and `CodeArtifact`) actually correct?**
  _`TechnicalSpec` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `CodeArtifact` (e.g. with `CodeArtifact` and `TechnicalSpec`) actually correct?**
  _`CodeArtifact` has 9 INFERRED edges - model-reasoned connections that need verification._