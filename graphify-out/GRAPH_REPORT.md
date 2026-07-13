# Graph Report - MultiAgent  (2026-07-13)

## Corpus Check
- 61 files · ~48,273 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1077 nodes · 2593 edges · 60 communities (56 shown, 4 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 232 edges (avg confidence: 0.56)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `c132b135`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_External Skills CLI|External Skills CLI]]
- [[_COMMUNITY_Planner Orchestration|Planner Orchestration]]
- [[_COMMUNITY_Deep Research Graph|Deep Research Graph]]
- [[_COMMUNITY_TUI App Shell|TUI App Shell]]
- [[_COMMUNITY_Quota Tracker SQLite|Quota Tracker SQLite]]
- [[_COMMUNITY_Context Tools Files|Context Tools Files]]
- [[_COMMUNITY_CLI Entry Commands|CLI Entry Commands]]
- [[_COMMUNITY_Model Router Config|Model Router Config]]
- [[_COMMUNITY_Router Fallback Tests|Router Fallback Tests]]
- [[_COMMUNITY_Vibe Coding Architect|Vibe Coding Architect]]
- [[_COMMUNITY_Coder Agent Artifacts|Coder Agent Artifacts]]
- [[_COMMUNITY_Grounding And Runs|Grounding And Runs]]
- [[_COMMUNITY_Config PiP UI|Config PiP UI]]
- [[_COMMUNITY_Slash Commands Chat|Slash Commands Chat]]
- [[_COMMUNITY_API Keys Providers|API Keys Providers]]
- [[_COMMUNITY_Host Tools Exec|Host Tools Exec]]
- [[_COMMUNITY_Session Context Compact|Session Context Compact]]
- [[_COMMUNITY_Side Panel UI|Side Panel UI]]
- [[_COMMUNITY_Run History DB|Run History DB]]
- [[_COMMUNITY_Research Safety Compress|Research Safety Compress]]
- [[_COMMUNITY_Agent Chat Loop|Agent Chat Loop]]
- [[_COMMUNITY_TUI Main Entry|TUI Main Entry]]
- [[_COMMUNITY_Deep Research Schemas|Deep Research Schemas]]
- [[_COMMUNITY_Pipeline Graph Tests|Pipeline Graph Tests]]
- [[_COMMUNITY_Synthesizer Agent|Synthesizer Agent]]
- [[_COMMUNITY_Test Executor Node|Test Executor Node]]
- [[_COMMUNITY_LLM Clients Cache|LLM Clients Cache]]
- [[_COMMUNITY_MCP Server Tools|MCP Server Tools]]
- [[_COMMUNITY_Deep Research Invoke|Deep Research Invoke]]
- [[_COMMUNITY_Synthesizer Citations|Synthesizer Citations]]
- [[_COMMUNITY_CLI Chat Defaults|CLI Chat Defaults]]
- [[_COMMUNITY_Vibe Graph Routing|Vibe Graph Routing]]
- [[_COMMUNITY_Prompt Area Input|Prompt Area Input]]
- [[_COMMUNITY_Vibe Role Config|Vibe Role Config]]
- [[_COMMUNITY_Dependencies LangGraph|Dependencies LangGraph]]
- [[_COMMUNITY_Code Preserve Merge|Code Preserve Merge]]
- [[_COMMUNITY_ModelRouter Core|ModelRouter Core]]
- [[_COMMUNITY_Help PiP Overlay|Help PiP Overlay]]
- [[_COMMUNITY_Providers Overview|Providers Overview]]
- [[_COMMUNITY_GraphRAG Query|GraphRAG Query]]
- [[_COMMUNITY_Chat History Widgets|Chat History Widgets]]
- [[_COMMUNITY_Fallback Cascade Config|Fallback Cascade Config]]
- [[_COMMUNITY_Vibe Pipeline Invoke|Vibe Pipeline Invoke]]
- [[_COMMUNITY_Web Search Agent|Web Search Agent]]
- [[_COMMUNITY_Compose Layout Widgets|Compose Layout Widgets]]
- [[_COMMUNITY_Quotas And Router|Quotas And Router]]
- [[_COMMUNITY_Debugger Agent|Debugger Agent]]
- [[_COMMUNITY_Status Line Widgets|Status Line Widgets]]
- [[_COMMUNITY_Language Helpers|Language Helpers]]
- [[_COMMUNITY_Approval Bar UI|Approval Bar UI]]
- [[_COMMUNITY_Global Skills System|Global Skills System]]
- [[_COMMUNITY_Graphify Workflow|Graphify Workflow]]
- [[_COMMUNITY_Install Launcher Script|Install Launcher Script]]

