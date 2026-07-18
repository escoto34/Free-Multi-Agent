# Graph Report - MultiAgent  (2026-07-17)

## Corpus Check
- 84 files · ~87,023 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1562 nodes · 3839 edges · 82 communities (77 shown, 5 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 240 edges (avg confidence: 0.53)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `b18b8690`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_CLI Session Context|CLI Session Context]]
- [[_COMMUNITY_Docs and Config|Docs and Config]]
- [[_COMMUNITY_Source Fetch Search|Source Fetch Search]]
- [[_COMMUNITY_Agent Chat Context|Agent Chat Context]]
- [[_COMMUNITY_Research Grounding Types|Research Grounding Types]]
- [[_COMMUNITY_Skills Registry CLI|Skills Registry CLI]]
- [[_COMMUNITY_Vibe Coding Graph|Vibe Coding Graph]]
- [[_COMMUNITY_Entity Focus Anchors|Entity Focus Anchors]]
- [[_COMMUNITY_Host Tools Terminal|Host Tools Terminal]]
- [[_COMMUNITY_Main CLI Entrypoint|Main CLI Entrypoint]]
- [[_COMMUNITY_Pipeline Orchestration|Pipeline Orchestration]]
- [[_COMMUNITY_Toolbox Catalog|Toolbox Catalog]]
- [[_COMMUNITY_Slash Commands|Slash Commands]]
- [[_COMMUNITY_Search Guards Scrub|Search Guards Scrub]]
- [[_COMMUNITY_TUI App Core|TUI App Core]]
- [[_COMMUNITY_Quota Tracker|Quota Tracker]]
- [[_COMMUNITY_Chat Turn Tools|Chat Turn Tools]]
- [[_COMMUNITY_Router Fallback Tests|Router Fallback Tests]]
- [[_COMMUNITY_Deep Research Graph|Deep Research Graph]]
- [[_COMMUNITY_Coder Preserve Files|Coder Preserve Files]]
- [[_COMMUNITY_Model Router|Model Router]]
- [[_COMMUNITY_Research Run History|Research Run History]]
- [[_COMMUNITY_LLM Clients|LLM Clients]]
- [[_COMMUNITY_Web Search Agent|Web Search Agent]]
- [[_COMMUNITY_Config Editor|Config Editor]]
- [[_COMMUNITY_Research Pipeline Tests|Research Pipeline Tests]]
- [[_COMMUNITY_Architect Spec Schema|Architect Spec Schema]]
- [[_COMMUNITY_Graphify RAG|Graphify RAG]]
- [[_COMMUNITY_Debugger Rollback Tests|Debugger Rollback Tests]]
- [[_COMMUNITY_TUI Launch Init|TUI Launch Init]]
- [[_COMMUNITY_Research Constraints|Research Constraints]]
- [[_COMMUNITY_Toolbox Runtime Resolve|Toolbox Runtime Resolve]]
- [[_COMMUNITY_Agent Config Loader|Agent Config Loader]]
- [[_COMMUNITY_TUI Approval Widgets|TUI Approval Widgets]]
- [[_COMMUNITY_Config PiP Panel|Config PiP Panel]]
- [[_COMMUNITY_Prompt Area Input|Prompt Area Input]]
- [[_COMMUNITY_Symbol Preserve Logic|Symbol Preserve Logic]]
- [[_COMMUNITY_Runtime Schema Tests|Runtime Schema Tests]]
- [[_COMMUNITY_Python Dependencies|Python Dependencies]]
- [[_COMMUNITY_Chat History Widget|Chat History Widget]]
- [[_COMMUNITY_HTML to Text|HTML to Text]]
- [[_COMMUNITY_Safe Artifact Writes|Safe Artifact Writes]]
- [[_COMMUNITY_Context Compressor|Context Compressor]]
- [[_COMMUNITY_Pytest Fixtures|Pytest Fixtures]]
- [[_COMMUNITY_TUI Role Selectors|TUI Role Selectors]]
- [[_COMMUNITY_Tool Approval Handlers|Tool Approval Handlers]]
- [[_COMMUNITY_Help Side Panel|Help Side Panel]]
- [[_COMMUNITY_External Skills Docs|External Skills Docs]]
- [[_COMMUNITY_Graphify Agent Rules|Graphify Agent Rules]]
- [[_COMMUNITY_Architect Agent|Architect Agent]]
- [[_COMMUNITY_Tool Approval Wait|Tool Approval Wait]]
- [[_COMMUNITY_Safety Filter|Safety Filter]]
- [[_COMMUNITY_Install Launcher Script|Install Launcher Script]]
- [[_COMMUNITY_Project Metadata|Project Metadata]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 80|Community 80]]
- [[_COMMUNITY_Community 81|Community 81]]

