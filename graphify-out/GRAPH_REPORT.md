# Graph Report - MultiAgent  (2026-07-09)

## Corpus Check
- 58 files · ~34,787 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 924 nodes · 2100 edges · 70 communities (54 shown, 16 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 142 edges (avg confidence: 0.6)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `0e5455e5`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Interactive CLI|Interactive CLI]]
- [[_COMMUNITY_Interactive CLI 2|Interactive CLI 2]]
- [[_COMMUNITY_Interactive CLI 3|Interactive CLI 3]]
- [[_COMMUNITY_Interactive CLI 4|Interactive CLI 4]]
- [[_COMMUNITY_Quota Tracking|Quota Tracking]]
- [[_COMMUNITY_Interactive CLI 5|Interactive CLI 5]]
- [[_COMMUNITY_Deep Research|Deep Research]]
- [[_COMMUNITY_Vibe Coding|Vibe Coding]]
- [[_COMMUNITY_Interactive CLI 6|Interactive CLI 6]]
- [[_COMMUNITY_Deep Research 2|Deep Research 2]]
- [[_COMMUNITY_Interactive CLI 7|Interactive CLI 7]]
- [[_COMMUNITY_Interactive CLI 8|Interactive CLI 8]]
- [[_COMMUNITY_Run History|Run History]]
- [[_COMMUNITY_Vibe Coding 2|Vibe Coding 2]]
- [[_COMMUNITY_Vibe Coding 3|Vibe Coding 3]]
- [[_COMMUNITY_search_guards.py|search_guards.py]]
- [[_COMMUNITY_Deep Research 3|Deep Research 3]]
- [[_COMMUNITY_Git Safety|Git Safety]]
- [[_COMMUNITY_Vibe Coding 4|Vibe Coding 4]]
- [[_COMMUNITY_Model Router|Model Router]]
- [[_COMMUNITY_Model Router 2|Model Router 2]]
- [[_COMMUNITY_Interactive CLI 9|Interactive CLI 9]]
- [[_COMMUNITY_Deep Research 4|Deep Research 4]]
- [[_COMMUNITY_Vibe Coding 5|Vibe Coding 5]]
- [[_COMMUNITY_Deep Research 5|Deep Research 5]]
- [[_COMMUNITY_Interactive CLI 10|Interactive CLI 10]]
- [[_COMMUNITY_Vibe Coding 6|Vibe Coding 6]]
- [[_COMMUNITY_Deep Research 6|Deep Research 6]]
- [[_COMMUNITY_Vibe Coding 7|Vibe Coding 7]]
- [[_COMMUNITY_graphify Knowledge Graph (graphify-out)|graphify Knowledge Graph (graphify-out/)]]
- [[_COMMUNITY_Model Router 3|Model Router 3]]
- [[_COMMUNITY_Vibe Coding 8|Vibe Coding 8]]
- [[_COMMUNITY_Schemas|Schemas]]
- [[_COMMUNITY_Schemas 2|Schemas 2]]
- [[_COMMUNITY_Schemas 3|Schemas 3]]
- [[_COMMUNITY_Deep Research 7|Deep Research 7]]
- [[_COMMUNITY_Interactive CLI 11|Interactive CLI 11]]
- [[_COMMUNITY_Schemas 4|Schemas 4]]
- [[_COMMUNITY_Schemas 5|Schemas 5]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]

## God Nodes (most connected - your core abstractions)
1. `ConversationSession` - 53 edges
2. `MultiAgentApp` - 47 edges
3. `CodeArtifact` - 29 edges
4. `TechnicalSpec` - 28 edges
5. `QuotaTracker` - 26 edges
6. `Free-Multi-Agent` - 23 edges
7. `ConversationSession` - 22 edges
8. `CommandResult` - 21 edges
9. `get_cli_settings()` - 21 edges
10. `DebugReport` - 21 edges

