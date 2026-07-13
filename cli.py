"""
Command Line Interface for Free-Multi-Agent.

Pipelines (vibe-coding / deep-research) run only inside the interactive CLI
via /do (planner chooses steps). Outer commands are chat, config, keys,
providers, skills, tools, quota, history.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import click
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from core.agent_config import get_agent_config
from core.router import get_router
from core.runs import get_run_history

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)


def _providers_used_by_config() -> set[str]:
    """Providers referenced by active System A/B + cli roles."""
    used: set[str] = set()
    try:
        from core.config_editor import list_roles

        for row in list_roles():
            if row.get("provider"):
                used.add(str(row["provider"]))
            fb = row.get("fallback")
            if isinstance(fb, str) and "/" in fb:
                used.add(fb.split("/", 1)[0])
    except Exception:
        used |= {"groq", "openrouter", "cohere"}
    return used


def validate_api_keys() -> None:
    """Validate keys only for providers actually used in model_router.yaml roles."""
    from core.keys import provider_env_map

    try:
        from core.clients import NO_KEY_PROVIDERS
    except Exception:
        NO_KEY_PROVIDERS = frozenset({"ollama"})

    env_map = provider_env_map()
    needed = _providers_used_by_config()
    missing: list[str] = []
    for prov in sorted(needed):
        if prov in NO_KEY_PROVIDERS:
            continue  # e.g. ollama — local, no secret required
        env_name = env_map.get(prov)
        if not env_name:
            continue
        val = os.environ.get(env_name)
        if not val or not val.strip() or "your_" in val or "_here" in val:
            missing.append(f"  {prov:12} → {env_name}  (multiagent keys set {prov})")
    if missing:
        click.secho(
            "❌ Missing API keys for providers used by current roles:\n"
            + "\n".join(missing)
            + "\n\nOptional: mistral/gemini/cerebras/ollama/agnes only needed if "
            "assigned in /config or as fallbacks. Ollama needs no key "
            "(install + ollama serve + ollama pull <model>).",
            fg="red",
            bold=True,
            err=True,
        )
        sys.exit(1)


def check_hy3_expiration() -> None:
    """Warn if tencent/hy3:free is near or past free_until (from YAML cache)."""
    try:
        free_until_str = get_agent_config("vibe_coding", "debugger").get("free_until")
        if not free_until_str:
            free_until_str = get_agent_config(
                "deep_research", "context_compressor"
            ).get("free_until")
        if not free_until_str:
            return

        expiration_date = date.fromisoformat(free_until_str)
        today = date.today()
        delta_days = (expiration_date - today).days

        click.secho("=" * 70, fg="blue")
        click.secho(
            f"📅 Current Date: {today.isoformat()} | Hy3 free tier expiry: "
            f"{expiration_date.isoformat()}",
            fg="blue",
        )

        if 0 <= delta_days <= 3:
            click.secho(
                f"⚠️ WARNING: tencent/hy3:free expires in {delta_days} day(s) "
                f"(on {expiration_date.isoformat()})!\n"
                f"Edit config/model_router.yaml to switch models; no Python changes needed.",
                fg="yellow",
                bold=True,
            )
        elif delta_days < 0:
            click.secho(
                f"⚠️ WARNING: tencent/hy3:free EXPIRED {abs(delta_days)} day(s) ago "
                f"(on {expiration_date.isoformat()})!\n"
                f"Fallback cascade (e.g. gpt-oss-120b on Groq) will be used when primary fails.",
                fg="red",
                bold=True,
            )
        else:
            click.secho(
                f"ℹ️ tencent/hy3:free remains active for {delta_days} more days.",
                fg="cyan",
            )
        click.secho("=" * 70 + "\n", fg="blue")
    except Exception as exc:
        click.secho(f"Failed to check Hy3 expiration date: {exc}", fg="yellow")


def _print_quota_summary() -> None:
    router = get_router()
    summary = router.quota.status_summary()
    if not summary:
        click.echo("No quota usage recorded today yet.")
        return
    click.echo("\nRemaining Quotas Today:")
    for label, stats in summary.items():
        click.echo(
            f"  • {label}: Used {stats['used']}, Remaining {stats['remaining']}"
        )


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx: click.Context) -> None:
    """Free-Multi-Agent — interactive CLI (pipelines only inside the TUI).

    With no subcommand (``multiagent`` / ``python cli.py``), opens the chat TUI.
    Use /do inside the TUI (planner picks vibe/research) — not as outer subcommands.
    """
    if ctx.invoked_subcommand is None:
        ctx.invoke(chat_cmd)


@main.command(name="quota")
def show_quota() -> None:
    """Show today's free-tier quota usage (from data/quotas.db)."""
    _print_quota_summary()