## God Nodes (most connected - your core abstractions)
1. `ConversationSession` - 65 edges
2. `MultiAgentApp` - 55 edges
3. `DifficultyAssessment` - 47 edges
4. `QuotaTracker` - 43 edges
5. `CodeArtifact` - 40 edges
6. `TechnicalSpec` - 38 edges
7. `select_for_role()` - 34 edges
8. `ToolCall` - 33 edges
9. `transfer_control()` - 30 edges
10. `exec_tool()` - 27 edges

## Surprising Connections (you probably didn't know these)
- `Planner (/do)` --semantically_similar_to--> `cli.planner`  [INFERRED] [semantically similar]
  README.md → systems.md
- `CondensedTrends` --uses--> `CondensedTrends`  [INFERRED]
  agents/deep_research/context_compressor.py → schemas/deep_research.py
- `SafetyClassification` --uses--> `SafetyClassification`  [INFERRED]
  agents/deep_research/safety_filter.py → schemas/deep_research.py
- `TechnicalSpec` --uses--> `TechnicalSpec`  [INFERRED]
  agents/vibe_coding/architect.py → schemas/vibe_coding.py
- `test_outbound_from_json_ld_same_as()` --calls--> `extract_outbound_presence()`  [EXTRACTED]
  tests/test_source_fetch_and_scrub.py → agents/deep_research/source_fetch.py

## Import Cycles
- 1-file cycle: `core/router.py -> core/router.py`
- 1-file cycle: `core/clients.py -> core/clients.py`

## Hyperedges (group relationships)
- **System A Vibe Coding pipeline roles** — multiagent_systems_role_architect, multiagent_systems_role_coder, multiagent_systems_role_debugger, multiagent_readme_system_a_vibe_coding [EXTRACTED 1.00]
- **System B Deep Research pipeline roles** — multiagent_systems_role_safety_filter, multiagent_systems_role_context_compressor, multiagent_systems_role_web_search, multiagent_systems_role_grounding, multiagent_systems_role_synthesizer, multiagent_readme_system_b_deep_research [EXTRACTED 1.00]
- **Free-durable hot-path primary models** — multiagent_systems_model_agnes_2_0_flash, multiagent_systems_model_codestral_latest, multiagent_systems_model_gpt_oss_120b, multiagent_systems_model_compound_mini, multiagent_systems_model_command_a_plus, multiagent_systems_model_gpt_oss_safeguard_20b [EXTRACTED 1.00]

## Communities (82 total, 5 thin omitted)

### Community 0 - "CLI Session Context"
Cohesion: 0.11
Nodes (26): dispatch(), Parse a slash command line and run the handler., ConversationSession, OpenAI-style messages for the chat role (skip pure system-notes)., Last *n* user/assistant turns only (for slim graph-augmented chat).          Exc, In-memory chat session with a soft context budget., Path, Tests for interactive CLI helpers (config editor, keys, session, slash cmds). (+18 more)

### Community 1 - "Docs and Config"
Cohesion: 0.23
Nodes (15): System B anti-hallucination multi-source path, command-a-plus-05-2026, groq/compound-mini, openai/gpt-oss-120b, openai/gpt-oss-safeguard-20b, Cohere provider, Groq provider, ResearchProfile typology (+7 more)

