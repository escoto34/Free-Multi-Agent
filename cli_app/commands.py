"""
Slash-command registry for the interactive CLI (``/help``, ``/vibe``, …).

Similar in spirit to graphify's ``/graphify …`` commands: typed commands that
operate on the project without leaving the chat session.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from core.agent_config import reload_config
from core.agent_runtime import invoke_router
from core.config_editor import (
    get_cli_settings,
    list_roles,
    reset_to_defaults,
    set_context_limit,
    set_role,
)
from core.keys import get_key_status, set_api_key
from core.router import get_router
from core.runs import get_run_history
from graphs.deep_research_graph import invoke_deep_research_pipeline
from graphs.vibe_coding_graph import invoke_vibe_coding_pipeline

from cli_app.session import ConversationSession

ROOT = Path(__file__).parent.parent


@dataclass
class CommandResult:
    ok: bool
    text: str
    # Optional structured payload for the TUI
    data: Optional[dict[str, Any]] = None


CommandHandler = Callable[[list[str], ConversationSession], CommandResult]


def _help(_args: list[str], _session: ConversationSession) -> CommandResult:
    text = """\
Slash commands (F1 opens this panel · type /help anytime)

  Pipelines
    /do <task>                Planner AI chooses vibe-coding and/or deep-research
    /planner                  Show planner AI (provider/model)
    /planner set <prov> <model>  Choose which AI plans the pipelines
    /research-resume <id> <topic>   Resume System B checkpoint

  Models & orchestration
    /config                   Open config panel (ctrl+o)
    /config set <sys.role> <provider> <model>
    /config fallback <sys.role> <provider> <model>
    /config clear-fallback <sys.role>
    /config cycles <N>        Set vibe_coding.max_fix_cycles
    /config limit <tokens>    Set interactive context limit
    /config reset             Restore factory defaults (System A/B)
    /config text              Dump full role list as text

  API keys & free platforms
    /keys                     Show which keys are set (masked)
    /keys set <provider> <key>  groq|openrouter|cohere|mistral|gemini|cerebras
    /providers                Free-tier platforms, models, signup links

  Session / context
    /compact                  Compact context (ctrl+k)
    /clear                    Clear chat context (keeps system prompt)
    /status                   Context used/limit + message count
    /approve [always|off]     Always-approve write/terminal tools (or ask each time)

  Chat tools (free text)
    The assistant can list/read/write files, edit files, query graphify, and run
    terminal commands. Mutating tools prompt: a / A / r / R / ! (always)

  Skills (global — ~/.config/multiagent/skills.yaml)
    /skills                   List registered skills (ON/off)
    /skills add <path>        Register skill (must contain SKILL.md)
    /skills enable <name>     Activate skill
    /skills disable <name>    Deactivate without removing
    /skills show <name>       Path + description + body preview
    /skills remove <name>     Unregister (files kept)

  Project
    /quota                    Today's free-tier usage
    /history [N]              Recent pipeline runs
    /graphify [question]      Budgeted graph query
    /help                     This help
    /exit                     Quit

  Keys
    ctrl+k compact · ctrl+o config · F1 help · esc close panel · ↑↓ prompt history