@main.command(name="history")
@click.option("--limit", default=15, show_default=True, help="Max rows to show.")
def show_history(limit: int) -> None:
    """Show recent pipeline runs (from data/runs.db)."""
    rows = get_run_history().list_recent(limit=limit)
    if not rows:
        click.echo("No runs recorded yet.")
        return
    for r in rows:
        status = r["status"]
        color = {
            "success": "green",
            "failed": "red",
            "error": "red",
            "aborted": "yellow",
            "unsafe": "yellow",
            "running": "cyan",
        }.get(status, "white")
        click.secho(
            f"{r['created_at'][:19]}  {r['system']:14}  {status:8}  "
            f"{(r['input_summary'] or '')[:60]}",
            fg=color,
        )
        if r.get("error"):
            click.echo(f"    error: {r['error'][:120]}")
        if r.get("id"):
            click.echo(f"    id: {r['id']}")


@main.group()
def config() -> None:
    """Inspect / edit model_router.yaml (single source of truth)."""
    pass


@config.command(name="show")
def config_show() -> None:
    """Print active provider/model per agent role."""
    from core.config_editor import list_roles, get_cli_settings

    for row in list_roles():
        if row.get("scalar"):
            click.echo(f"  {row['id']:32} = {row['model']}")
            continue
        if row.get("missing"):
            click.secho(f"  {row['id']:32} (missing)", fg="yellow")
            continue
        fb = f"  fallback→ {row['fallback']}" if row.get("fallback") else ""
        free = f"  free_until={row['free_until']}" if row.get("free_until") else ""
        click.echo(f"  {row['id']:32} {row['provider']}/{row['model']}{free}{fb}")
    settings = get_cli_settings()
    click.echo(f"\n  cli.context_limit_tokens       = {settings['context_limit_tokens']}")


@config.command(name="set")
@click.argument("role_id")
@click.argument("provider")
@click.argument("model")
def config_set(role_id: str, provider: str, model: str) -> None:
    """Set provider/model for a role, e.g. cli.planner groq openai/gpt-oss-120b"""
    from core.config_editor import set_role

    if "." not in role_id:
        click.secho("role_id must be system.role", fg="red", err=True)
        sys.exit(2)
    system, role = role_id.split(".", 1)
    try:
        node = set_role(system, role, provider=provider, model=model)
    except Exception as exc:
        click.secho(f"❌ {exc}", fg="red", err=True)
        sys.exit(1)
    click.secho(
        f"✔ {role_id} → {node['provider']}/{node['model']}", fg="green"
    )


@config.command(name="reset")
@click.confirmation_option(prompt="Restore factory defaults (System A/B stack)?")
def config_reset() -> None:
    """Overwrite model_router.yaml with factory defaults."""
    from core.config_editor import reset_to_defaults

    reset_to_defaults()
    click.secho("✔ Restored defaults from config/defaults_model_router.yaml", fg="green")


@main.group()
def keys() -> None:
    """Manage API keys in .env (values never printed in full)."""
    pass


@keys.command(name="status")
def keys_status() -> None:
    """Show which provider keys are set (masked)."""
    from core.keys import get_key_status

    for row in get_key_status():
        color = "green" if row["status"] == "set" else "red"
        click.secho(
            f"  {row['provider']:12} {row['env']:22} {row['status']:8} {row['preview']}",
            fg=color,
        )