### Community 2 - "Source Fetch Search"
Cohesion: 0.09
Nodes (44): _abs_url(), classify_outbound_url(), _clean_href(), collect_outbound_from_sources(), extract_outbound_presence(), extract_structured_signals(), extract_user_urls(), fetch_outbound_presence_pages() (+36 more)

### Community 3 - "Agent Chat Context"
Cohesion: 0.16
Nodes (22): extract_path_candidates(), gather_dir_context(), gather_file_context(), graph_mtime(), in_multiagent_project(), _is_safe_dir(), _is_safe_path(), list_project_dir() (+14 more)

### Community 4 - "Research Grounding Types"
Cohesion: 0.11
Nodes (28): Any, CondensedTrends, Context Compressor agent for System B (Deep Research).  Provider/model/fallback, Extract search terms + research profile from the research query., run_context_compressor(), classify_research(), merge_profiles(), profile_from_mapping() (+20 more)

### Community 5 - "Skills Registry CLI"
Cohesion: 0.11
Nodes (44): Manage global external skills (path + SKILL.md format)., _skills(), List registered skills (ON/off). Works from any directory., Register a skill folder (must contain valid SKILL.md)., Enable a registered skill globally., Disable a skill globally (stays registered)., Show skill metadata and body preview., skills_add() (+36 more)

### Community 6 - "Vibe Coding Graph"
Cohesion: 0.07
Nodes (48): TechnicalSpec, get_max_fix_cycles(), Return System A max debugger fix cycles from YAML (default 3)., assessments_to_state_dict(), JSON-serializable map for LangGraph state (short keys only)., _after_architect(), _after_coder(), architect_node() (+40 more)

### Community 7 - "Entity Focus Anchors"
Cohesion: 0.07
Nodes (46): ProgressCb, ResearchProfile, NoLiveSearchError, raise_if_no_live_search(), Raised when search output admits it did not perform a live search., Raise ``NoLiveSearchError`` if the result admits it wasn't a real search., entity_focus_block(), extract_entity_anchors() (+38 more)

### Community 8 - "Host Tools Terminal"
Cohesion: 0.16
Nodes (18): format_command_header(), needs_approval(), ApprovalFn, Path, Host-side tools for interactive chat (files, dirs, graphify, terminal).  The mod, Directory where multiagent was *launched* (user project).      File writes, shel, Resolve a relative path under the launch cwd (work root), not package root., Return python executable inside a venv (POSIX or Windows). (+10 more)

### Community 9 - "Main CLI Entrypoint"
Cohesion: 0.07
Nodes (40): _providers(), List free-tier providers, models, and whether keys are configured., config(), config_reset(), config_set(), keys(), keys_set(), main() (+32 more)

### Community 10 - "Pipeline Orchestration"
Cohesion: 0.10
Nodes (38): _display_step_output(), _emit(), ensure_origin_urls_in_research_prompt(), execute_plan(), _format_research_report(), Any, PipelinePlan, ProgressCb (+30 more)

### Community 11 - "Toolbox Catalog"
Cohesion: 0.05
Nodes (87): Terminal toolbox: doctor / suggest / search over the curated catalog., _tools(), exec_tool(), _looks_like_pip_or_venv(), Any, Execute a single tool; never raises — returns ToolResult., Recommend tools for a free-form task description., Search the toolbox catalog by keyword. (+79 more)

### Community 12 - "Slash Commands"
Cohesion: 0.11
Nodes (37): format_plan(), PipelinePlan, _approve_cmd(), _build_planner_context(), chat_turn(), _clear(), CommandResult, _compact() (+29 more)

### Community 13 - "Search Guards Scrub"
Cohesion: 0.09
Nodes (42): _address_lines(), _asset_urls(), extract_research_facts(), _gaps(), _hex_colors(), Extract grounded constraints from a research report for vibe-coding steps.  When, Parse a research report (+ optional source URLs) into fact buckets., _social() (+34 more)

### Community 14 - "TUI App Core"
Cohesion: 0.15
Nodes (4): HelpPiP, _invalidate_option_caches(), Update status line. Config selects only when full_config=True., F1 help side panel (not dumped into chat history).