## Surprising Connections (you probably didn't know these)
- `Vibe Coding LangGraph (Architect→Coder→Debugger + Git rollback)` --semantically_similar_to--> `System A — Vibe Coding`  [INFERRED] [semantically similar]
  Implementation_plan.md → README.md
- `Deep Research LangGraph (5-stage + SQLite checkpoints)` --semantically_similar_to--> `System B — Deep Research`  [INFERRED] [semantically similar]
  Implementation_plan.md → README.md
- `TechnicalSpec` --uses--> `TechnicalSpec`  [INFERRED]
  agents/vibe_coding/architect.py → schemas/vibe_coding.py
- `LangGraph` --semantically_similar_to--> `langgraph>=0.4.0`  [INFERRED] [semantically similar]
  README.md → requirements.txt
- `Pydantic v2` --semantically_similar_to--> `pydantic>=2.7.0`  [INFERRED] [semantically similar]
  README.md → requirements.txt

## Import Cycles
- 1-file cycle: `core/router.py -> core/router.py`
- 1-file cycle: `core/clients.py -> core/clients.py`

## Hyperedges (group relationships)
- **Vibe Coding pipeline flow: Architect → Coder → Test Executor → Debugger** — readme_agent_architect, readme_agent_coder, readme_test_executor, readme_agent_debugger [EXTRACTED 1.00]
- **Deep Research pipeline flow: Safety → Compress → Search → Ground → Synthesize** — readme_agent_safety_filter, readme_agent_context_compressor, readme_agent_web_search, readme_agent_grounding, readme_agent_synthesizer [EXTRACTED 1.00]
- **Shared free/trial LLM provider infrastructure** — readme_provider_groq, readme_provider_openrouter, readme_provider_cohere [EXTRACTED 1.00]

## Communities (70 total, 16 thin omitted)

### Community 0 - "Interactive CLI"
Cohesion: 0.20
Nodes (22): _config(), Force the next ``get_agent_config`` call to re-read the YAML from disk.      Use, reload_config(), ensure_defaults_snapshot(), list_roles(), Any, Path, Read/write model role assignments in ``config/model_router.yaml``.  Factory defa (+14 more)

### Community 1 - "Interactive CLI 2"
Cohesion: 0.15
Nodes (22): _build_planner_context(), chat_turn(), File reads + optional graphify for the planner (not every turn blindly)., Free-form message with **file reads** + **conditional graphify**.      Flow:, extract_path_candidates(), gather_file_context(), graph_mtime(), in_multiagent_project() (+14 more)

### Community 2 - "Interactive CLI 3"
Cohesion: 0.12
Nodes (28): context_compressor_node(), DeepResearchState, grounding_node(), initial_deep_research_state(), invoke_deep_research_pipeline(), Any, LangGraph orchestration for the System B (Deep Research) pipeline. Orchestrates:, Synthesize web results into grounded assertions with sources. (+20 more)

### Community 3 - "Interactive CLI 4"
Cohesion: 0.15
Nodes (10): ConversationSession, Message, OpenAI-style messages for the chat role (skip pure system-notes)., Auto-run local compact when usage exceeds *threshold*., Drop middle turns, keep system + recent messages (no LLM).          Returns a hu, Summarize older turns via LLM, keep recent messages intact., In-memory chat session with a soft context budget., test_chat_turn_uses_graph() (+2 more)

### Community 4 - "Quota Tracking"
Cohesion: 0.07
Nodes (26): Any, GroundedReport, _extract_sources_from_citations(), Best-effort extraction of source URLs from Cohere's native citations., Ground the query against search_results; return prose + sources., run_grounding(), GroundedReport, Pydantic schemas for the System B (Deep Research) pipeline. These models define (+18 more)

### Community 5 - "Interactive CLI 5"
Cohesion: 0.19
Nodes (4): _invalidate_option_caches(), MultiAgentApp, Chat shell with optional side panel that pushes the main column., Update status line. Config selects only when full_config=True.