"""
    return CommandResult(ok=True, text=text, data={"help_panel": True})


def _status(_args: list[str], session: ConversationSession) -> CommandResult:
    session.reload_limits()
    return CommandResult(ok=True, text=session.status_line())


def _clear(_args: list[str], session: ConversationSession) -> CommandResult:
    session.clear()
    return CommandResult(ok=True, text="Context cleared.")


def _compact(args: list[str], session: ConversationSession) -> CommandResult:
    use_llm = "--llm" in args or "-l" in args
    if use_llm:
        settings = get_cli_settings()
        chat = settings["chat"]

        def llm_call(messages: list[dict[str, str]]) -> str:
            resp = invoke_router(
                None,
                provider=chat["provider"],
                model=chat["model"],
                messages=messages,
                fallback=chat.get("fallback"),
            )
            return resp.content

        msg = session.compact_with_llm(llm_call)
    else:
        msg = session.compact_local()
    return CommandResult(ok=True, text=msg, data={"status": session.status_line()})


def _config(args: list[str], _session: ConversationSession) -> CommandResult:
    # Bare /config → TUI opens picture-in-picture; also return a short dump.
    if not args or (len(args) == 1 and args[0].lower() in ("show", "pip", "panel")):
        lines = [
            "Config panel: ctrl+o (picture-in-picture). "
            "Use /config text for full role dump.\n"
        ]
        for row in list_roles():
            if row.get("scalar"):
                lines.append(f"  {row['id']:32} = {row['model']}")
                continue
            if row.get("missing"):
                continue
            rid = row.get("id") or ""
            if not (
                rid.startswith("cli.")
                or any(
                    rid.endswith(s)
                    for s in (
                        ".architect",
                        ".coder",
                        ".debugger",
                        ".planner",
                        ".chat",
                    )
                )
            ):
                continue
            fb = f"  fb→{row['fallback']}" if row.get("fallback") else ""
            lines.append(
                f"  {row['id']:32} {row['provider']}/{row['model']}{fb}"
            )
        return CommandResult(ok=True, text="\n".join(lines), data={"open_pip": True})

    if args[0].lower() == "text":
        lines = ["Active orchestration roles:\n"]
        for row in list_roles():
            if row.get("scalar"):
                lines.append(f"  {row['id']:32} = {row['model']}")
                continue
            if row.get("missing"):
                lines.append(f"  {row['id']:32} (missing)")
                continue
            fb = f"  fallback→ {row['fallback']}" if row.get("fallback") else ""
            free = f"  free_until={row['free_until']}" if row.get("free_until") else ""
            lines.append(
                f"  {row['id']:32} {row['provider']}/{row['model']}{free}{fb}"
            )
        settings = get_cli_settings()
        lines.append(
            f"\n  cli.context_limit_tokens       = {settings['context_limit_tokens']}"
        )
        return CommandResult(ok=True, text="\n".join(lines))

    sub = args[0].lower()
    if sub == "reset":
        reset_to_defaults()
        return CommandResult(
            ok=True,
            text="Restored factory defaults (System A + B + cli chat).",
        )

    if sub == "cycles" and len(args) >= 2:
        node = set_role("vibe_coding", "max_fix_cycles", model=args[1])
        return CommandResult(ok=True, text=f"max_fix_cycles = {node['max_fix_cycles']}")

    if sub == "limit" and len(args) >= 2:
        set_context_limit(int(args[1]))
        return CommandResult(ok=True, text=f"context_limit_tokens = {args[1]}")

    if sub == "set" and len(args) >= 4:
        sys_role = args[1]
        provider, model = args[2], args[3]
        if "." not in sys_role:
            return CommandResult(
                ok=False, text="Use system.role form, e.g. vibe_coding.debugger"
            )
        system, role = sys_role.split(".", 1)
        node = set_role(system, role, provider=provider, model=model)
        return CommandResult(
            ok=True,
            text=f"Updated {sys_role} → {node['provider']}/{node['model']}",
        )

    if sub == "fallback" and len(args) >= 4:
        sys_role = args[1]
        system, role = sys_role.split(".", 1)
        node = set_role(
            system,
            role,
            fallback_provider=args[2],
            fallback_model=args[3],
        )
        fb = node.get("fallback") or {}
        return CommandResult(
            ok=True,
            text=f"Fallback for {sys_role} → {fb.get('provider')}/{fb.get('model')}",
        )

    if sub == "clear-fallback" and len(args) >= 2:
        sys_role = args[1]
        system, role = sys_role.split(".", 1)
        set_role(system, role, clear_fallback=True)
        return CommandResult(ok=True, text=f"Cleared fallback for {sys_role}")

    return CommandResult(
        ok=False,
        text="Usage: /config | /config set sys.role provider model | /config reset | …",
    )


def _keys(args: list[str], _session: ConversationSession) -> CommandResult:
    if not args:
        lines = ["API keys (.env) — values never shown in full:\n"]
        for row in get_key_status():
            lines.append(
                f"  {row['provider']:12} {row['env']:22} {row['status']:8} {row['preview']}"
            )
        return CommandResult(ok=True, text="\n".join(lines))

    if args[0].lower() == "set" and len(args) >= 2:
        provider = args[1]
        if len(args) < 3:
            return CommandResult(
                ok=False,
                text=(
                    f"Provide the key: /keys set {provider} <api_key>\n"
                    "In the TUI you can also use the Keys panel."
                ),
                data={"prompt_key": provider},
            )
        preview = set_api_key(provider, " ".join(args[2:]))
        return CommandResult(
            ok=True, text=f"Saved {provider} key (preview {preview})."
        )

    return CommandResult(ok=False, text="Usage: /keys | /keys set <provider> <key>")


def _quota(_args: list[str], _session: ConversationSession) -> CommandResult:
    summary = get_router().quota.status_summary()
    if not summary:
        return CommandResult(ok=True, text="No quota usage recorded today yet.")
    lines = ["Remaining quotas today:"]
    for label, stats in summary.items():
        lines.append(
            f"  • {label}: used {stats['used']}, remaining {stats['remaining']}"
        )
    return CommandResult(ok=True, text="\n".join(lines))


def _history(args: list[str], _session: ConversationSession) -> CommandResult:
    limit = 15
    if args:
        try:
            limit = int(args[0])
        except ValueError:
            pass
    rows = get_run_history().list_recent(limit=limit)
    if not rows:
        return CommandResult(ok=True, text="No runs recorded yet.")
    lines = []
    for r in rows:
        lines.append(
            f"{r['created_at'][:19]}  {r['system']:14}  {r['status']:8}  "
            f"{(r.get('input_summary') or '')[:50]}"
        )
    return CommandResult(ok=True, text="\n".join(lines))


def _resolve_planner(session: ConversationSession) -> tuple[str, str]:
    """Return (provider, model) for planner: session override or YAML."""
    if session.planner_provider and session.planner_model:
        return session.planner_provider, session.planner_model
    try:
        from core.agent_config import get_agent_config

        cfg = get_agent_config("cli", "planner")
        return str(cfg["provider"]), str(cfg["model"])
    except Exception:
        return "groq", "openai/gpt-oss-120b"


def _planner(args: list[str], session: ConversationSession) -> CommandResult:
    """Show or set the planner AI used by /do."""
    if not args:
        prov, model = _resolve_planner(session)
        src = (
            "session"
            if session.planner_provider and session.planner_model
            else "config cli.planner"
        )
        return CommandResult(
            ok=True,
            text=(
                f"Planner AI: {prov}/{model}  ({src})\n"
                f"Change: /planner set <provider> <model>\n"
                f"Example: /planner set gemini gemini-2.5-flash\n"
                f"Then: /do research X then implement Y in the repo"
            ),
        )
    if args[0].lower() == "set" and len(args) >= 3:
        from core.config_editor import known_providers, set_role

        prov, model = args[1].lower(), args[2]
        if prov not in known_providers():
            return CommandResult(
                ok=False,
                text=f"Unknown provider {prov!r}. Valid: {known_providers()}",
            )
        # Persist to YAML + session so it sticks across restarts
        try:
            set_role("cli", "planner", provider=prov, model=model)
        except Exception as exc:
            return CommandResult(ok=False, text=f"Could not save planner: {exc}")
        session.planner_provider = prov
        session.planner_model = model
        return CommandResult(
            ok=True,
            text=f"Planner AI set to {prov}/{model} (saved in config + this session).",
        )
    return CommandResult(
        ok=False,
        text="Usage: /planner | /planner set <provider> <model>",
    )


def _build_planner_context(prompt: str, session: ConversationSession) -> str:
    """File reads + optional graphify for the planner (not every turn blindly)."""
    from cli_app.context_tools import (
        gather_file_context,
        graph_mtime,
        paths_from_graph_snippet,
        should_use_graphify,
    )
    from cli_app.graph_rag import graph_available, query_graph

    parts: list[str] = []
    settings = get_cli_settings()
    budget = int(settings.get("graphify_budget") or 1200)

    use_g = should_use_graphify(
        session_graph_mtime=session.graph_mtime_at_inject,
        session_graph_used=session.graph_used,
    )
    graph_snippet = ""
    if use_g and graph_available():
        graph_snippet = query_graph(prompt, budget=budget)
        session.graph_used = True
        session.graph_mtime_at_inject = graph_mtime()
        session.cached_graph_snippet = graph_snippet or ""
        if graph_snippet:
            parts.append(f"[graphify]\n{graph_snippet}")
    elif session.cached_graph_snippet:
        # Reuse last inject when graph unchanged (still in project)
        graph_snippet = session.cached_graph_snippet

    extra = paths_from_graph_snippet(graph_snippet) if graph_snippet else None
    files = gather_file_context(prompt, extra_paths=extra)
    if files:
        parts.append(f"[files]\n{files}")
    return "\n\n".join(parts)


def _do(args: list[str], session: ConversationSession) -> CommandResult:
    """Plan with user-chosen AI, then run vibe and/or research steps."""
    prompt = " ".join(args).strip()
    if not prompt:
        return CommandResult(
            ok=False,
            text=(
                "Usage: /do <task>\n"
                "A planner AI splits the task into vibe-coding and/or deep-research steps.\n"
                "Pick the planner first: /planner set <provider> <model>"
            ),
        )

    from agents.planner import format_plan, plan_pipelines
    from cli_app.orchestrate import execute_plan

    prov, model = _resolve_planner(session)
    session.add("user", f"/do {prompt[:500]}")

    # Systems A/B work best in English — translate when the user writes otherwise.
    from cli_app.language import to_english_for_pipelines

    settings = get_cli_settings()
    chat = settings.get("chat") or {}
    pipeline_prompt = to_english_for_pipelines(
        prompt,
        invoke_fn=invoke_router,
        provider=str(chat.get("provider") or prov),
        model=str(chat.get("model") or model),
        fallback=chat.get("fallback"),
    )
    translated = pipeline_prompt.strip() != prompt.strip()

    context = _build_planner_context(pipeline_prompt, session)
    try:
        plan = plan_pipelines(
            pipeline_prompt, provider=prov, model=model, context=context or None
        )
    except Exception as exc:
        return CommandResult(ok=False, text=f"Planner failed ({prov}/{model}): {exc}")

    plan_text = format_plan(plan)
    # Execute (blocking; TUI runs this in a worker thread)
    try:
        result = execute_plan(plan)
    except Exception as exc:
        return CommandResult(
            ok=False,
            text=f"Plan:\n{plan_text}\n\nExecution failed: {exc}",
        )

    header = f"Planner: {prov}/{model}"
    if translated:
        header += "\n(task translated to English for Systems A/B)"
    text = f"{header}\n\n{plan_text}\n\n---\n\n{result.get('text', '')}"
    session.add("assistant", text[:2000])
    return CommandResult(
        ok=bool(result.get("ok")),
        text=text,
        data={"plan": result.get("plan"), "steps": result.get("steps")},
    )


def _vibe(args: list[str], session: ConversationSession) -> CommandResult:
    idea = " ".join(args).strip()
    if not idea:
        return CommandResult(ok=False, text="Usage: /vibe <idea>")
    # Bare skill paths are a common mistake — point at /skills add.
    from pathlib import Path as _P

    maybe = _P(idea).expanduser()
    if maybe.is_dir() and (maybe / "SKILL.md").is_file():
        return CommandResult(
            ok=False,
            text=(
                f"That looks like a skill folder, not a coding idea.\n"
                f"Register it with:\n"
                f"  /skills add {maybe}\n"
                f"  /skills enable <name>"
            ),
        )
    session.add("user", f"/vibe {idea}")
    try:
        summary = invoke_vibe_coding_pipeline(idea)
    except Exception as exc:
        err = str(exc)
        # Common when an older relative runs.db existed under cwd
        if "mas_executions" in err or "no such table" in err.lower():
            err = (
                f"{err}\n"
                "(run history DB is fixed to MultiAgent/data/runs.db — "
                "retry /vibe; if it persists, delete any local data/runs.db "
                "created by mistake in the project you were standing in)"
            )
        return CommandResult(ok=False, text=f"Vibe-coding failed: {err}")

    if summary.get("error"):
        text = f"Error: {summary['error']}"
    elif summary.get("passed"):
        files = ", ".join(
            f["path"] for f in (summary.get("files_written") or [])
        ) or "(none)"
        text = (
            f"SUCCESS (attempt {summary.get('fix_attempts')}). "
            f"Files: {files}. run_id={summary.get('run_id')}"
        )
    else:
        text = (
            f"FAILED after {summary.get('fix_attempts')} cycles "
            f"(git rolled back). issues={summary.get('issues')}"
        )
    session.add("assistant", text)
    return CommandResult(ok=True, text=text, data=summary)


def _research(args: list[str], session: ConversationSession) -> CommandResult:
    topic = " ".join(args).strip()
    if not topic:
        return CommandResult(ok=False, text="Usage: /research <topic>")
    session.add("user", f"/research {topic}")
    try:
        summary = invoke_deep_research_pipeline(topic)
    except Exception as exc:
        return CommandResult(ok=False, text=f"Deep-research failed: {exc}")

    if summary.get("error"):
        text = f"Error: {summary['error']} (thread={summary.get('thread_id')})"
    elif summary.get("is_safe") is False:
        text = f"UNSAFE: {', '.join(summary.get('safety_reasons') or [])}"
    else:
        content = (summary.get("content") or "")[:2000]
        sources = summary.get("sources") or []
        text = content + (
            "\n\nSources:\n" + "\n".join(f"- {s}" for s in sources[:12])
            if sources
            else ""
        )
        if summary.get("thread_id"):
            text += f"\n\nthread_id={summary['thread_id']}"
    session.add("assistant", text[:8000])
    return CommandResult(ok=True, text=text[:8000], data=summary)


def _research_resume(args: list[str], session: ConversationSession) -> CommandResult:
    if len(args) < 2:
        return CommandResult(
            ok=False, text="Usage: /research-resume <thread_id> <topic>"
        )
    tid, topic = args[0], " ".join(args[1:])
    try:
        summary = invoke_deep_research_pipeline(topic, thread_id=tid)
    except Exception as exc:
        return CommandResult(ok=False, text=f"Resume failed: {exc}")
    content = (summary.get("content") or summary.get("error") or str(summary))[:4000]
    session.add("assistant", content)
    return CommandResult(ok=True, text=content, data=summary)


def _graphify(args: list[str], _session: ConversationSession) -> CommandResult:
    """Query the local knowledge graph (budgeted). Same backend free chat uses."""
    from cli_app.graph_rag import graph_available, query_graph

    query = " ".join(args).strip()
    if not query:
        status = "ready" if graph_available() else "missing graphify-out/graph.json"
        return CommandResult(
            ok=True,
            text=(
                f"Graph status: {status}\n"
                "Usage:\n"
                "  /graphify <question>     raw graph traversal (budgeted)\n"
                "  free-text chat           auto-uses graphify under the hood\n"
                "Rebuild: run graphify on this repo if the graph is stale."
            ),
        )

    settings = get_cli_settings()
    budget = int(settings.get("graphify_budget") or 1200)
    # Optional: /graphify --budget 800 question...
    if args and args[0] in ("--budget", "-b") and len(args) >= 3:
        try:
            budget = int(args[1])
            query = " ".join(args[2:]).strip()
        except ValueError:
            pass

    out = query_graph(query, budget=budget)
    header = f"[graphify budget≈{budget} tokens]\n"
    return CommandResult(ok=True, text=header + (out or "(empty)"))


def _exit(_args: list[str], _session: ConversationSession) -> CommandResult:
    return CommandResult(ok=True, text="exit", data={"exit": True})


def _skills(args: list[str], _session: ConversationSession) -> CommandResult:
    """Manage global external skills (path + SKILL.md format)."""
    from core.skills import (
        GLOBAL_SKILLS_FILE,
        active_skills,
        add_skill,
        list_skills,
        load_skill,
        remove_skill,
        set_enabled,
    )

    if not args:
        rows = list_skills()
        if not rows:
            return CommandResult(
                ok=True,
                text=(
                    f"No skills registered yet.\n"
                    f"Registry: {GLOBAL_SKILLS_FILE}\n"
                    f"Add one:  /skills add /path/to/skill-folder\n"
                    f"Format:   see skills/README.md (SKILL.md + frontmatter)"
                ),
            )
        lines = [f"Global skills registry: {GLOBAL_SKILLS_FILE}\n"]
        for s in rows:
            lines.append(s.summary_line())
            if s.description:
                lines.append(f"         {s.description[:100]}")
        active = [s.name for s in active_skills()]
        lines.append(
            f"\nActive this session: {', '.join(active) if active else '(none)'}"
        )
        return CommandResult(ok=True, text="\n".join(lines))

    sub = args[0].lower()
    rest = args[1:]

    try:
        if sub == "add" and rest:
            path = rest[0]
            enabled = "--disabled" not in rest
            meta = add_skill(path, enabled=enabled)
            state = "enabled" if meta.enabled else "disabled"
            return CommandResult(
                ok=True,
                text=(
                    f"Registered skill {meta.name!r} ({state})\n"
                    f"  path: {meta.path}\n"
                    f"  {meta.description[:160]}\n"
                    f"Toggle: /skills enable {meta.name} | /skills disable {meta.name}"
                ),
            )

        if sub == "enable" and rest:
            meta = set_enabled(rest[0], True)
            return CommandResult(
                ok=True, text=f"Skill {meta.name!r} enabled (global)."
            )

        if sub == "disable" and rest:
            meta = set_enabled(rest[0], False)
            return CommandResult(
                ok=True, text=f"Skill {meta.name!r} disabled (global)."
            )

        if sub == "remove" and rest:
            ok = remove_skill(rest[0])
            if not ok:
                return CommandResult(ok=False, text=f"Skill {rest[0]!r} not found.")
            return CommandResult(
                ok=True,
                text=f"Unregistered {rest[0]!r} (files on disk were not deleted).",
            )

        if sub == "show" and rest:
            meta = load_skill(rest[0])
            preview = meta.body[:800] + ("…" if len(meta.body) > 800 else "")
            return CommandResult(
                ok=True,
                text=(
                    f"name:        {meta.name}\n"
                    f"enabled:     {meta.enabled}\n"
                    f"valid:       {meta.valid} {meta.error or ''}\n"
                    f"version:     {meta.version}\n"
                    f"path:        {meta.path}\n"
                    f"description: {meta.description}\n\n"
                    f"--- body preview ---\n{preview}"
                ),
            )

        if sub == "list":
            return _skills([], _session)

    except Exception as exc:
        return CommandResult(ok=False, text=f"/skills {sub} failed: {exc}")

    return CommandResult(
        ok=False,
        text=(
            "Usage:\n"
            "  /skills\n"
            "  /skills add <path> [--disabled]\n"
            "  /skills enable|disable|remove|show <name>"
        ),
    )


def _providers(_args: list[str], _session: ConversationSession) -> CommandResult:
    """List free-tier providers, models, and whether keys are configured."""
    from core.clients import get_provider_meta, list_provider_names
    from core.keys import get_key_status

    status = {r["provider"]: r for r in get_key_status()}
    lines = ["Free-tier API platforms (System A / B / chat):\n"]
    for name in list_provider_names():
        try:
            meta = get_provider_meta(name)
        except Exception as exc:
            lines.append(f"  {name}: error {exc}")
            continue
        st = status.get(name, {}).get("status", "?")
        models = ", ".join((meta.get("models") or [])[:5])
        lines.append(f"  [{st:7}] {name:12} env={meta.get('env_key')}")
        if meta.get("signup"):
            lines.append(f"             signup: {meta['signup']}")
        if meta.get("notes"):
            lines.append(f"             {meta['notes'][:100]}")
        if models:
            lines.append(f"             models: {models}")
    lines.append(
        "\nWire into a role: /config set vibe_coding.coder mistral codestral-latest"
    )
    lines.append("Add key:         /keys set mistral <api_key>")
    return CommandResult(ok=True, text="\n".join(lines))


def _approve_cmd(args: list[str], session: ConversationSession) -> CommandResult:
    """Toggle always-approve for write/terminal tools."""
    if not args:
        state = "ON" if session.always_approve else "off"
        return CommandResult(
            ok=True,
            text=(
                f"always-approve is {state}\n"
                "  /approve always   — run write/edit/terminal without asking\n"
                "  /approve off      — ask for each command (default)\n"
                "During approval (one command at a time):\n"
                "  accept / a   ·  reject / r   ·  always / !"
            ),
        )
    sub = args[0].lower()
    if sub in ("always", "on", "true", "1", "!"):
        session.always_approve = True
        return CommandResult(
            ok=True,
            text="always-approve ON — mutating tools run without prompt.",
        )
    if sub in ("off", "false", "0", "ask", "prompt"):
        session.always_approve = False
        return CommandResult(
            ok=True,
            text="always-approve OFF — you will be asked to approve tools.",
        )
    return CommandResult(
        ok=False, text="Usage: /approve | /approve always | /approve off"
    )


COMMANDS: dict[str, CommandHandler] = {
    "help": _help,
    "h": _help,
    "status": _status,
    "clear": _clear,
    "compact": _compact,
    "config": _config,
    "keys": _keys,
    "providers": _providers,
    "provider": _providers,
    "skills": _skills,
    "skill": _skills,
    "quota": _quota,
    "history": _history,
    "do": _do,
    "planner": _planner,
    "approve": _approve_cmd,
    # /vibe and /research removed: the planner (/do) chooses pipelines.
    # Keep research-resume for checkpoint recovery.
    "research-resume": _research_resume,
    "graphify": _graphify,
    "exit": _exit,
    "quit": _exit,
    "q": _exit,
}


def dispatch(line: str, session: ConversationSession) -> CommandResult:
    """Parse a slash command line and run the handler."""
    raw = line.strip()
    if not raw.startswith("/"):
        raise ValueError("not a slash command")
    try:
        parts = shlex.split(raw[1:])
    except ValueError as exc:
        return CommandResult(ok=False, text=f"Parse error: {exc}")
    if not parts:
        return _help([], session)
    name, args = parts[0].lower(), parts[1:]
    handler = COMMANDS.get(name)
    if handler is None:
        return CommandResult(
            ok=False,
            text=f"Unknown command /{name}. Type /help for the list.",
        )
    try:
        return handler(args, session)
    except Exception as exc:
        return CommandResult(ok=False, text=f"/{name} failed: {exc}")


def _wants_graph_refresh(text: str) -> bool:
    t = (text or "").lower()
    return bool(
        re.search(
            r"actualiza(r)?\s+(el\s+)?grafo|update\s+(the\s+)?graph|graphify\s+update|"
            r"rebuild\s+(the\s+)?graph",
            t,
        )
    )


def _try_graphify_update() -> str:
    """Run local graphify update; return status text for the user."""
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    try:
        proc = subprocess.run(
            ["graphify", "update", "."],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
        )
        out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        if proc.returncode == 0:
            return f"Grafo actualizado (graphify update .).\n{out[:1500]}"
        return (
            f"graphify update falló (code={proc.returncode}).\n{out[:1500]}\n"
            "Si el binario no está instalado: pip install graphifyy"
        )
    except FileNotFoundError:
        return (
            "No se encontró el comando `graphify` en PATH. "
            "Instala con: pip install graphifyy  (o uv tool install graphifyy)"
        )
    except subprocess.TimeoutExpired:
        return "graphify update agotó el tiempo (timeout)."
    except Exception as exc:
        return f"No se pudo actualizar el grafo: {exc}"


def chat_turn(
    user_text: str,
    session: ConversationSession,
    *,
    approve=None,
    progress=None,
) -> CommandResult:
    """Free-form tool-using chat (files, graphify, terminal with approval)."""
    from cli_app.agent_chat import agent_chat_turn

    result = agent_chat_turn(
        user_text,
        session,
        approve=approve,
        progress=progress,
    )
    data = dict(result.get("data") or {})
    data["tools"] = result.get("tools_used") or []
    data["always_approve"] = result.get("always_approve", session.always_approve)
    # Mark as assistant-visible content for the TUI
    data["used_graph"] = data.get("used_graph", False)
    return CommandResult(
        ok=bool(result.get("ok")),
        text=str(result.get("text") or ""),
        data=data,
    )