### Community 15 - "Quota Tracker"
Cohesion: 0.10
Nodes (13): Connection, Path, Create the usage table if it doesn't exist yet., Open a connection to the quota database., ISO-formatted current date for partitioning., Determine the tracking key for a (provider, model) pair.          * **Groq** — e, Return the daily limit for *provider*.          Reads from ``config/model_router, Return today's call count for *provider*/*model*. (+5 more)

### Community 16 - "Chat Turn Tools"
Cohesion: 0.10
Nodes (11): Side panel sibling of chat — pushes main content (does not float over it)., Keep PiP within half screen when the terminal is resized., SidePanel, MouseDown, MouseMove, MouseScrollDown, MouseScrollLeft, MouseScrollRight (+3 more)

### Community 17 - "Router Fallback Tests"
Cohesion: 0.06
Nodes (24): Persistent SQLite-backed quota counters with automatic daily reset.  Limits are, custom_tracker(), Tests for ModelRouter, QuotaTracker, and fallback cascade. These tests mock HTTP, Provide an isolated QuotaTracker using a temp database., Historical bug: groq→gemini→openrouter→groq cycled when Gemini failed.      With, Provide a ModelRouter bound to the isolated QuotaTracker., groq→gemini→openrouter→groq: skip visited groq and stop cleanly if leaf gone., Test cohere routing through ClientV2 mock/interceptor. (+16 more)

### Community 18 - "Deep Research Graph"
Cohesion: 0.06
Nodes (56): Any, GroundedReport, ResearchProfile, GroundedReport, ResearchProfile, find_no_live_search_marker(), Return the first matching marker in *text*, or None if clean., _extract_sources_from_citations() (+48 more)

### Community 19 - "Coder Preserve Files"
Cohesion: 0.11
Nodes (28): CodeArtifact, TechnicalSpec, Path, coder_node(), Pydantic schemas for the System A (Vibe Coding) pipeline. These models define th, Output schema for the Architect agent.      Defines the system design, component, TechnicalSpec, Path (+20 more)

### Community 20 - "Model Router"
Cohesion: 0.15
Nodes (26): CodeArtifact, Path, TechnicalSpec, CodeArtifact, Output schema for the Coder agent.      Contains the written source code mapped, Path, Vibe test runner: scoped pytest targets + static grounded checks., test_node_project_fails_execute_vibe_tests() (+18 more)

### Community 21 - "Research Run History"
Cohesion: 0.12
Nodes (19): call_agent(), EmptyCompletionError, get_router(), ModelRouter, Any, ClientV2, OpenAI, Path (+11 more)

### Community 22 - "LLM Clients"
Cohesion: 0.17
Nodes (18): get_client(), get_cohere_client(), get_groq_client(), get_openrouter_client(), list_ollama_local_models(), _normalize_openai_base_url(), _ollama_base_url(), _openai_compat_client() (+10 more)

### Community 23 - "Web Search Agent"
Cohesion: 0.13
Nodes (18): CodeArtifact, DebugReport, _debugger_next_agent(), debugger_node(), DebugReport, Mirror ``debugger_routing`` so the handoff names the real next hop., Runs the Debugger agent to assess test logs and propose fixes.      Always incre, DebugReport (+10 more)

### Community 24 - "Config Editor"
Cohesion: 0.18
Nodes (24): _config(), config_show(), Print active provider/model per agent role., ensure_defaults_snapshot(), get_cli_settings(), list_roles(), Any, Path (+16 more)

### Community 25 - "Research Pipeline Tests"
Cohesion: 0.11
Nodes (32): invoke_router(), Any, date, DifficultyAssessment, Shared runtime helpers for every agent role.  Eliminates the 8-way copy of: load, Return (provider, model, fallback, selection, assessment) for a role call., Load role config, pick model by difficulty, apply reasoning, call LLM.      Exam, Like ``run_structured_agent`` but returns the raw ``LLMResponse`` (prose paths). (+24 more)

### Community 26 - "Architect Spec Schema"
Cohesion: 0.12
Nodes (24): keys_status(), Show which provider keys are set (masked)., _isolate_clients(), Path, Root conftest — sets up fake API keys so that imports of core.clients don't rais, Clear cached LLM clients between tests to avoid cross-contamination., Provide a temporary SQLite path for QuotaTracker in tests., tmp_quota_db() (+16 more)

### Community 27 - "Graphify RAG"
Cohesion: 0.18
Nodes (11): Any, Connection, Path, Mark a run as completed / failed / aborted., Return newest runs first., Thread-safe log of MAS pipeline executions., Insert a running row; return its id., RunHistory (+3 more)

### Community 28 - "Debugger Rollback Tests"
Cohesion: 0.16
Nodes (17): get_vibe_coding_graph(), initial_vibe_coding_state(), Build a fresh graph state for System A., Build and compile the StateGraph for System A., StateGraph, Path, Tests for LangGraph orchestration. Includes testing the Git rollback behavior fo, Debugger LLM failures must still increment fix_attempts and end the graph. (+9 more)

### Community 29 - "TUI Launch Init"
Cohesion: 0.15
Nodes (15): Interactive Free-Multi-Agent CLI (slash commands + session context)., run_tui(), _known_provider_options(), _planner_options(), _provider_options(), _quiet_logging_for_tui(), MultiAgent TUI — chat + side config/help panels that push the main column.  - En, Stop router/HTTP retry noise from painting over the prompt bar.      ``cli.py`` (+7 more)

### Community 30 - "Research Constraints"
Cohesion: 0.10
Nodes (46): _expired_fallback_for(), get_model_entry(), get_model_scores(), hy3_status(), is_model_available(), _is_primary_degraded(), _load_benchmarks(), _mis_specialization_reasons() (+38 more)

### Community 31 - "Toolbox Runtime Resolve"
Cohesion: 0.14
Nodes (30): _clamp_effort(), difficulty_to_effort(), _effort_rank(), get_model_reasoning_capability(), _load_benchmarks(), _map_effort_for_style(), Any, DifficultyAssessment (+22 more)

### Community 32 - "Agent Config Loader"
Cohesion: 0.18
Nodes (14): plan_pipelines(), Planner agent: given a free-form user prompt, choose System A (/vibe), System B, Ask the planner model for a PipelinePlan.      If *provider*/*model* are set, th, check_hy3_expiration(), Warn if tencent/hy3:free is near or past free_until.      Uses ``config/model_be, get_agent_config(), get_full_config(), _load() (+6 more)