## God Nodes (most connected - your core abstractions)
1. `ConversationSession` - 92 edges
2. `MultiAgentApp` - 55 edges
3. `ToolCall` - 35 edges
4. `CodeArtifact` - 31 edges
5. `QuotaTracker` - 29 edges
6. `TechnicalSpec` - 28 edges
7. `exec_tool()` - 27 edges
8. `ConversationSession` - 24 edges
9. `dispatch()` - 24 edges
10. `CommandResult` - 23 edges

## Surprising Connections (you probably didn't know these)
- `cli.chat → groq/openai/gpt-oss-120b` --semantically_similar_to--> `Chat tool-using agent`  [INFERRED] [semantically similar]
  config/defaults_model_router.yaml → README.md
- `CondensedTrends` --uses--> `CondensedTrends`  [INFERRED]
  agents/deep_research/context_compressor.py → schemas/deep_research.py
- `Any` --uses--> `GroundedReport`  [INFERRED]
  agents/deep_research/grounding.py → schemas/deep_research.py
- `GroundedReport` --uses--> `GroundedReport`  [INFERRED]
  agents/deep_research/grounding.py → schemas/deep_research.py
- `SafetyClassification` --uses--> `SafetyClassification`  [INFERRED]
  agents/deep_research/safety_filter.py → schemas/deep_research.py

## Import Cycles
- 1-file cycle: `core/router.py -> core/router.py`
- 1-file cycle: `core/clients.py -> core/clients.py`

## Hyperedges (group relationships)
- **Vibe Coding pipeline role sequence** — readme_architect, readme_coder, readme_test_executor, readme_debugger [EXTRACTED 1.00]
- **Deep Research pipeline stages** — readme_safety_filter, readme_context_compressor, readme_web_search, readme_grounding, readme_synthesizer [EXTRACTED 1.00]
- **Model router config: live, defaults, and agent load path** — readme_model_router_yaml, readme_defaults_model_router_yaml, readme_agent_config, config_model_router_live, config_defaults_model_router_providers [INFERRED 0.85]

## Communities (60 total, 4 thin omitted)

### Community 0 - "External Skills CLI"
Cohesion: 0.26
Nodes (17): Manage global external skills (path + SKILL.md format)., _skills(), add_skill(), _ensure_global_file(), load_registry(), load_skill(), parse_skill_md(), Any (+9 more)

