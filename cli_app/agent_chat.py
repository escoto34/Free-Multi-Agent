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
from cli_app.session import ConversationSession
from cli_app.tools import (
    exec_tool,
    format_tool_results,
    parse_tool_calls,
    run_tools,
    strip_tool_blocks,
    tools_help_text,
)
from core.agent_runtime import invoke_router
from core.config_editor import get_cli_settings

logger = logging.getLogger(__name__)

MAX_ROUNDS = 8
ApprovalFn = Callable[[Any], str]

_ACTION_RE = re.compile(
    r"\b(crea|crear|create|write|edit|install|pip|venv|actualiza|update|"
    r"borra|delete|run|ejecuta|escribe|escrib[ei]|haz|make|add|agrega)\b",
    re.I,
)
_HELLO_RE = re.compile(r"hola\s*mundo|hello\s*world", re.I)
_FAKE_TOOL_RE = re.compile(
    r"(Ejecut[eé]\s+.*graphify|graphify\s+query\s+[\"']|【[^】]+】|→\s*skipped:)",
    re.I,
)


def _seed_context(user_text: str) -> str:
    """Cheap host-side context so the model need not invent graphify CLI."""
    parts: list[str] = []
    try:
        from cli_app.context_tools import (
            gather_dir_context,
            gather_file_context,
            in_multiagent_project,
        )
        from cli_app.graph_rag import graph_available, query_graph

        # Always use package ROOT (not launch cwd)
        if in_multiagent_project() and graph_available():
            g = query_graph(user_text, budget=1200)
            if g:
                parts.append(f"=== KNOWLEDGE GRAPH (seed) ===\n{g}\n=== END GRAPH ===")
        d = gather_dir_context(user_text)
        if d:
            parts.append(f"=== PROJECT DIRS ===\n{d}\n=== END DIRS ===")
        f = gather_file_context(user_text)
        if f:
            parts.append(f"=== PROJECT FILES ===\n{f}\n=== END FILES ===")
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
        "Heavy multi-pipeline work: suggest /do <task>.\n"
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
    chat = settings["chat"]
    recent_n = int(settings.get("chat_recent_messages") or 4)
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

    # --- Host-side hello-world create (model often forgets write_file) ---
    # Still go through approval when not always_approve
    if _HELLO_RE.search(user_text) and re.search(
        r"\b(crea|crear|create|write|archivo|file|haz)\b", user_text, re.I
    ):
        from cli_app.tools import ToolCall

        path = "hola_mundo.py"
        m = re.search(
            r"(?:archivo|file)\s+[«\"'`]?([A-Za-z0-9_./-]+\.[A-Za-z0-9]+)[»\"'`]?",
            user_text,
            re.I,
        )
        if m:
            path = m.group(1)
        content = 'print("Hola mundo")\n'
        call = ToolCall(
            name="write_file",
            args={"path": path, "content": content},
        )
        if not session.always_approve and approve is not None:
            decision = (approve(call) or "reject").strip().lower()
            if decision in ("always", "!", "always_approve"):
                session.always_approve = True
                decision = "approve"
            if decision not in ("approve", "yes", "y", "a", "ok", "accept"):
                session.add("user", user_text[:800])
                msg = f"Creación de `{path}` rechazada."
                session.add("assistant", msg)
                return {
                    "ok": True,
                    "text": msg,
                    "always_approve": session.always_approve,
                    "tools_used": [],
                    "data": {"used_graph": False},
                }
        res = exec_tool("write_file", call.args)
        session.add("user", user_text[:800])
        from cli_app.tools import work_root

        where = work_root()
        if res.ok:
            text = (
                f"Creado `{path}` en `{where}`:\n\n```python\n{content}```\n\n"
                f"{res.output}"
            )
        else:
            text = f"No se pudo crear `{path}` en `{where}`: {res.output}"
        session.add("assistant", text[:store_max])
        return {
            "ok": res.ok,
            "text": text,
            "always_approve": session.always_approve,
            "tools_used": ["write_file"],
            "data": {"used_graph": False, "tools": ["write_file"]},
        }

    session.add("user", user_text[:800])
    seed = _seed_context(user_text)

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
                provider=chat["provider"],
                model=chat["model"],
                messages=messages,
                fallback=chat.get("fallback"),
            )
            raw = (resp.content or "").strip()
        except Exception as exc:
            err = f"(chat error: {exc})"
            session.add("assistant", err[:store_max])
            return {
                "ok": False,
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

        # One tool at a time (approval UI shows a single command header)
        messages.append({"role": "assistant", "content": raw[:6000]})
        all_results = []
        for call in calls:
            _prog(f"tool: {call.name}")
            results, always, _ = run_tools(
                [call],
                approve=approve,
                always_approve=always,
                one_mutating_at_a_time=True,
            )
            session.always_approve = always
            all_results.extend(results)
            for r in results:
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
    session.maybe_autocompact(threshold=0.55)

    return {
        "ok": True,
        "text": final_text,
        "always_approve": always,
        "tools_used": tools_used,
        "data": {
            "used_graph": used_graph,
            "tools": tools_used,
            "always_approve": always,
        },
    }