### Community 33 - "TUI Approval Widgets"
Cohesion: 0.20
Nodes (8): ApprovalBar, Compact vertical list: bold header + three bordered, centered option rows., StatusLine, ComposeResult, Horizontal, Static, Vertical, VerticalScroll

### Community 34 - "Config PiP Panel"
Cohesion: 0.38
Nodes (3): _planner_label(), ConversationSession, _short_cwd()

### Community 35 - "Prompt Area Input"
Cohesion: 0.18
Nodes (4): PromptArea, Multi-line prompt: Enter = send, Shift+Enter = newline., Key, TextArea

### Community 36 - "Symbol Preserve Logic"
Cohesion: 0.13
Nodes (24): agent_chat_turn(), _clean_final(), _modern_toolbox_block(), Any, ApprovalFn, ConversationSession, Tool-using chat loop for the interactive CLI.  The host fetches graph/dir seeds,, Run a tool-augmented chat turn. (+16 more)

### Community 37 - "Runtime Schema Tests"
Cohesion: 0.10
Nodes (25): Force the next ``get_agent_config`` call to re-read the YAML from disk.      Use, reload_config(), Remove optional markdown code fences around model JSON/text output., strip_fences(), Clear benchmarks cache (tests / live YAML edit)., reload_benchmarks(), Clear local + model_selector benchmarks caches after YAML edits., reload_reasoning_config() (+17 more)