@keys.command(name="set")
@click.argument("provider")
@click.option("--key", "api_key", default=None, help="API key (prompted if omitted).")
def keys_set(provider: str, api_key: Optional[str]) -> None:
    """Write a provider API key to .env."""
    from core.keys import provider_env_map, set_api_key

    valid = sorted(provider_env_map())
    if provider.lower() not in valid:
        click.secho(f"❌ Unknown provider. Valid: {valid}", fg="red", err=True)
        sys.exit(2)
    if not api_key:
        api_key = click.prompt(f"{provider} API key", hide_input=True)
    try:
        preview = set_api_key(provider, api_key)
    except Exception as exc:
        click.secho(f"❌ {exc}", fg="red", err=True)
        sys.exit(1)
    click.secho(f"✔ Saved {provider} key (preview {preview})", fg="green")


@main.command(name="providers")
def providers_cmd() -> None:
    """List free-tier-friendly providers, signup URLs, models, and key status."""
    from core.clients import get_provider_meta, list_provider_names
    from core.keys import get_key_status

    status = {r["provider"]: r for r in get_key_status()}
    click.secho("Free-tier API platforms available to System A / B / chat:\n", bold=True)
    for name in list_provider_names():
        try:
            meta = get_provider_meta(name)
        except Exception as exc:
            click.echo(f"  {name}: (error: {exc})")
            continue
        st = status.get(name, {})
        key_s = st.get("status", "?")
        color = "green" if key_s == "set" else "yellow"
        click.secho(f"▸ {name}", fg="blue", bold=True, nl=False)
        click.secho(f"  key={key_s}  env={meta.get('env_key')}", fg=color)
        if meta.get("base_url"):
            click.echo(f"    base_url: {meta['base_url']}")
        if meta.get("signup"):
            click.echo(f"    signup:   {meta['signup']}")
        if meta.get("notes"):
            click.echo(f"    notes:    {meta['notes']}")
        models = meta.get("models") or []
        if models:
            click.echo(f"    models:   {', '.join(models[:8])}")
        click.echo()
    click.echo(
        "Assign models inside the TUI:\n"
        "  /planner set gemini gemini-2.5-flash\n"
        "  /config set vibe_coding.coder mistral codestral-latest\n"
        "  /config set cli.chat ollama llama3.2\n"
        "  /config set cli.chat agnes agnes-2.0-flash\n"
        "  /do research X then implement Y\n"
    )


@main.command(name="chat")
def chat_cmd() -> None:
    """Interactive TUI (pipelines via /do planner only here)."""
    try:
        from cli_app.tui import run_app
    except ImportError as exc:
        click.secho(
            f"❌ Interactive TUI requires textual. Install with:\n"
            f"   pip install textual\n({exc})",
            fg="red",
            err=True,
        )
        sys.exit(1)
    run_app()


@main.group()
def skills() -> None:
    """Integrate external SKILL.md packs (global enable/disable)."""
    pass


@skills.command(name="list")
def skills_list() -> None:
    """List registered skills (ON/off). Works from any directory."""
    from core.skills import GLOBAL_SKILLS_FILE, list_skills

    rows = list_skills()
    click.echo(f"Registry: {GLOBAL_SKILLS_FILE}")
    if not rows:
        click.echo("  (none) — multiagent skills add /path/to/skill")
        return
    for s in rows:
        color = "green" if s.enabled and s.valid else ("yellow" if s.enabled else "white")
        click.secho(f"  {s.summary_line()}", fg=color)


@skills.command(name="add")
@click.argument("path", type=click.Path(exists=True))
@click.option("--disabled", is_flag=True, help="Register but leave disabled.")
def skills_add(path: str, disabled: bool) -> None:
    """Register a skill folder (must contain valid SKILL.md)."""
    from core.skills import add_skill

    try:
        meta = add_skill(path, enabled=not disabled)
    except Exception as exc:
        click.secho(f"❌ {exc}", fg="red", err=True)
        sys.exit(1)
    state = "enabled" if meta.enabled else "disabled"
    click.secho(f"✔ Registered {meta.name!r} ({state}) → {meta.path}", fg="green")


@skills.command(name="enable")
@click.argument("name")
def skills_enable(name: str) -> None:
    """Enable a registered skill globally."""
    from core.skills import set_enabled

    try:
        meta = set_enabled(name, True)
    except Exception as exc:
        click.secho(f"❌ {exc}", fg="red", err=True)
        sys.exit(1)
    click.secho(f"✔ {meta.name} enabled", fg="green")


