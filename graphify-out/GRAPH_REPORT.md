# Graph Report - MultiAgent  (2026-07-18)

## Corpus Check
- 89 files · ~91,376 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1612 nodes · 3928 edges · 87 communities (81 shown, 6 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 240 edges (avg confidence: 0.53)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `4461a333`
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
- [[_COMMUNITY_Community 79|Community 79]]
- [[_COMMUNITY_Community 80|Community 80]]
- [[_COMMUNITY_Community 81|Community 81]]
- [[_COMMUNITY_Community 82|Community 82]]
- [[_COMMUNITY_Community 83|Community 83]]
- [[_COMMUNITY_Community 84|Community 84]]
- [[_COMMUNITY_Community 85|Community 85]]
- [[_COMMUNITY_Community 86|Community 86]]

## God Nodes (most connected - your core abstractions)
1. `ConversationSession` - 65 edges
2. `MultiAgentApp` - 55 edges
3. `DifficultyAssessment` - 47 edges
4. `CodeArtifact` - 44 edges
5. `QuotaTracker` - 43 edges
6. `TechnicalSpec` - 39 edges
7. `select_for_role()` - 34 edges
8. `ToolCall` - 33 edges
9. `transfer_control()` - 30 edges
10. `exec_tool()` - 27 edges

## Surprising Connections (you probably didn't know these)
- `CondensedTrends` --uses--> `CondensedTrends`  [INFERRED]
  agents/deep_research/context_compressor.py → schemas/deep_research.py
- `Planner (/do)` --semantically_similar_to--> `cli.planner`  [INFERRED] [semantically similar]
  README.md → systems.md
- `SafetyClassification` --uses--> `SafetyClassification`  [INFERRED]
  agents/deep_research/safety_filter.py → schemas/deep_research.py
- `TechnicalSpec` --uses--> `TechnicalSpec`  [INFERRED]
  agents/vibe_coding/architect.py → schemas/vibe_coding.py
- `TechnicalSpec` --uses--> `CodeArtifact`  [INFERRED]
  agents/vibe_coding/coder.py → schemas/vibe_coding.py

## Import Cycles
- 1-file cycle: `core/router.py -> core/router.py`
- 1-file cycle: `core/clients.py -> core/clients.py`

## Hyperedges (group relationships)
- **System A Vibe Coding pipeline roles** — multiagent_systems_role_architect, multiagent_systems_role_coder, multiagent_systems_role_debugger, multiagent_readme_system_a_vibe_coding [EXTRACTED 1.00]
- **System B Deep Research pipeline roles** — multiagent_systems_role_safety_filter, multiagent_systems_role_context_compressor, multiagent_systems_role_web_search, multiagent_systems_role_grounding, multiagent_systems_role_synthesizer, multiagent_readme_system_b_deep_research [EXTRACTED 1.00]
- **Free-durable hot-path primary models** — multiagent_systems_model_agnes_2_0_flash, multiagent_systems_model_codestral_latest, multiagent_systems_model_gpt_oss_120b, multiagent_systems_model_compound_mini, multiagent_systems_model_command_a_plus, multiagent_systems_model_gpt_oss_safeguard_20b [EXTRACTED 1.00]

## Communities (87 total, 6 thin omitted)

### Community 0 - "CLI Session Context"
Cohesion: 0.06
Nodes (40): dispatch(), Parse a slash command line and run the handler., build_graph_augmented_messages(), Compose a **small** message list for the chat model.      - Does not include the, ConversationSession, estimate_tokens(), Message, Multi-turn conversation context for the interactive CLI.  Tracks messages, estim (+32 more)

### Community 1 - "Docs and Config"
Cohesion: 0.33
Nodes (9): System B anti-hallucination multi-source path, groq/compound-mini, openai/gpt-oss-120b, openai/gpt-oss-safeguard-20b, Groq provider, vibe_coding.debugger, deep_research.safety_filter, deep_research.synthesizer (+1 more)

### Community 2 - "Source Fetch Search"
Cohesion: 0.12
Nodes (29): _abs_url(), classify_outbound_url(), _clean_href(), collect_outbound_from_sources(), extract_outbound_presence(), extract_structured_signals(), fetch_url(), FetchedSource (+21 more)

### Community 3 - "Agent Chat Context"
Cohesion: 0.07
Nodes (51): _clean_final(), _modern_toolbox_block(), Tool-using chat loop for the interactive CLI.  The host fetches graph/dir seeds,, Cheap host-side context so the model need not invent graphify CLI., Installed catalog capabilities so the model prefers modern CLIs., _seed_context(), _system_prompt(), _build_planner_context() (+43 more)

### Community 4 - "Research Grounding Types"
Cohesion: 0.13
Nodes (22): Any, CondensedTrends, Context Compressor agent for System B (Deep Research).  Provider/model/fallback, Extract search terms + research profile from the research query., run_context_compressor(), classify_research(), merge_profiles(), profile_from_mapping() (+14 more)

### Community 5 - "Skills Registry CLI"
Cohesion: 0.09
Nodes (58): Manage global external skills (path + SKILL.md format)., _skills(), List registered skills (ON/off). Works from any directory., Register a skill folder (must contain valid SKILL.md). Off by default., Enable a registered skill globally., Disable a skill globally (stays registered)., Unregister a skill (does not delete files)., Show skill metadata and body preview. (+50 more)

### Community 6 - "Vibe Coding Graph"
Cohesion: 0.10
Nodes (37): get_max_fix_cycles(), Return System A max debugger fix cycles from YAML (default 3)., _after_architect(), _after_coder(), architect_node(), debugger_routing(), get_git_repo(), git_commit_node() (+29 more)

### Community 7 - "Entity Focus Anchors"
Cohesion: 0.10
Nodes (31): entity_focus_block(), extract_entity_anchors(), extract_location_phrases(), extract_name_variants(), merge_search_terms(), Entity anchoring helpers for System B (Deep Research).  Keeps research tied to t, Pull likely subject-name variants from a free-text research topic., Build high-precision search strings anchored on the research subject. (+23 more)

### Community 8 - "Host Tools Terminal"
Cohesion: 0.17
Nodes (18): format_tool_results(), _looks_like_pip_or_venv(), needs_approval(), ApprovalFn, Path, Host-side tools for interactive chat (files, dirs, graphify, terminal).  The mod, Directory where multiagent was *launched* (user project).      File writes, shel, Resolve a relative path under the launch cwd (work root), not package root. (+10 more)

### Community 9 - "Main CLI Entrypoint"
Cohesion: 0.05
Nodes (47): chat_cmd(), config(), config_reset(), config_set(), keys(), keys_status(), main(), _print_quota_capacity_report() (+39 more)

### Community 10 - "Pipeline Orchestration"
Cohesion: 0.07
Nodes (50): format_plan(), PipelinePlan, Planner agent: given a free-form user prompt, choose System A (/vibe), System B, _display_step_output(), _emit(), ensure_origin_urls_in_research_prompt(), execute_plan(), _format_research_report() (+42 more)

### Community 11 - "Toolbox Catalog"
Cohesion: 0.12
Nodes (31): Terminal toolbox: doctor / suggest / search over the curated catalog., _tools(), alternatives(), Catalog, doctor(), format_install_hint(), get_catalog(), help_text() (+23 more)

### Community 12 - "Slash Commands"
Cohesion: 0.17
Nodes (26): _approve_cmd(), chat_turn(), _clear(), CommandResult, _compact(), _do(), _exit(), _graphify() (+18 more)

### Community 13 - "Search Guards Scrub"
Cohesion: 0.13
Nodes (25): _corpus_contains(), extract_emails(), extract_url_set(), normalize_source_url(), Shared guards for live web-search verification and URL extraction.  Single sourc, Lowercased, slash-stripped URL set for cross-referencing citations., Lowercase, strip trailing slash/punctuation for comparison., True only if *source* matches a URL that actually appears in *corpus*.      Prev (+17 more)

### Community 14 - "TUI App Core"
Cohesion: 0.12
Nodes (27): Any, GroundedReport, ResearchProfile, GroundedReport, ResearchProfile, _extract_sources_from_citations(), Grounding agent for System B (Deep Research).  Plain cited prose from the model;, Ground the query against search_results; return prose + sources. (+19 more)

### Community 15 - "Quota Tracker"
Cohesion: 0.12
Nodes (15): Connection, Path, QuotaTracker, Create the usage table if it doesn't exist yet., Open a connection to the quota database., ISO-formatted current date for partitioning., Determine the tracking key for a (provider, model) pair.          * **Groq** — e, Return the daily limit for *provider*.          Reads from ``config/model_router (+7 more)

### Community 16 - "Chat Turn Tools"
Cohesion: 0.09
Nodes (22): agent_chat_turn(), Any, ApprovalFn, ConversationSession, Run a tool-augmented chat turn., Run local graphify update; return status text for the user., _try_graphify_update(), _wants_graph_refresh() (+14 more)

### Community 17 - "Router Fallback Tests"
Cohesion: 0.07
Nodes (23): custom_tracker(), Tests for ModelRouter, QuotaTracker, and fallback cascade. These tests mock HTTP, Provide an isolated QuotaTracker using a temp database., Historical bug: groq→gemini→openrouter→groq cycled when Gemini failed.      With, Provide a ModelRouter bound to the isolated QuotaTracker., groq→gemini→openrouter→groq: skip visited groq and stop cleanly if leaf gone., Test cohere routing through ClientV2 mock/interceptor., Verify that OpenRouter uses a single SHARED counter for all :free models.      C (+15 more)

### Community 18 - "Deep Research Graph"
Cohesion: 0.12
Nodes (27): context_compressor_node(), DeepResearchState, get_deep_research_graph(), grounding_node(), initial_deep_research_state(), invoke_deep_research_pipeline(), Any, LangGraph orchestration for the System B (Deep Research) pipeline. Orchestrates: (+19 more)

### Community 19 - "Coder Preserve Files"
Cohesion: 0.12
Nodes (23): CodeArtifact, TechnicalSpec, Path, Path, Tests for existing-source preservation helpers and coder merge wiring., Integration-ish: coder_node reads disk before run_coder., test_coder_node_loads_disk_and_calls_run_coder(), test_extract_and_missing_symbols() (+15 more)

### Community 20 - "Model Router"
Cohesion: 0.09
Nodes (41): CodeArtifact, Path, TechnicalSpec, CodeArtifact, CodeArtifact, Output schema for the Coder agent.      Contains the written source code mapped, Path, Vibe test runner: scoped pytest targets + static grounded checks. (+33 more)

### Community 21 - "Research Run History"
Cohesion: 0.13
Nodes (15): EmptyCompletionError, ModelRouter, Any, ClientV2, OpenAI, Path, QuotaTracker, QuotaExhaustedError (+7 more)

### Community 22 - "LLM Clients"
Cohesion: 0.10
Nodes (33): _providers(), List free-tier providers, models, and whether keys are configured., _models_for_provider(), _planner_options(), providers_cmd(), List free-tier-friendly providers, signup URLs, models, and key status., get_client(), get_cohere_client() (+25 more)

### Community 23 - "Web Search Agent"
Cohesion: 0.22
Nodes (12): CodeArtifact, DebugReport, _debugger_next_agent(), debugger_node(), DebugReport, Mirror ``debugger_routing`` so the handoff names the real next hop., Runs the Debugger agent to assess test logs and propose fixes.      Always incre, DebugReport (+4 more)

### Community 24 - "Config Editor"
Cohesion: 0.16
Nodes (27): _config(), _session_info_text(), config_show(), Print active provider/model per agent role., Force the next ``get_agent_config`` call to re-read the YAML from disk.      Use, reload_config(), ensure_defaults_snapshot(), get_cli_settings() (+19 more)

### Community 25 - "Research Pipeline Tests"
Cohesion: 0.13
Nodes (32): plan_pipelines(), Ask the planner model for a PipelinePlan.      If *provider*/*model* are set, th, check_hy3_expiration(), Warn if tencent/hy3:free is near or past free_until.      Uses ``config/model_be, get_agent_config(), Fetch a nested agent role config by dot-path.      Example::          get_agent_, invoke_router(), Any (+24 more)

### Community 26 - "Architect Spec Schema"
Cohesion: 0.19
Nodes (18): keys_set(), Write a provider API key to .env., clear_client_cache(), Clear all cached clients. Mainly useful for testing / key rotation., env_path(), get_key_status(), _is_placeholder(), mask_key() (+10 more)

### Community 27 - "Graphify RAG"
Cohesion: 0.18
Nodes (11): Any, Connection, Path, Mark a run as completed / failed / aborted., Return newest runs first., Thread-safe log of MAS pipeline executions., Insert a running row; return its id., RunHistory (+3 more)

### Community 28 - "Debugger Rollback Tests"
Cohesion: 0.13
Nodes (22): TechnicalSpec, get_vibe_coding_graph(), initial_vibe_coding_state(), Build a fresh graph state for System A., Build and compile the StateGraph for System A., Pydantic schemas for the System A (Vibe Coding) pipeline. These models define th, Output schema for the Architect agent.      Defines the system design, component, TechnicalSpec (+14 more)

### Community 29 - "TUI Launch Init"
Cohesion: 0.21
Nodes (11): Interactive Free-Multi-Agent CLI (slash commands + session context)., run_tui(), _invalidate_option_caches(), _known_provider_options(), _provider_options(), _quiet_logging_for_tui(), MultiAgent TUI — chat + side config/help panels that push the main column.  - En, Stop router/HTTP retry noise from painting over the prompt bar.      ``cli.py`` (+3 more)

### Community 30 - "Research Constraints"
Cohesion: 0.16
Nodes (29): _expired_fallback_for(), get_model_entry(), get_model_scores(), hy3_status(), is_model_available(), _is_primary_degraded(), _load_benchmarks(), _mis_specialization_reasons() (+21 more)

### Community 31 - "Toolbox Runtime Resolve"
Cohesion: 0.12
Nodes (34): model_key(), _clamp_effort(), difficulty_to_effort(), _effort_rank(), get_model_reasoning_capability(), _load_benchmarks(), _map_effort_for_style(), Any (+26 more)

### Community 32 - "Agent Config Loader"
Cohesion: 0.24
Nodes (8): get_full_config(), _load(), Any, Path, Central loader for per-agent provider/model assignments.  ``config/model_router., Load (and cache) the full YAML config.      A custom ``config_path`` bypasses th, Return the entire cached ``model_router.yaml`` document., Persistent SQLite-backed quota counters with automatic daily reset.  Limits are

### Community 33 - "TUI Approval Widgets"
Cohesion: 0.22
Nodes (8): ApprovalBar, Compact vertical list: bold header + three bordered, centered option rows., StatusLine, ComposeResult, Horizontal, Static, Vertical, VerticalScroll

### Community 34 - "Config PiP Panel"
Cohesion: 0.32
Nodes (3): _planner_label(), ConversationSession, _short_cwd()

### Community 35 - "Prompt Area Input"
Cohesion: 0.10
Nodes (7): HelpPiP, PromptArea, Grow input-row with content; skip no-op height changes., Multi-line prompt: Enter = send, Shift+Enter = newline., F1 help side panel (not dumped into chat history)., Key, TextArea

### Community 36 - "Symbol Preserve Logic"
Cohesion: 0.11
Nodes (22): Safety Filter agent for System B (Deep Research).  Provider/model from config/mo, Classify whether the research query is safe to process., run_safety_filter(), SafetyClassification, CondensedTrends, Pydantic schemas for the System B (Deep Research) pipeline. These models define, Output schema for the Safety Filter agent.      Determines if the research topic, Output schema for the Context Compressor agent.      Search terms plus an option (+14 more)

### Community 37 - "Runtime Schema Tests"
Cohesion: 0.19
Nodes (21): _address_lines(), _asset_urls(), extract_research_facts(), format_grounded_constraints_block(), _gaps(), _hex_colors(), Extract grounded constraints from a research report for vibe-coding steps.  When, Parse a research report (+ optional source URLs) into fact buckets. (+13 more)

### Community 38 - "Python Dependencies"
Cohesion: 0.17
Nodes (11): click>=8.1.0, cohere>=5.0.0, gitpython>=3.1.0, langgraph>=0.4.0, langgraph-checkpoint-sqlite>=2.0.0, mcp>=1.0.0, openai>=1.30.0, pydantic>=2.7.0 (+3 more)

### Community 39 - "Chat History Widget"
Cohesion: 0.24
Nodes (4): ChatHistory, Scrollable chat: Markdown for assistant, fenced code block for user prompts., User prompt as a markdown fenced block (``` ... ```)., Assistant reply as rendered markdown (no role label).

### Community 40 - "HTML to Text"
Cohesion: 0.22
Nodes (5): html_to_text(), _HTMLToText, Minimal HTML → visible text (scripts/styles dropped)., HTMLParser, test_html_to_text_strips_scripts()

### Community 41 - "Safe Artifact Writes"
Cohesion: 0.17
Nodes (16): _apply_preservation_warnings(), coder_node(), CodeArtifact, Path, Raised when the Coder agent tries to write outside the repo root or     to a pat, Return the repo root to constrain writes to, falling back to cwd., Resolve `file_path` against `repo_root` and ensure it can't escape it.      Reje, Validate and write every file in `artifact.files` atomically.      All paths are (+8 more)

### Community 42 - "Context Compressor"
Cohesion: 0.17
Nodes (22): _coerce_history(), extract_user_input(), HandoffError, _present_keys(), Any, PipelineName, Central handoff API for LangGraph agent nodes.  ``transfer_control`` is the **on, Build a LangGraph state patch that records a formal agent handoff.      Paramete (+14 more)

### Community 43 - "Pytest Fixtures"
Cohesion: 0.14
Nodes (27): Clear benchmarks cache (tests / live YAML edit)., reload_benchmarks(), BucketDemand, build_system_estimate(), estimate_all(), format_quota_report(), _limit_and_usage(), _load_benchmarks() (+19 more)

### Community 44 - "TUI Role Selectors"
Cohesion: 0.14
Nodes (8): Changed, ConfigPiP, Restore factory defaults: one role if selected, else all roles., Progress line from the agent loop (called via call_from_thread)., Full-height side panel; each tab is one scroll (no nested height fight)., Cheap path: update ctx line without rebuilding selects., True when a Textual :class:`Select` has no real option chosen.      Textual ≥0.x, _select_unset()

### Community 45 - "Tool Approval Handlers"
Cohesion: 0.16
Nodes (5): MultiAgentApp, Update status line. Config selects only when full_config=True., Called from PromptArea (Enter)., Chat shell with optional side panel that pushes the main column., Click

### Community 46 - "Help Side Panel"
Cohesion: 0.12
Nodes (23): assessment_from_state(), assessments_to_state_dict(), _clip(), _length_base(), plan_pipeline_difficulties(), Any, Task difficulty scoring (0–100) aligned with systems.md / model_benchmarks.yaml., Heuristic 0–100 assessment (no LLM). Suitable for planners and tests. (+15 more)

### Community 47 - "External Skills Docs"
Cohesion: 0.22
Nodes (9): CLI, Format, Global registry, MultiAgent skills, Optional frontmatter for pipeline skills, Runtime behaviour, Skill body injection into chat system prompt, SKILL.md format (+1 more)

### Community 48 - "Graphify Agent Rules"
Cohesion: 0.50
Nodes (4): graphify Knowledge Graph (graphify-out/), graphify query / query_graph, graphify update (AST-only refresh), graphify Workflow

### Community 49 - "Architect Agent"
Cohesion: 0.12
Nodes (18): DifficultyAssessment, Structured difficulty scores for one subtask / role.      Area fields mirror the, PipelineName, Record primary→fallback (or expiry) model switch via ``transfer_control``., record_model_selection_handoff(), Path, Safeguard-as-coder (code 35) vs Agnes (code 78): Δ≥8 and weak primary → fallback, Gemini reason 78 > Agnes 76 (Δ=2 < 8). Healthy + mid difficulty → keep Agnes. (+10 more)

### Community 50 - "Tool Approval Wait"
Cohesion: 0.33
Nodes (4): format_command_header(), Human-readable one-line command for approval UI header., Block worker thread until the user decides (UI thread)., ToolCall

### Community 51 - "Safety Filter"
Cohesion: 0.24
Nodes (16): _minimal_router(), Path, Tests for live System A/B quota capacity estimates (no real HTTP)., (a) Exhausting a required provider bucket → 0 complete runs., (b) Swapping primary model in YAML changes which bucket is charged., (c) Planner fallback mode bills fallback endpoints for roles that have them., Fallback scenario can reduce remaining runs vs primary when scarce bucket piles, test_changing_primary_yaml_changes_demand() (+8 more)

### Community 61 - "Community 61"
Cohesion: 0.14
Nodes (14): API keys, Deep research, Default roles, Free-Multi-Agent, Notes, Outer CLI (no TUI), Pipelines (`/do`), Planner (+6 more)

### Community 62 - "Community 62"
Cohesion: 0.15
Nodes (13): 0. Live role inventory (primary + fallback), 10. Anti-patterns deliberately avoided, 11. Optional profiles (not default), 12. Key checklist for free-durable defaults, 13. Source map (research), 1. Design goals, 2. Calls per pipeline (budget math), 5. System A — Vibe Coding (role assignments) (+5 more)

### Community 63 - "Community 63"
Cohesion: 0.31
Nodes (9): config/cli_toolbox.yaml, Toolbox profile: core, bat (toolbox), eza (toolbox), fd (toolbox), ripgrep (toolbox), core/toolbox.py, Runtime CLI soft-upgrade (+1 more)

### Community 64 - "Community 64"
Cohesion: 0.19
Nodes (19): modern_find_files(), modern_list_dir(), modern_search_text(), modern_view_file(), ProbeResult, Path, Terminal toolbox catalog for MultiAgent.  Loads ``config/cli_toolbox.yaml`` and, Return the first installed catalog tool for a host capability. (+11 more)

### Community 65 - "Community 65"
Cohesion: 0.21
Nodes (12): CLI context settings, Graphify context integration, Chat host tools, Interactive TUI (multiagent), Planner (/do), agnes-2.0-flash, Agnes AI provider, ResearchProfile typology (+4 more)

### Community 66 - "Community 66"
Cohesion: 0.33
Nodes (7): core/router.py, Fallback cascade DAG, codestral-latest, Cerebras provider, Gemini (Google AI Studio) provider, Mistral provider, vibe_coding.coder

### Community 67 - "Community 67"
Cohesion: 0.15
Nodes (13): 1. What existed before, 2.1 `HandoffRecord` (one transfer), 2.2 Graph state field, 2.3 Official API: `transfer_control`, 2. Formal handoff model, 3. Control flow diagrams, 4. Swarm analogy, 5. Failure modes (+5 more)

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
Cohesion: 0.17
Nodes (17): exec_tool(), Any, Execute a single tool; never raises — returns ToolResult., clear_runtime_cache(), Rewrite leading classic utilities to modern catalog tools when installed.      O, soft_rewrite_shell_command(), Tests for the terminal toolbox catalog (doctor / suggest / search)., test_grep_annotates_backend() (+9 more)

### Community 72 - "Community 72"
Cohesion: 0.22
Nodes (13): ProgressCb, ResearchProfile, NoLiveSearchError, raise_if_no_live_search(), Raised when search output admits it did not perform a live search., Raise ``NoLiveSearchError`` if the result admits it wasn't a real search., format_linked_presence_fetch_block(), outbound_presence_search_facets() (+5 more)

### Community 73 - "Community 73"
Cohesion: 0.67
Nodes (4): config/defaults_model_router.yaml (factory), config/model_router.yaml (live), core/agent_config.py, Systems orchestration document

### Community 74 - "Community 74"
Cohesion: 0.17
Nodes (12): 4.1 Rubric definition (0–100 per area), 4.2 Benchmark scores by model × area, 4.3 Recomendación primario vs fallback por rol, 4.4 Cómo se elige y se usa el modelo en un run (end-to-end), 4.5 Reasoning / thinking effort (same call, no extra RPD), 4. Scoring rubric and model benchmarks (0–100), Cascade safety, Critical quota fact (calls ≠ tokens) (+4 more)

### Community 75 - "Community 75"
Cohesion: 0.22
Nodes (9): List doctor profiles., tools_profiles(), _as_str_tuple(), list_profiles(), load_catalog(), Any, Load and validate the toolbox catalog YAML., test_catalog_loads_and_has_core_tools() (+1 more)

### Community 76 - "Community 76"
Cohesion: 0.22
Nodes (8): Architect checklist (put into `architecture` + `test_cases`), Coder checklist, Contact UX, Design tokens, Grounded facts first, Page structure (minimum bar), Stack & files, Vibe: static brand landing quality

### Community 77 - "Community 77"
Cohesion: 0.13
Nodes (24): extract_primary_ok_blocks(), extract_user_domains(), extract_user_urls(), fetch_outbound_presence_pages(), fetch_user_primary_sources(), _host_of(), is_plausible_public_host(), is_plausible_source_url() (+16 more)

### Community 78 - "Community 78"
Cohesion: 0.29
Nodes (6): _isolate_clients(), Path, Root conftest — sets up fake API keys so that imports of core.clients don't rais, Clear cached LLM clients between tests to avoid cross-contamination., Provide a temporary SQLite path for QuotaTracker in tests., tmp_quota_db()

### Community 79 - "Community 79"
Cohesion: 0.20
Nodes (6): Contact UX when email is a gap, Correct content-test patterns, How the pipeline should build the page, Related code, Symptoms we saw in production, Vibe coding: brand / marketing landing failures

### Community 82 - "Community 82"
Cohesion: 0.29
Nodes (6): Debugger rule, Good patterns, Hard anti-patterns (never generate these), Vibe: content tests for static landings, What to assert, When research says no email

### Community 83 - "Community 83"
Cohesion: 0.50
Nodes (5): core/quotas.py, command-a-plus-05-2026, Cohere provider, deep_research.grounding, Soft quotas vs real limits

### Community 84 - "Community 84"
Cohesion: 0.40
Nodes (5): Model benchmarks (0–100) and intended use, Project structure, Provider rate limits (API keys), Reasoning used for model placement, Technical reference

## Knowledge Gaps
- **115 isolated node(s):** `Any`, `install-launcher.sh script`, `Context`, `Any`, `Any` (+110 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ConversationSession` connect `CLI Session Context` to `TUI Approval Widgets`, `Config PiP Panel`, `Agent Chat Context`, `Prompt Area Input`, `Skills Registry CLI`, `Chat History Widget`, `Community 71`, `TUI Role Selectors`, `Slash Commands`, `Tool Approval Handlers`, `Chat Turn Tools`, `Tool Approval Wait`, `Config Editor`, `TUI Launch Init`?**
  _High betweenness centrality (0.080) - this node is a cross-community bridge._
- **Why does `MultiAgentApp` connect `Tool Approval Handlers` to `CLI Session Context`, `TUI Approval Widgets`, `Config PiP Panel`, `Prompt Area Input`, `Chat History Widget`, `TUI Role Selectors`, `Chat Turn Tools`, `Tool Approval Wait`, `Architect Spec Schema`, `TUI Launch Init`?**
  _High betweenness centrality (0.046) - this node is a cross-community bridge._
- **Why does `is_plausible_source_url()` connect `Community 77` to `Source Fetch Search`, `Deep Research Graph`, `Search Guards Scrub`, `TUI App Core`?**
  _High betweenness centrality (0.034) - this node is a cross-community bridge._
- **Are the 30 inferred relationships involving `ConversationSession` (e.g. with `Changed` and `Any`) actually correct?**
  _`ConversationSession` has 30 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `MultiAgentApp` (e.g. with `ConversationSession` and `ToolCall`) actually correct?**
  _`MultiAgentApp` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 18 inferred relationships involving `DifficultyAssessment` (e.g. with `Any` and `date`) actually correct?**
  _`DifficultyAssessment` has 18 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `CodeArtifact` (e.g. with `CodeArtifact` and `TechnicalSpec`) actually correct?**
  _`CodeArtifact` has 19 INFERRED edges - model-reasoned connections that need verification._