### Community 38 - "Python Dependencies"
Cohesion: 0.17
Nodes (11): click>=8.1.0, cohere>=5.0.0, gitpython>=3.1.0, langgraph>=0.4.0, langgraph-checkpoint-sqlite>=2.0.0, mcp>=1.0.0, openai>=1.30.0, pydantic>=2.7.0 (+3 more)

### Community 39 - "Chat History Widget"
Cohesion: 0.15
Nodes (6): ChatHistory, Restore factory defaults: one role if selected, else all roles., Progress line from the agent loop (called via call_from_thread)., Scrollable chat: Markdown for assistant, fenced code block for user prompts., User prompt as a markdown fenced block (``` ... ```)., Assistant reply as rendered markdown (no role label).

### Community 40 - "HTML to Text"
Cohesion: 0.22
Nodes (5): html_to_text(), _HTMLToText, Minimal HTML → visible text (scripts/styles dropped)., HTMLParser, test_html_to_text_strips_scripts()

### Community 41 - "Safe Artifact Writes"
Cohesion: 0.24
Nodes (10): _apply_preservation_warnings(), CodeArtifact, Path, Raised when the Coder agent tries to write outside the repo root or     to a pat, Resolve `file_path` against `repo_root` and ensure it can't escape it.      Reje, Validate and write every file in `artifact.files` atomically.      All paths are, Log (and note in summary) if the Coder dropped top-level symbols from existing f, UnsafeFilePathError (+2 more)

### Community 42 - "Context Compressor"
Cohesion: 0.17
Nodes (22): _coerce_history(), extract_user_input(), HandoffError, _present_keys(), Any, PipelineName, Central handoff API for LangGraph agent nodes.  ``transfer_control`` is the **on, Build a LangGraph state patch that records a formal agent handoff.      Paramete (+14 more)

### Community 43 - "Pytest Fixtures"
Cohesion: 0.18
Nodes (24): BucketDemand, build_system_estimate(), estimate_all(), format_quota_report(), _limit_and_usage(), _load_benchmarks(), pipeline_role_calls(), _provider_limit() (+16 more)

### Community 44 - "TUI Role Selectors"
Cohesion: 0.22
Nodes (6): Changed, ConfigPiP, _models_for_provider(), Full-height side panel; each tab is one scroll (no nested height fight)., True when a Textual :class:`Select` has no real option chosen.      Textual ≥0.x, _select_unset()

### Community 45 - "Tool Approval Handlers"
Cohesion: 0.18
Nodes (5): MultiAgentApp, Grow input-row with content; skip no-op height changes., Called from PromptArea (Enter)., Chat shell with optional side panel that pushes the main column., Click

### Community 46 - "Help Side Panel"
Cohesion: 0.13
Nodes (19): assessment_from_state(), _clip(), DifficultyAssessment, _length_base(), plan_pipeline_difficulties(), Any, Task difficulty scoring (0–100) aligned with systems.md / model_benchmarks.yaml., Heuristic 0–100 assessment (no LLM). Suitable for planners and tests. (+11 more)

### Community 47 - "External Skills Docs"
Cohesion: 0.25
Nodes (8): CLI, Format, Global registry, MultiAgent skills, Runtime behaviour, Skill body injection into chat system prompt, SKILL.md format, Skills (policy/workflow) vs Graphify (codebase facts)

### Community 48 - "Graphify Agent Rules"
Cohesion: 0.50
Nodes (4): graphify Knowledge Graph (graphify-out/), graphify query / query_graph, graphify update (AST-only refresh), graphify Workflow

### Community 49 - "Architect Agent"
Cohesion: 0.14
Nodes (8): estimate_tokens(), Message, Multi-turn conversation context for the interactive CLI.  Tracks messages, estim, Auto-run local compact when usage exceeds *threshold*., Drop middle turns, keep system + recent messages (no LLM).          Returns a hu, Summarize older turns via LLM, keep recent messages intact., Cheap token estimate without tiktoken (≈ 4 chars/token)., test_estimate_tokens_positive()