### Community 1 - "Planner Orchestration"
Cohesion: 0.17
Nodes (24): format_plan(), plan_pipelines(), PipelinePlan, Planner agent: given a free-form user prompt, choose System A (/vibe), System B, Ask the planner model for a PipelinePlan.      If *provider*/*model* are set, th, _emit(), execute_plan(), Any (+16 more)

### Community 2 - "Deep Research Graph"
Cohesion: 0.12
Nodes (28): CondensedTrends, Extract short search terms from the research query., run_context_compressor(), Classify whether the research query is safe to process., run_safety_filter(), context_compressor_node(), DeepResearchState, get_deep_research_graph() (+20 more)

### Community 3 - "TUI App Shell"
Cohesion: 0.31
Nodes (4): ChatHistory, Scrollable chat: Markdown for assistant, fenced code block for user prompts., User prompt as a markdown fenced block (``` ... ```)., Assistant reply as rendered markdown (no role label).

### Community 4 - "Quota Tracker SQLite"
Cohesion: 0.12
Nodes (11): Connection, Open a connection to the quota database., ISO-formatted current date for partitioning., Determine the tracking key for a (provider, model) pair.          * **Groq** — e, Return the daily limit for *provider*.          Reads from ``config/model_router, Return today's call count for *provider*/*model*., Return how many calls remain today for *provider*/*model*., Check whether a call is allowed within today's quota. (+3 more)

### Community 5 - "Context Tools Files"
Cohesion: 0.08
Nodes (40): _clean_final(), _modern_toolbox_block(), Tool-using chat loop for the interactive CLI.  The host fetches graph/dir seeds,, Cheap host-side context so the model need not invent graphify CLI., Installed catalog capabilities so the model prefers modern CLIs., _seed_context(), _system_prompt(), extract_path_candidates() (+32 more)

### Community 6 - "CLI Entry Commands"
Cohesion: 0.05
Nodes (42): config(), config_reset(), config_set(), keys(), _print_quota_summary(), Command Line Interface for Free-Multi-Agent.  Pipelines (vibe-coding / deep-rese, Show today's free-tier quota usage (from data/quotas.db)., Show recent pipeline runs (from data/runs.db). (+34 more)

### Community 7 - "Model Router Config"
Cohesion: 0.17
Nodes (25): _config(), config_show(), Print active provider/model per agent role., Force the next ``get_agent_config`` call to re-read the YAML from disk.      Use, reload_config(), ensure_defaults_snapshot(), get_cli_settings(), list_roles() (+17 more)

### Community 8 - "Router Fallback Tests"
Cohesion: 0.08
Nodes (19): custom_tracker(), Tests for ModelRouter, QuotaTracker, and fallback cascade. These tests mock HTTP, Provide an isolated QuotaTracker using a temp database., Historical bug: groq→gemini→openrouter→groq cycled when Gemini failed.      With, Provide a ModelRouter bound to the isolated QuotaTracker., Test cohere routing through ClientV2 mock/interceptor., Verify that OpenRouter uses a single SHARED counter for all :free models.      C, Verify that OpenRouter and Cohere quotas are isolated from each other.      Open (+11 more)

### Community 9 - "Vibe Coding Architect"
Cohesion: 0.08
Nodes (50): _after_architect(), _after_coder(), architect_node(), coder_node(), debugger_node(), debugger_routing(), get_git_repo(), get_vibe_coding_graph() (+42 more)

### Community 10 - "Coder Agent Artifacts"
Cohesion: 0.10
Nodes (32): TechnicalSpec, CodeArtifact, TechnicalSpec, CodeArtifact, Load role config from YAML, call the router, parse JSON into ``schema``.      Ex, run_structured_agent(), DebugReport, CodeArtifact (+24 more)

### Community 11 - "Grounding And Runs"
Cohesion: 0.21
Nodes (11): Remove optional markdown code fences around model JSON/text output., strip_fences(), extract_urls(), Extract http(s) URLs from *text*, de-duplicated, order preserved., Unit tests for agent_runtime, run history, entry schemas, and YAML helpers., test_deep_research_request_accepts_topic(), test_extract_urls_dedupes(), test_max_fix_cycles_from_yaml() (+3 more)

### Community 12 - "Config PiP UI"
Cohesion: 0.24
Nodes (4): Changed, ConfigPiP, _models_for_provider(), Full-height side panel; each tab is one scroll (no nested height fight).

### Community 13 - "Slash Commands Chat"
Cohesion: 0.12
Nodes (34): _approve_cmd(), chat_turn(), _clear(), CommandResult, _compact(), _do(), _exit(), _help() (+26 more)

### Community 14 - "API Keys Providers"
Cohesion: 0.06
Nodes (59): Interactive Free-Multi-Agent CLI (slash commands + session context)., run_tui(), _invalidate_option_caches(), _known_provider_options(), _planner_options(), _provider_options(), _quiet_logging_for_tui(), MultiAgent TUI — chat + side config/help panels that push the main column.  - En (+51 more)

### Community 15 - "Host Tools Exec"
Cohesion: 0.05
Nodes (92): Terminal toolbox: doctor / suggest / search over the curated catalog., _tools(), exec_tool(), format_tool_results(), _looks_like_pip_or_venv(), needs_approval(), Any, ApprovalFn (+84 more)

### Community 16 - "Session Context Compact"
Cohesion: 0.11
Nodes (19): dispatch(), Parse a slash command line and run the handler., ConversationSession, Message, OpenAI-style messages for the chat role (skip pure system-notes)., Last *n* user/assistant turns only (for slim graph-augmented chat).          Exc, Auto-run local compact when usage exceeds *threshold*., Drop middle turns, keep system + recent messages (no LLM).          Returns a hu (+11 more)

### Community 17 - "Side Panel UI"
Cohesion: 0.08
Nodes (24): agent_chat_turn(), Any, ApprovalFn, ConversationSession, Run a tool-augmented chat turn., Run local graphify update; return status text for the user., _try_graphify_update(), _wants_graph_refresh() (+16 more)

### Community 18 - "Run History DB"
Cohesion: 0.18
Nodes (11): Any, Connection, Path, Mark a run as completed / failed / aborted., Return newest runs first., Thread-safe log of MAS pipeline executions., Insert a running row; return its id., RunHistory (+3 more)

### Community 19 - "Research Safety Compress"
Cohesion: 0.24
Nodes (13): invoke_router(), Any, Shared runtime helpers for every agent role.  Eliminates the 8-way copy of: load, Like ``run_structured_agent`` but returns the raw ``LLMResponse`` (prose paths)., Call either ``ModelRouter.call_agent``, module ``call_agent``, or a test mock., run_role_raw(), LLMResponse, Standardised response envelope returned by ``call_agent``. (+5 more)

### Community 20 - "Agent Chat Loop"
Cohesion: 0.27
Nodes (16): active_skills(), build_skills_system_block(), list_skills(), Resolve user path to the SKILL.md file., Validate format and return metadata (enabled=False placeholder)., Markdown block to inject into the chat system prompt for enabled skills., resolve_skill_md(), validate_skill_path() (+8 more)

### Community 21 - "TUI Main Entry"
Cohesion: 0.20
Nodes (4): HelpPiP, F1 help side panel (not dumped into chat history)., Keep PiP within half screen when the terminal is resized., Resize

### Community 22 - "Deep Research Schemas"
Cohesion: 0.12
Nodes (21): BaseModel, Context Compressor agent for System B (Deep Research).  Provider/model/fallback, Safety Filter agent for System B (Deep Research).  Provider/model from config/mo, CondensedTrends, GroundedReport, Pydantic schemas for the System B (Deep Research) pipeline. These models define, Output schema for the Safety Filter agent.      Determines if the research topic, Output schema for the Context Compressor agent.      Represents key entities, tr (+13 more)

### Community 23 - "Pipeline Graph Tests"
Cohesion: 0.13
Nodes (18): build_graph_augmented_messages(), Compose a **small** message list for the chat model.      - Does not include the, estimate_tokens(), Multi-turn conversation context for the interactive CLI.  Tracks messages, estim, Cheap token estimate without tiktoken (≈ 4 chars/token)., Path, Tests for interactive CLI helpers (config editor, keys, session, slash cmds)., test_build_graph_augmented_messages_is_slim() (+10 more)

### Community 24 - "Synthesizer Agent"
Cohesion: 0.33
Nodes (6): initial_vibe_coding_state(), Build a fresh graph state for System A., Debugger LLM failures must still increment fix_attempts and end the graph., Architect failure must go to rollback/end, not spin into coder forever., test_vibe_coding_architect_failure_does_not_loop(), test_vibe_coding_stops_when_debugger_always_raises()

### Community 25 - "Test Executor Node"
Cohesion: 0.20
Nodes (9): call_agent(), ModelRouter, Any, ClientV2, Routes LLM calls with automatic fallback cascade and quota tracking., Route the call to the correct provider backend.          Raises:             Emp, Make an LLM call with automatic fallback on quota / HTTP / empty-completion erro, Walk the cascade graph skipping already-tried (provider, model) pairs. (+1 more)

### Community 26 - "LLM Clients Cache"
Cohesion: 0.40
Nodes (5): chat_cmd(), main(), Free-Multi-Agent — interactive CLI (pipelines only inside the TUI).      With no, Interactive TUI (pipelines via /do planner only here)., Context

### Community 27 - "MCP Server Tools"
Cohesion: 0.22
Nodes (15): deep_research.context_compressor → openrouter/tencent/hy3:free, deep_research role config (defaults), deep_research.grounding → cohere/command-a-plus-05-2026, deep_research.safety_filter → groq/gpt-oss-safeguard-20b, deep_research.synthesizer → cohere/command-r-plus-08-2024, deep_research.web_search → groq/compound-mini, agents/ package, Context Compressor (Deep Research) (+7 more)

### Community 28 - "Deep Research Invoke"
Cohesion: 0.50
Nodes (4): _providers_used_by_config(), Providers referenced by active System A/B + cli roles., Validate keys only for providers actually used in model_router.yaml roles., validate_api_keys()

### Community 29 - "Synthesizer Citations"
Cohesion: 0.19
Nodes (12): GroundedReport, extract_url_set(), Lowercased, slash-stripped URL set for cross-referencing citations., clean_and_parse_synthesizer_report(), extract_urls(), Synthesizer agent for System B (Deep Research).  JSON GroundedReport output; ret, Compatibility wrapper — prefers shared ``extract_url_set``., Clean markdown code blocks and parse content as GroundedReport. (+4 more)

### Community 30 - "CLI Chat Defaults"
Cohesion: 0.24
Nodes (11): cli chat/planner config (defaults), cli.chat → groq/openai/gpt-oss-120b, cli.planner → groq/openai/gpt-oss-120b (defaults), cli.use_graphify=true (defaults), cli.planner → mistral/mistral-small-latest (live), cli.use_graphify=true (live), Chat tool-using agent, Graphify knowledge graph (+3 more)

### Community 32 - "Prompt Area Input"
Cohesion: 0.18
Nodes (5): PromptArea, Grow input-row with content; skip no-op height changes., Multi-line prompt: Enter = send, Shift+Enter = newline., Key, TextArea

### Community 33 - "Vibe Role Config"
Cohesion: 0.20
Nodes (15): vibe_coding.architect → cohere/command-a-plus-05-2026, vibe_coding.coder → openrouter/cohere/north-mini-code:free, vibe_coding.debugger → openrouter/tencent/hy3:free, vibe_coding role config (defaults), tencent/hy3:free free_until 2026-07-21, vibe_coding role config (live), Architect (Vibe Coding role), Coder (Vibe Coding role) (+7 more)

### Community 34 - "Dependencies LangGraph"
Cohesion: 0.15
Nodes (12): graphs/ LangGraph pipelines, LangGraph + SQLite checkpoints, Provider: Cohere, click>=8.1.0, cohere>=5.0.0, gitpython>=3.1.0, langgraph>=0.4.0, langgraph-checkpoint-sqlite>=2.0.0 (+4 more)

### Community 35 - "Code Preserve Merge"
Cohesion: 0.13
Nodes (21): Path, _apply_preservation_warnings(), CodeArtifact, Log (and note in summary) if the Coder dropped top-level symbols from existing f, Path, Tests for existing-source preservation helpers and coder merge wiring., Integration-ish: coder_node reads disk before run_coder., test_coder_node_loads_disk_and_calls_run_coder() (+13 more)

### Community 36 - "ModelRouter Core"
Cohesion: 0.29
Nodes (7): Path, QuotaTracker, Create the usage table if it doesn't exist yet., Thread-safe, SQLite-backed quota tracker with automatic daily reset.      Usage:, get_router(), Path, QuotaTracker

### Community 37 - "Help PiP Overlay"
Cohesion: 0.18
Nodes (12): Any, GroundedReport, find_no_live_search_marker(), Return the first matching marker in *text*, or None if clean., _extract_sources_from_citations(), Grounding agent for System B (Deep Research).  Plain cited prose from the model;, Best-effort extraction of source URLs from Cohere's native citations., Ground the query against search_results; return prose + sources. (+4 more)

### Community 38 - "Providers Overview"
Cohesion: 0.12
Nodes (17): Deprecated models list, Providers block (factory defaults), Launch-cwd vs install-tree isolation, config/defaults_model_router.yaml (factory reset), Free-Multi-Agent, Notes, Project layout, Provider: Cerebras (+9 more)

### Community 39 - "GraphRAG Query"
Cohesion: 0.20
Nodes (13): _build_planner_context(), _graphify(), File reads + optional graphify for the planner (not every turn blindly)., Query the local knowledge graph (budgeted). Same backend free chat uses., paths_from_graph_snippet(), Best-effort extract source_file paths from a graphify text dump., graph_available(), _local_fallback() (+5 more)

### Community 40 - "Chat History Widgets"
Cohesion: 0.15
Nodes (12): EmptyCompletionError, OpenAI, QuotaExhaustedError, Intelligent model router with cascading fallback and quota management.  The rout, Drop the cached default router (e.g. after editing model_router.yaml)., Raised when a provider returns HTTP 200 but empty/whitespace content.      Treat, Raised when every provider in the fallback chain is exhausted., reset_router() (+4 more)

### Community 41 - "Fallback Cascade Config"
Cohesion: 0.22
Nodes (10): Acyclic fallback cascade design, fallback_cascade (acyclic DAG, defaults), deep_research role config (live), fallback_cascade (live), Live model_router.yaml config, core/agent_config.py, core/ (router, quotas, clients, keys, skills), config/model_router.yaml (live) (+2 more)

### Community 42 - "Vibe Pipeline Invoke"
Cohesion: 0.18
Nodes (11): Chat (tool-using agent), cli_app (TUI + tools), cli.py, Doctor profiles, Interactive TUI, Keys & chrome, Outer CLI (no pipelines), Runtime (automatic) (+3 more)

### Community 43 - "Web Search Agent"
Cohesion: 0.24
Nodes (10): NoLiveSearchError, raise_if_no_live_search(), Shared guards for live web-search verification and URL extraction.  Single sourc, Raised when search output admits it did not perform a live search., Raise ``NoLiveSearchError`` if the result admits it wasn't a real search., _build_safe_query(), Web Search agent for System B (Deep Research).  Provider/model from config/model, Build a short, bounded query string from a list of search terms. (+2 more)

### Community 44 - "Compose Layout Widgets"
Cohesion: 0.26
Nodes (7): ApprovalBar, Compact vertical list: bold header + three bordered, centered option rows., ComposeResult, Horizontal, Static, Vertical, VerticalScroll

### Community 45 - "Quotas And Router"
Cohesion: 0.19
Nodes (14): check_hy3_expiration(), Warn if tencent/hy3:free is near or past free_until (from YAML cache)., get_agent_config(), get_full_config(), get_max_fix_cycles(), _load(), Any, Path (+6 more)

### Community 47 - "Status Line Widgets"
Cohesion: 0.13
Nodes (7): _planner_label(), ConversationSession, Cheap path: update ctx line without rebuilding selects., Update status line. Config selects only when full_config=True., _session_info_text(), _short_cwd(), StatusLine

### Community 52 - "Approval Bar UI"
Cohesion: 0.15
Nodes (5): MultiAgentApp, Progress line from the agent loop (called via call_from_thread)., Called from PromptArea (Enter)., Chat shell with optional side panel that pushes the main column., Click

### Community 53 - "Global Skills System"
Cohesion: 0.24
Nodes (9): Global skills (~/.config/multiagent/), CLI, Format, Global registry, MultiAgent skills, Runtime behaviour, Skill body injection into chat system prompt, SKILL.md format (+1 more)

### Community 54 - "Graphify Workflow"
Cohesion: 0.50
Nodes (4): graphify Knowledge Graph (graphify-out/), graphify query / query_graph, graphify update (AST-only refresh), graphify Workflow

## Knowledge Gaps
- **46 isolated node(s):** `install-launcher.sh script`, `Context`, `Any`, `Any`, `ApprovalFn` (+41 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ConversationSession` connect `Session Context Compact` to `External Skills CLI`, `Prompt Area Input`, `TUI App Shell`, `Context Tools Files`, `GraphRAG Query`, `Model Router Config`, `Config PiP UI`, `Slash Commands Chat`, `API Keys Providers`, `Compose Layout Widgets`, `Status Line Widgets`, `Side Panel UI`, `Host Tools Exec`, `Research Safety Compress`, `Approval Bar UI`, `TUI Main Entry`, `Agent Chat Loop`, `Pipeline Graph Tests`?**
  _High betweenness centrality (0.135) - this node is a cross-community bridge._
- **Why does `QuotaTracker` connect `ModelRouter Core` to `Quota Tracker SQLite`, `Chat History Widgets`, `Router Fallback Tests`, `Quotas And Router`, `Research Safety Compress`, `Test Executor Node`?**
  _High betweenness centrality (0.067) - this node is a cross-community bridge._
- **Why does `clear_client_cache()` connect `API Keys Providers` to `Router Fallback Tests`?**
  _High betweenness centrality (0.040) - this node is a cross-community bridge._
- **Are the 30 inferred relationships involving `ConversationSession` (e.g. with `Changed` and `Any`) actually correct?**
  _`ConversationSession` has 30 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `MultiAgentApp` (e.g. with `ConversationSession` and `ToolCall`) actually correct?**
  _`MultiAgentApp` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 27 inferred relationships involving `ToolCall` (e.g. with `Changed` and `Any`) actually correct?**
  _`ToolCall` has 27 INFERRED edges - model-reasoned connections that need verification._
- **Are the 13 inferred relationships involving `CodeArtifact` (e.g. with `CodeArtifact` and `TechnicalSpec`) actually correct?**
  _`CodeArtifact` has 13 INFERRED edges - model-reasoned connections that need verification._