### Community 6 - "Deep Research"
Cohesion: 0.13
Nodes (23): CodeArtifact, TechnicalSpec, BaseModel, CodeArtifact, Pydantic schemas for the System A (Vibe Coding) pipeline. These models define th, Output schema for the Architect agent.      Defines the system design, component, Output schema for the Coder agent.      Contains the written source code mapped, TechnicalSpec (+15 more)

### Community 7 - "Vibe Coding"
Cohesion: 0.17
Nodes (15): vibe_coding.architect, vibe_coding.coder, max_fix_cycles: 3, vibe_coding pipeline config, Git Rollback (git reset --hard after 3 fix cycles), Vibe Coding LangGraph (Architect→Coder→Debugger + Git rollback), Architect agent, Coder agent (+7 more)

### Community 8 - "Interactive CLI 6"
Cohesion: 0.19
Nodes (16): cli.chat, cohere_fallback → hy3:free, vibe_coding.debugger, deprecated models list, Model Router Configuration (live), fallback_cascade, groq_fallback → north-mini-code:free, openrouter_fallback → gpt-oss-120b (+8 more)

### Community 9 - "Deep Research 2"
Cohesion: 0.16
Nodes (18): plan_pipelines(), Planner agent: given a free-form user prompt, choose System A (/vibe), System B, Ask the planner model for a PipelinePlan.      If *provider*/*model* are set, th, invoke_router(), Any, Shared runtime helpers for every agent role.  Eliminates the 8-way copy of: load, Like ``run_structured_agent`` but returns the raw ``LLMResponse`` (prose paths)., Call either ``ModelRouter.call_agent``, module ``call_agent``, or a test mock. (+10 more)

### Community 10 - "Interactive CLI 7"
Cohesion: 0.10
Nodes (11): Side panel sibling of chat — pushes main content (does not float over it)., Keep PiP within half screen when the terminal is resized., SidePanel, MouseDown, MouseMove, MouseScrollDown, MouseScrollLeft, MouseScrollRight (+3 more)

### Community 11 - "Interactive CLI 8"
Cohesion: 0.15
Nodes (13): Model Router Factory Defaults, Factory defaults for /config reset, cli.py, config/defaults_model_router.yaml, GitPython, langgraph-checkpoint-sqlite, Pydantic v2, click>=8.1.0 (+5 more)

### Community 12 - "Run History"
Cohesion: 0.16
Nodes (13): get_run_history(), Any, Connection, Path, SQLite-backed execution history (MasExecution-style, local single-operator).  DB, Mark a run as completed / failed / aborted., Return newest runs first., Thread-safe log of MAS pipeline executions. (+5 more)

### Community 13 - "Vibe Coding 2"
Cohesion: 0.18
Nodes (15): _apply_preservation_warnings(), get_vibe_coding_graph(), initial_vibe_coding_state(), CodeArtifact, Log (and note in summary) if the Coder dropped top-level symbols from existing f, Build a fresh graph state for System A., Build and compile the StateGraph for System A., StateGraph (+7 more)

### Community 14 - "Vibe Coding 3"
Cohesion: 0.14
Nodes (16): CodeArtifact, DebugReport, debugger_node(), Runs the Debugger agent to assess test logs and propose fixes.      Always incre, DebugReport, Output schema for the Debugger agent.      Represents the result of running unit, Path, Create a temporary initialized Git repository with an initial commit. (+8 more)

### Community 15 - "search_guards.py"
Cohesion: 0.12
Nodes (5): PromptArea, Multi-line prompt: Enter = send, Shift+Enter = newline., Grow input-row with content; skip no-op height changes., Key, TextArea

### Community 16 - "Deep Research 3"
Cohesion: 0.12
Nodes (21): extract_url_set(), extract_urls(), find_no_live_search_marker(), NoLiveSearchError, raise_if_no_live_search(), Shared guards for live web-search verification and URL extraction.  Single sourc, Raised when search output admits it did not perform a live search., Return the first matching marker in *text*, or None if clean. (+13 more)

### Community 17 - "Git Safety"
Cohesion: 0.10
Nodes (35): _after_architect(), _after_coder(), coder_node(), debugger_routing(), get_git_repo(), git_commit_node(), git_rollback_node(), make_git_checkpoint() (+27 more)

### Community 18 - "Vibe Coding 4"
Cohesion: 0.27
Nodes (10): invoke_vibe_coding_pipeline(), Any, Normalize final state into a JSON-serializable summary (no full file bodies)., Validate input, run System A, record history, return summary dict.      Shared e, summarize_vibe_coding_state(), Optional MCP server for the vibe_coding pipeline.  Not required for the CLI (``p, Run the full vibe-coding pipeline (architect -> coder -> test_executor     -> de, run_vibe_coding() (+2 more)

### Community 19 - "Model Router"
Cohesion: 0.12
Nodes (16): Repository Scaffold (Fase 0), Deprecated Models (DO NOT USE), Free-Multi-Agent, Free-tier API platforms, Important Dates, Inside the TUI (pipelines), Interactive TUI (recommended), No project-side config required (+8 more)

### Community 20 - "Model Router 2"
Cohesion: 0.21
Nodes (13): get_agent_config(), get_full_config(), get_max_fix_cycles(), _load(), Any, Path, Central loader for per-agent provider/model assignments.  ``config/model_router., Load (and cache) the full YAML config.      A custom ``config_path`` bypasses th (+5 more)

### Community 21 - "Interactive CLI 9"
Cohesion: 0.19
Nodes (12): GroundedReport, Remove optional markdown code fences around model JSON/text output., strip_fences(), clean_and_parse_synthesizer_report(), extract_urls(), Synthesizer agent for System B (Deep Research).  JSON GroundedReport output; ret, Compatibility wrapper — prefers shared ``extract_url_set``., Clean markdown code blocks and parse content as GroundedReport. (+4 more)

### Community 22 - "Deep Research 4"
Cohesion: 0.14
Nodes (16): CondensedTrends, Extract short search terms from the research query., run_context_compressor(), Classify whether the research query is safe to process., run_safety_filter(), get_deep_research_graph(), Build and compile the StateGraph for System B.      Equipped with a persistent S, SafetyClassification (+8 more)

### Community 23 - "Vibe Coding 5"
Cohesion: 0.11
Nodes (45): Manage global external skills (path + SKILL.md format)., _skills(), List registered skills (ON/off). Works from any directory., Register a skill folder (must contain valid SKILL.md)., Enable a registered skill globally., Disable a skill globally (stays registered)., Unregister a skill (does not delete files)., Show skill metadata and body preview. (+37 more)

### Community 24 - "Deep Research 5"
Cohesion: 0.19
Nodes (13): deep_research.grounding, Grounding uses documents= not connectors, Cohere provider config, YAML/quotas.py limit sync requirement, deep_research.synthesizer, Grounding/Citations agent, Synthesizer agent, Cohere trial non-commercial restriction (+5 more)

### Community 25 - "Interactive CLI 10"
Cohesion: 0.33
Nodes (6): call_agent() with Fallback Cascade, Core Layer (clients, quotas, router), Hy3 free_until Hard-Date Watch (≤3 days warning), Persistent Quota Counters (disk-backed, midnight reset), tencent/hy3:free expires 2026-07-21, tencent/hy3:free

### Community 26 - "Vibe Coding 6"
Cohesion: 0.20
Nodes (22): _clear(), CommandResult, _compact(), _do(), _exit(), _graphify(), _help(), _history() (+14 more)

### Community 27 - "Deep Research 6"
Cohesion: 0.29
Nodes (8): LangGraph, mcp_server.py, opencode integration, Path-traversal protection, run_vibe_coding MCP tool, graphs/vibe_coding_graph.py, langgraph>=0.4.0, mcp>=1.0.0

### Community 28 - "Vibe Coding 7"
Cohesion: 0.19
Nodes (21): format_plan(), PipelinePlan, _emit(), execute_plan(), Any, PipelinePlan, Execute a PipelinePlan: run /vibe and/or /research steps, optionally chaining pr, Run each plan step in order. Returns aggregate result for the CLI. (+13 more)

### Community 29 - "graphify Knowledge Graph (graphify-out/)"
Cohesion: 0.50
Nodes (4): graphify Knowledge Graph (graphify-out/), graphify query / query_graph, graphify update (AST-only refresh), graphify Workflow

### Community 46 - "Community 46"
Cohesion: 0.08
Nodes (25): chat_cmd(), check_hy3_expiration(), config(), config_set(), keys(), main(), _print_quota_summary(), _providers_used_by_config() (+17 more)

### Community 47 - "Community 47"
Cohesion: 0.06
Nodes (37): Connection, Path, QuotaTracker, Create the usage table if it doesn't exist yet., Open a connection to the quota database., ISO-formatted current date for partitioning., Determine the tracking key for a (provider, model) pair.          * **Groq** — e, Return the daily limit for *provider*.          Reads from ``config/model_router (+29 more)

### Community 48 - "Community 48"
Cohesion: 0.24
Nodes (11): Path, test_extract_and_missing_symbols(), extract_top_level_symbols(), missing_preserved_symbols(), Read existing repo files so the Coder can merge changes without wiping useful lo, Names of top-level functions/classes (rough, language-agnostic-ish for py)., Symbols present in *old* but absent from *new* (likely accidental drops)., Load existing file text for paths the Architect plans to touch.      Returns a m (+3 more)

### Community 49 - "Community 49"
Cohesion: 0.07
Nodes (47): config_reset(), keys_set(), keys_status(), providers_cmd(), Overwrite model_router.yaml with factory defaults., Show which provider keys are set (masked)., Write a provider API key to .env., List free-tier-friendly providers, signup URLs, models, and key status. (+39 more)

### Community 50 - "Community 50"
Cohesion: 0.18
Nodes (7): ConfigPiP, _planner_label(), ConversationSession, Full-height side panel; each tab is one scroll (no nested height fight)., Cheap path: update ctx line without rebuilding selects., _short_cwd(), Vertical

### Community 51 - "Community 51"
Cohesion: 0.13
Nodes (21): deep_research.context_compressor, deep_research pipeline config, deep_research.safety_filter, deep_research.web_search, Deep Research LangGraph (5-stage + SQLite checkpoints), SqliteSaver Checkpoints for Mid-Pipeline Resume, core/agent_config.py, Context Compressor agent (+13 more)

### Community 52 - "Community 52"
Cohesion: 0.26
Nodes (11): dispatch(), Parse a slash command line and run the handler., Path, Tests for interactive CLI helpers (config editor, keys, session, slash cmds)., test_context_tools_path_extract_and_read(), test_dispatch_help(), test_dispatch_status(), test_dispatch_unknown() (+3 more)

### Community 53 - "Community 53"
Cohesion: 0.26
Nodes (6): ActionBar, Always-visible actions (compact never depends on Footer focus/bindings)., StatusLine, ComposeResult, Horizontal, Static

### Community 54 - "Community 54"
Cohesion: 0.22
Nodes (13): Return (provider, model) for planner: session override or YAML., _resolve_planner(), Interactive Free-Multi-Agent CLI (slash commands + session context)., run_tui(), _known_provider_options(), _planner_options(), _provider_options(), MultiAgent TUI — chat + side config/help panels that push the main column.  - En (+5 more)

### Community 55 - "Community 55"
Cohesion: 0.24
Nodes (10): build_graph_augmented_messages(), graph_available(), _local_fallback(), query_graph(), Graph-backed retrieval for the interactive chat.  Queries ``graphify-out/graph.j, Compose a **small** message list for the chat model.      - Does not include the, Return a compact graph traversal for *question*.      Prefers ``graphify query …, Keyword hit list from GRAPH_REPORT + graph.json when CLI is unavailable. (+2 more)

### Community 56 - "Community 56"
Cohesion: 0.33
Nodes (5): CLI, Format, Global registry, MultiAgent skills, Runtime behaviour

### Community 57 - "Community 57"
Cohesion: 0.32
Nodes (7): looks_non_english(), Any, Language helpers for chat + pipelines.  - Chat answers in the user's language (p, Cheap check — not a full language detector., Return English text suitable for Systems A/B.      If the text already looks Eng, to_english_for_pipelines(), test_language_helpers()

### Community 61 - "Community 61"
Cohesion: 0.29
Nodes (7): TechnicalSpec, architect_node(), Runs the Architect agent to design the TechnicalSpec., If the working tree is dirty, stash user changes (incl. untracked).      Rollbac, stash_preexisting_work(), Design the technical specification for the given idea., run_architect()

### Community 63 - "Community 63"
Cohesion: 0.29
Nodes (6): Multi-turn conversation context for the interactive CLI.  Tracks messages, estim, _session_info_text(), config_show(), Print active provider/model per agent role., get_cli_settings(), Return ``cli`` section with safe defaults.

### Community 64 - "Community 64"
Cohesion: 0.33
Nodes (3): Chat log optimized for mouse selection + bounded memory., SelectableLog, RichLog

### Community 65 - "Community 65"
Cohesion: 0.33
Nodes (6): 1. Clone the repository, 2. Create a virtual environment, 3. Install dependencies, 4. Configure API keys (once, in MultiAgent only), 5. Git note (System A only), Installation

### Community 68 - "Community 68"
Cohesion: 0.50
Nodes (3): estimate_tokens(), Cheap token estimate without tiktoken (≈ 4 chars/token)., test_estimate_tokens_positive()

## Knowledge Gaps
- **52 isolated node(s):** `install-launcher.sh script`, `Context`, `Any`, `Path`, `ClientV2` (+47 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **16 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ConversationSession` connect `Interactive CLI 4` to `Community 64`, `Community 66`, `Community 69`, `Interactive CLI 5`, `Interactive CLI 7`, `search_guards.py`, `Community 50`, `Community 52`, `Community 53`, `Community 54`, `Vibe Coding 5`, `Vibe Coding 6`, `Community 62`, `Community 63`?**
  _High betweenness centrality (0.107) - this node is a cross-community bridge._
- **Why does `MultiAgentApp` connect `Interactive CLI 5` to `Community 64`, `Community 66`, `Interactive CLI 4`, `Community 67`, `Interactive CLI 7`, `search_guards.py`, `Community 50`, `Community 53`, `Community 54`, `Community 62`?**
  _High betweenness centrality (0.050) - this node is a cross-community bridge._
- **Why does `QuotaTracker` connect `Community 47` to `Deep Research 2`, `Model Router 2`, `Quota Tracking`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Are the 25 inferred relationships involving `ConversationSession` (e.g. with `Changed` and `CommandResult`) actually correct?**
  _`ConversationSession` has 25 INFERRED edges - model-reasoned connections that need verification._
- **Are the 13 inferred relationships involving `CodeArtifact` (e.g. with `CodeArtifact` and `TechnicalSpec`) actually correct?**
  _`CodeArtifact` has 13 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `TechnicalSpec` (e.g. with `TechnicalSpec` and `CodeArtifact`) actually correct?**
  _`TechnicalSpec` has 12 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `QuotaTracker` (e.g. with `EmptyCompletionError` and `LLMResponse`) actually correct?**
  _`QuotaTracker` has 9 INFERRED edges - model-reasoned connections that need verification._