### Community 51 - "Safety Filter"
Cohesion: 0.23
Nodes (17): Map a role to provider/model for ``primary`` or ``fallback`` scenario., resolve_role_endpoint(), _minimal_router(), Path, Tests for live System A/B quota capacity estimates (no real HTTP)., (a) Exhausting a required provider bucket → 0 complete runs., (b) Swapping primary model in YAML changes which bucket is charged., (c) Planner fallback mode bills fallback endpoints for roles that have them. (+9 more)

### Community 61 - "Community 61"
Cohesion: 0.12
Nodes (16): Agent handoffs, Default roles (free-durable), Free-durable keys (defaults), Free-Multi-Agent, Model selection, difficulty & reasoning, Notes, Pipelines, Planner (`/do`) (+8 more)

### Community 62 - "Community 62"
Cohesion: 0.15
Nodes (13): 0. Live role inventory (primary + fallback), 10. Anti-patterns deliberately avoided, 11. Optional profiles (not default), 12. Key checklist for free-durable defaults, 13. Source map (research), 1. Design goals, 2. Calls per pipeline (budget math), 5. System A — Vibe Coding (role assignments) (+5 more)

### Community 63 - "Community 63"
Cohesion: 0.21
Nodes (12): config/cli_toolbox.yaml, Toolbox profile: core, bat (toolbox), eza (toolbox), fd (toolbox), ripgrep (toolbox), core/toolbox.py, Runtime CLI soft-upgrade (+4 more)

### Community 64 - "Community 64"
Cohesion: 0.24
Nodes (9): build_graph_augmented_messages(), _local_fallback(), query_graph(), Graph-backed retrieval for the interactive chat.  Queries ``graphify-out/graph.j, Compose a **small** message list for the chat model.      - Does not include the, Return a compact graph traversal for *question*.      Prefers ``graphify query …, Keyword hit list from GRAPH_REPORT + graph.json when CLI is unavailable., _trim() (+1 more)

### Community 65 - "Community 65"
Cohesion: 0.27
Nodes (10): CLI context settings, Graphify context integration, Chat host tools, Interactive TUI (multiagent), Planner (/do), agnes-2.0-flash, Agnes AI provider, vibe_coding.architect (+2 more)

### Community 66 - "Community 66"
Cohesion: 0.27
Nodes (10): max_fix_cycles, core/router.py, Fallback cascade DAG, codestral-latest, Cerebras provider, Gemini (Google AI Studio) provider, Mistral provider, vibe_coding.coder (+2 more)

### Community 67 - "Community 67"
Cohesion: 0.22
Nodes (9): 1. What existed before, 3. Control flow diagrams, 4. Swarm analogy, 5. Failure modes, 6. Model selection handoffs, 7. Extending the protocol, Agent handoff protocol, System A — Vibe Coding (+1 more)

### Community 68 - "Community 68"
Cohesion: 0.22
Nodes (9): 3.1 Groq, 3.2 Agnes AI, 3.3 Mistral (La Plateforme Experiment), 3.4 Google AI Studio (Gemini), 3.5 Cohere (Trial), 3.6 Cerebras Inference, 3.7 OpenRouter (`:free` models), 3.8 Ollama (local) (+1 more)

### Community 69 - "Community 69"
Cohesion: 0.33
Nodes (7): Free-tier anti-patterns, Free-tier design goals, Free-durable profile, One scarce bucket = one critical role, Optional orchestration profiles, Ollama local provider, OpenRouter provider

### Community 70 - "Community 70"
Cohesion: 0.33
Nodes (5): BaseModel, HandoffEnvelope, Any, PipelineName, Optional structured view of the full transfer history for a run.      Graph stat

### Community 71 - "Community 71"
Cohesion: 0.40
Nodes (6): looks_non_english(), Any, Cheap check — not a full language detector., Return English text suitable for Systems A/B.      If the text already looks Eng, to_english_for_pipelines(), test_language_helpers()