@skills.command(name="disable")
@click.argument("name")
def skills_disable(name: str) -> None:
    """Disable a skill globally (stays registered)."""
    from core.skills import set_enabled

    try:
        meta = set_enabled(name, False)
    except Exception as exc:
        click.secho(f"❌ {exc}", fg="red", err=True)
        sys.exit(1)
    click.secho(f"✔ {meta.name} disabled", fg="yellow")


@skills.command(name="remove")
@click.argument("name")
def skills_remove(name: str) -> None:
    """Unregister a skill (does not delete files)."""
    from core.skills import remove_skill

    if not remove_skill(name):
        click.secho(f"❌ Skill {name!r} not found", fg="red", err=True)
        sys.exit(1)
    click.secho(f"✔ Unregistered {name!r}", fg="green")


@skills.command(name="show")
@click.argument("name")
def skills_show(name: str) -> None:
    """Show skill metadata and body preview."""
    from core.skills import load_skill

    try:
        meta = load_skill(name)
    except Exception as exc:
        click.secho(f"❌ {exc}", fg="red", err=True)
        sys.exit(1)
    click.echo(f"name:        {meta.name}")
    click.echo(f"enabled:     {meta.enabled}")
    click.echo(f"valid:       {meta.valid} {meta.error or ''}")
    click.echo(f"path:        {meta.path}")
    click.echo(f"description: {meta.description}")
    click.echo("\n--- body preview ---")
    click.echo(meta.body[:1200] + ("…" if len(meta.body) > 1200 else ""))


@main.group()
def tools() -> None:
    """Curated terminal toolbox: doctor, suggest, search (see config/cli_toolbox.yaml)."""
    pass


@tools.command(name="doctor")
@click.option(
    "--profile",
    "-p",
    default="core",
    show_default=True,
    help="core|git|docker|k8s|disk|net|monitor|data|security|ai|modern-rust|all",
)
@click.option(
    "--missing-only",
    is_flag=True,
    help="Only print missing tools (hide installed list).",
)
def tools_doctor(profile: str, missing_only: bool) -> None:
    """Check which catalog tools are on PATH."""
    from core.toolbox import doctor

    click.echo(doctor(profile, show_installed=not missing_only), nl=False)


@tools.command(name="suggest")
@click.argument("task", nargs=-1, required=True)
@click.option("--limit", default=8, show_default=True, help="Max recommendations.")
def tools_suggest(task: tuple[str, ...], limit: int) -> None:
    """Recommend tools for a free-form task description."""
    from core.toolbox import suggest

    click.echo(suggest(" ".join(task), limit=limit), nl=False)


@tools.command(name="search")
@click.argument("query", nargs=-1, required=True)
def tools_search(query: tuple[str, ...]) -> None:
    """Search the toolbox catalog by keyword."""
    from core.toolbox import search

    click.echo(search(" ".join(query)), nl=False)


@tools.command(name="show")
@click.argument("tool_id")
def tools_show(tool_id: str) -> None:
    """Show one tool: PATH status, tags, install hints."""
    from core.toolbox import show_tool

    click.echo(show_tool(tool_id), nl=False)


@tools.command(name="list")
@click.argument("category", required=False)
@click.option("--check", "-c", is_flag=True, help="Mark installed (✔) vs missing (·).")
def tools_list(category: Optional[str], check: bool) -> None:
    """List catalog entries, optionally filtered by category."""
    from core.toolbox import list_tools

    click.echo(list_tools(category=category, check=check), nl=False)


@tools.command(name="alt")
@click.argument("classic")
def tools_alt(classic: str) -> None:
    """Modern alternatives to a classic command (ls, grep, cat, …)."""
    from core.toolbox import alternatives

    click.echo(alternatives(classic), nl=False)


@tools.command(name="profiles")
def tools_profiles() -> None:
    """List doctor profiles."""
    from core.toolbox import list_profiles

    for r in list_profiles():
        click.echo(f"  {r['name']:14} ({r['count']:3})  {r['description']}")
    click.echo("  all            (all catalog entries)")


if __name__ == "__main__":
    main()
