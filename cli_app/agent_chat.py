"""
Tool-using chat loop for the interactive CLI.

The host fetches graph/dir seeds, then the model may call tools (read/write
files, terminal, graphify). Mutating tools go through an approval callback
**one command at a time**.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Optional

from cli_app.language import chat_language_instruction
from cli_app.session import ConversationSession, PIPELINES_BRIEFING
from cli_app.tools import (
    format_tool_results,
    parse_tool_calls,
    run_tools,
    strip_tool_blocks,
    tools_help_text,
)
from core.agent_runtime import invoke_router, resolve_role_selection
from core.config_editor import get_cli_settings

logger = logging.getLogger(__name__)

MAX_ROUNDS = 8
ApprovalFn = Callable[[Any], str]

_ACTION_RE = re.compile(
    r"\b(crea|crear|create|write|edit|install|pip|venv|actualiza|update|"
    r"borra|delete|run|ejecuta|escribe|escrib[ei]|haz|make|add|agrega)\b",
    re.I,
)
_FAKE_TOOL_RE = re.compile(
    r"(Ejecut[eé]\s+.*graphify|graphify\s+query\s+[\"']|【[^】]+】|→\s*skipped:)",
    re.I,
)


def _recent_pipeline_runs(limit: int = 4) -> str:
    """Recent runs from data/runs.db as a bounded context block (WAVE-17).

    Lets the chat answer "what did the last research say" / "is the site done"
    from recorded facts instead of inventing results.
    """
    try:
        from core.runs import get_run_history

        rows = get_run_history().list_recent(limit=limit)
    except Exception as exc:
        logger.debug("recent runs unavailable: %s", exc)
        return ""
    if not rows:
        return ""
    parts = ["=== RECENT PIPELINE RUNS (recorded facts; do not invent) ==="]
    for r in rows:
        summary = (r.get("result_summary") or r.get("input_summary") or "")[:110]
        parts.append(
            f"- {str(r.get('created_at'))[:19]}  {r.get('system')}: "
            f"{r.get('status')}  {summary}"
        )
    parts.append("=== END RECENT PIPELINE RUNS ===")
    return "\n".join(parts)


def _seed_context(user_text: str, session: ConversationSession) -> str:
    """Cheap host-side context so the model need not invent graphify CLI."""
    parts: list[str] = []
    try:
        from cli_app.context_tools import (
            gather_dir_context,
            gather_file_context,
            graph_mtime,
            in_multiagent_project,
            should_use_graphify,
        )
        from cli_app.graph_rag import graph_available, query_graph

        # Always use package ROOT (not launch cwd). WAVE-17: re-query the graph
        # only on first use or when graph.json changed; reuse the session's
        # cached snippet otherwise (same policy as the planner).
        if in_multiagent_project() and graph_available():
            if should_use_graphify(
                session_graph_mtime=session.graph_mtime_at_inject,
                session_graph_used=session.graph_used,
            ):
                g = query_graph(user_text, budget=1200)
                if g:
                    session.graph_used = True
                    session.graph_mtime_at_inject = graph_mtime()
                    session.cached_graph_snippet = g
            else:
                g = session.cached_graph_snippet or ""
            if g:
                parts.append(f"=== KNOWLEDGE GRAPH (seed) ===\n{g}\n=== END GRAPH ===")
        d = gather_dir_context(user_text)
        if d:
            parts.append(f"=== PROJECT DIRS ===\n{d}\n=== END DIRS ===")
        f = gather_file_context(user_text)
        if f:
            parts.append(f"=== PROJECT FILES ===\n{f}\n=== END FILES ===")
        runs = _recent_pipeline_runs()
        if runs:
            parts.append(runs)
        # If the user asks about modern tools / shell / PATH, seed doctor-ish brief
        if re.search(
            r"\b(eza|ripgrep|\brg\b|fd\b|bat\b|modern tool|toolbox|/tools|"
            r"qué tool|que tool|which tool|instala|install cli)\b",
            user_text or "",
            re.I,
        ):
            brief = _modern_toolbox_block()
            if brief:
                parts.append(f"=== MODERN TOOLBOX ===\n{brief}\n=== END TOOLBOX ===")
    except Exception as exc:
        logger.debug("seed context failed: %s", exc)
    return "\n\n".join(parts)


def _modern_toolbox_block() -> str:
    """Installed catalog capabilities so the model prefers modern CLIs."""
    try:
        from core.toolbox import runtime_brief

        return runtime_brief()
    except Exception:
        return ""


def _system_prompt() -> str:
    modern = _modern_toolbox_block()
    modern_block = f"\n{modern}\n" if modern else ""
    return (
        "You are Free-Multi-Agent's local coding assistant for this repository.\n"
        "Layout:\n"
        "- agents/ = Python package (planner, deep_research/, vibe_coding/)\n"
        "- .agents/ = editor rules only (NOT the agents package)\n"
        "- graphs/, cli_app/, core/, schemas/\n\n"
        "You have HOST TOOLS. Use them for real data. Never invent tool output.\n"
        "Never invent citations like 【file†L1-L9】. Never use '→ skipped:'.\n"
        "Never claim you ran a command unless a TOOL RESULT confirms it.\n"
        "If the seed context already answers a simple question, answer directly "
        "using those paths (e.g. agents/planner.py, agents/deep_research/).\n"
        "To CREATE a file you MUST call write_file — describing code is not enough.\n"
        "For mutations (write/edit/bash/pip/venv) the host asks the user to approve "
        "each command one at a time.\n"
"Python envs: use create_venv + pip_install.\n"
        "Heavy multi-pipeline work: use the run_pipeline tool (approval needed) "
        "or suggest /do <task>.\n"
        f"{PIPELINES_BRIEFING}\n"
        "Directory listing / search / file view: use list_dir, grep, glob, read_file "
        "(they auto-pick eza/rg/fd/bat when installed). Only use run_terminal for "
        "commands host tools cannot cover; prefer modern CLI names from the toolbox.\n"
        f"{chat_language_instruction()}\n"
        f"{modern_block}\n"
        f"{tools_help_text()}"
    )


def _clean_final(text: str) -> str:
    text = strip_tool_blocks(text or "")
    text = re.sub(r"\n*→\s*skipped:.*$", "", text, flags=re.I | re.S)
    text = re.sub(r"【[^】]+】", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def agent_chat_turn(
    user_text: str,
    session: ConversationSession,
    *,
    approve: Optional[ApprovalFn] = None,
    progress: Optional[Callable[[str], None]] = None,
) -> dict[str, Any]:
    """Run a tool-augmented chat turn."""
    settings = get_cli_settings()
    # WAVE-17: use more recent turns when the context is far from the budget.
    base_n = int(settings.get("chat_recent_messages") or 4)
    recent_n = max(base_n, 8) if session.usage_ratio() < 0.35 else base_n
    store_max = int(settings.get("store_reply_max_chars") or 2000)

    def _prog(msg: str) -> None:
        if progress:
            try:
                progress(msg)
            except Exception:
                pass

    from cli_app.commands import _try_graphify_update, _wants_graph_refresh

    # --- Host-side graph refresh (model never invents this) ---
    if _wants_graph_refresh(user_text):
        _prog("running graphify update…")
        status = _try_graphify_update()
        session.graph_used = False
        session.graph_mtime_at_inject = None
        session.cached_graph_snippet = ""
        session.add("user", user_text[:800])
        session.add("assistant", status[:store_max])
        return {
            "ok": True,
            "text": status,
            "always_approve": session.always_approve,
            "tools_used": ["graphify_update"],
            "data": {"graph_updated": True, "used_graph": True},
        }

    session.add("user", user_text[:800])
    seed = _seed_context(user_text, session)

    prior = [m for m in session.messages if m.role in ("user", "assistant")]
    prior = prior[:-1] if prior else []
    recent: list[dict[str, str]] = []
    for m in prior[-recent_n:]:
        content = m.content if len(m.content) <= 600 else m.content[:599] + "…"
        recent.append({"role": m.role, "content": content})

    system = _system_prompt()
    try:
        from core.skills import active_skills

        active = active_skills()
        if active:
            system += (
                f"\n\n(Coding skills active: {', '.join(s.name for s in active)}. "
                "Ignore style skills for factual answers; never emit → skipped.)"
            )
    except Exception:
        pass

    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    messages.extend(recent)
    # WAVE-21: cli.chat goes through the same role-selection machinery as every
    # other role (fitness ranking + reasoning effort). Resolved once per turn so
    # the budget/accreditation decision holds for the whole tool loop.
    chat_p, chat_m, chat_fb, chat_selection, chat_assessment = resolve_role_selection(
        "cli", "chat", messages=messages
    )
    user_block = user_text
    if seed:
        user_block = (
            f"{seed}\n\n"
            "Answer from seed context when sufficient. "
            "Otherwise emit a ```tool block. "
            f"QUESTION: {user_text}"
        )
    messages.append({"role": "user", "content": user_block})

    always = bool(session.always_approve)
    tools_used: list[str] = []
    final_text = ""
    used_graph = "KNOWLEDGE GRAPH" in seed
    forced_tool_retry = False

    for round_i in range(MAX_ROUNDS):
        _prog(f"thinking (round {round_i + 1}/{MAX_ROUNDS})…")
        try:
            resp = invoke_router(
                None,
                provider=chat_p,
                model=chat_m,
                messages=messages,
                fallback=chat_fb,
                assessment=chat_assessment,
                role_path="cli.chat",
            )
            raw = (resp.content or "").strip()
        except Exception as exc:
            err = f"(chat error: {exc})"
            session.add("assistant", err[:store_max])
            return {
                "ok": False,
                "status": "ERROR",
                "error_code": "MAE-0000",
                "text": err,
                "always_approve": always,
                "tools_used": tools_used,
                "data": {"used_graph": used_graph},
            }

        calls = parse_tool_calls(raw)
        visible = _clean_final(raw)

        # Force tool use when the user asked for an action but model only talked
        if (
            not calls
            and not forced_tool_retry
            and _ACTION_RE.search(user_text)
            and round_i == 0
        ):
            forced_tool_retry = True
            messages.append({"role": "assistant", "content": raw[:4000]})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "You did not call any tool. The user asked for an action. "
                        "Emit exactly one ```tool JSON block now "
                        "(write_file / edit_file / run_terminal / graphify_query / …). "
                        "Do not only describe."
                    ),
                }
            )
            continue

        if not calls:
            final_text = visible or raw
            # If model faked tool use, replace with seed-based honesty
            if _FAKE_TOOL_RE.search(final_text) and not tools_used:
                if seed:
                    final_text = (
                        "No inventé comandos. Esto es lo que el host ya obtuvo:\n\n"
                        f"{seed[:4000]}\n\n"
                        "Si necesitas más detalle, pide un path concreto o `/graphify <pregunta>`."
                    )
                else:
                    final_text = (
                        "No pude ejecutar herramientas ni inventar resultados. "
                        "Prueba de nuevo o usa `/graphify <pregunta>`."
                    )
                final_text = _clean_final(final_text)
            break

        if visible:
            _prog(visible[:400])

        # WAVE-13: run ALL requested tools in one run_tools batch. run_tools
        # executes read-only tools freely and prompts mutating tools one-at-a-time,
        # so read tools are batched (matching what the model is told) while write
        # approval stays strictly per-call and never weakened.
        messages.append({"role": "assistant", "content": raw[:6000]})
        all_results = []
        results, always_, rejected_n = run_tools(
            calls,
            approve=approve,
            always_approve=always,
            one_mutating_at_a_time=True,
            ctx={"session": session, "progress": progress},
        )
        session.always_approve = always_
        for r in results:
            _prog(f"tool: {r.name}")
            all_results.append(r)
            tools_used.append(r.name)
            if r.name in ("graphify_query", "graphify_update") and r.ok:
                used_graph = True
        messages.append(
            {
                "role": "user",
                "content": (
                    format_tool_results(all_results)
                    + "\n\nUsing only TOOL RESULTS + seed context, answer the user. "
                    "If you still need a tool, emit another ```tool block; "
                    "otherwise reply in plain markdown with no tool blocks "
                    "and no fake citations."
                ),
            }
        )
        continue
    else:
        final_text = visible or "(max tool rounds reached)"

    final_text = _clean_final(final_text) or "(empty reply)"
    # Prefer seed facts over empty waffle when we have dirs/graph
    if (
        used_graph or "PROJECT DIRS" in seed
    ) and len(final_text) < 40 and seed:
        final_text = (
            "Resumen desde el contexto del host:\n\n" + seed[:3500]
        )

    stored = (
        final_text if len(final_text) <= store_max else final_text[: store_max - 1] + "…"
    )
    session.add("assistant", stored)
    # WAVE-17: optional LLM-based compaction (opt-in; local drop is the default).
    if bool(settings.get("llm_compact")):

        def _llm_compact(prompt: list[dict[str, str]]) -> str:
            cp, cm, cfb, _csel, _cas = resolve_role_selection(
                "cli", "chat", messages=prompt
            )
            return invoke_router(
                None,
                provider=cp,
                model=cm,
                messages=prompt,
                fallback=cfb,
                role_path="cli.chat",
            ).content

        session.compact_with_llm(_llm_compact)
    else:
        session.maybe_autocompact(threshold=0.55)

    return {
        "ok": True,
        "status": "OK",
        "error_code": None,
        "text": final_text,
        "always_approve": always,
        "tools_used": tools_used,
        "data": {
            "used_graph": used_graph,
            "tools": tools_used,
            "always_approve": always,
            # WAVE-21: proof cli.chat routed through role selection — the
            # handoff record now carries the role_path it never did before.
            "model_selection": (
                chat_selection.as_dict() if chat_selection is not None else None
            ),
        },
    }