### Community 72 - "Community 72"
Cohesion: 0.33
Nodes (6): _print_quota_capacity_report(), _print_quota_summary(), Legacy one-liner usage dump (still used by brief TUI preflight)., Full System A/B capacity estimate (primary vs fallback scenarios)., Show today's quota usage and estimated full System A/B runs left.      Reads liv, show_quota()

### Community 73 - "Community 73"
Cohesion: 0.40
Nodes (6): config/defaults_model_router.yaml (factory), config/model_router.yaml (live), core/agent_config.py, core/quotas.py, Systems orchestration document, Soft quotas vs real limits

### Community 74 - "Community 74"
Cohesion: 0.33
Nodes (6): 4.1 Rubric definition (0–100 per area), 4.2 Benchmark scores by model × area, 4.3 Recomendación primario vs fallback por rol, 4.4 Cómo se elige y se usa el modelo en un run (end-to-end), 4. Scoring rubric and model benchmarks (0–100), Critical quota fact (calls ≠ tokens)

### Community 75 - "Community 75"
Cohesion: 0.33
Nodes (6): 4.5 Reasoning / thinking effort (same call, no extra RPD), Cascade safety, Difficulty → abstract effort bands, Provider-native kwargs (only capable models), What is **not** thinking mode, When to raise effort vs when to change model

### Community 76 - "Community 76"
Cohesion: 0.40
Nodes (5): Chat (tool-using agent), Interactive TUI, Keys & chrome, Outer CLI, Slash commands (inside TUI)

### Community 77 - "Community 77"
Cohesion: 0.50
Nodes (4): extract_primary_ok_blocks(), Return ``(url, body)`` pairs for successful host PRIMARY fetches., When PRIMARY OK succeeded, report must not end as Sources: [] / not found., test_merge_host_verified_primary_fixes_empty_denial()

### Community 78 - "Community 78"
Cohesion: 0.50
Nodes (4): 2.1 `HandoffRecord` (one transfer), 2.2 Graph state field, 2.3 Official API: `transfer_control`, 2. Formal handoff model

## Knowledge Gaps
- **99 isolated node(s):** `Any`, `install-launcher.sh script`, `Context`, `Any`, `Any` (+94 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ConversationSession` connect `CLI Session Context` to `TUI Approval Widgets`, `Config PiP Panel`, `Prompt Area Input`, `Symbol Preserve Logic`, `Skills Registry CLI`, `Chat History Widget`, `Toolbox Catalog`, `TUI Role Selectors`, `Slash Commands`, `TUI App Core`, `Tool Approval Handlers`, `Chat Turn Tools`, `Architect Agent`, `Tool Approval Wait`, `TUI Launch Init`?**
  _High betweenness centrality (0.061) - this node is a cross-community bridge._
- **Why does `get_agent_config()` connect `Agent Config Loader` to `Vibe Coding Graph`, `Main CLI Entrypoint`, `Pytest Fixtures`, `Slash Commands`, `Quota Tracker`, `Router Fallback Tests`, `Deep Research Graph`, `Safety Filter`, `Research Pipeline Tests`, `Research Constraints`?**
  _High betweenness centrality (0.037) - this node is a cross-community bridge._
- **Why does `is_plausible_source_url()` connect `Deep Research Graph` to `Source Fetch Search`, `Search Guards Scrub`?**
  _High betweenness centrality (0.035) - this node is a cross-community bridge._
- **Are the 30 inferred relationships involving `ConversationSession` (e.g. with `Changed` and `Any`) actually correct?**
  _`ConversationSession` has 30 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `MultiAgentApp` (e.g. with `ConversationSession` and `ToolCall`) actually correct?**
  _`MultiAgentApp` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 18 inferred relationships involving `DifficultyAssessment` (e.g. with `Any` and `date`) actually correct?**
  _`DifficultyAssessment` has 18 INFERRED edges - model-reasoned connections that need verification._
- **Are the 16 inferred relationships involving `QuotaTracker` (e.g. with `BucketDemand` and `Any`) actually correct?**
  _`QuotaTracker` has 16 INFERRED edges - model-reasoned connections that need verification._