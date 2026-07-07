"""
Command Line Interface for running Multi-Agent pipelines.

Commands:
  - run vibe-coding "<idea>"
  - run deep-research "<topic>"

Features:
  - Dynamically warns if tencent/hy3:free is expiring within 3 days or has expired.
  - Formatted observability displaying step status, fallbacks used, and remaining quota.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import date
from pathlib import Path
from typing import Optional
import click
import yaml


def validate_api_keys() -> None:
    """Validate that required API keys are configured and not placeholders."""
    required = {
        "OPENROUTER_API_KEY": "OpenRouter",
        "GROQ_API_KEY": "Groq",
        "COHERE_API_KEY": "Cohere",
    }
    for var, name in required.items():
        val = os.environ.get(var)
        if not val or not val.strip() or "your_" in val or "_here" in val:
            click.secho(
                f"❌ Error: Falta {var} en .env o tiene un valor placeholder.\n"
                f"Por favor, configura tu API key de {name} en el archivo .env.",
                fg="red",
                bold=True,
                err=True,
            )
            sys.exit(1)

from core.router import get_router
from graphs.vibe_coding_graph import get_vibe_coding_graph
from graphs.deep_research_graph import get_deep_research_graph

# Configure logging to show pipeline steps clearly in console
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

_CONFIG_PATH = Path(__file__).parent / "config" / "model_router.yaml"


# ---------------------------------------------------------------------------
# Hy3 Expiration Warning Helper
# ---------------------------------------------------------------------------

def check_hy3_expiration() -> None:
    """Read expiration dates from model_router.yaml and print warnings if near."""
    try:
        with open(_CONFIG_PATH) as fh:
            cfg = yaml.safe_load(fh)
        
        # Check date for vibe_coding debugger
        free_until_str = cfg.get("vibe_coding", {}).get("debugger", {}).get("free_until")
        if not free_until_str:
            return

        expiration_date = date.fromisoformat(free_until_str)
        today = date.today()
        delta_days = (expiration_date - today).days

        click.secho("=" * 70, fg="blue")
        click.secho(f"📅 Current Date: {today.isoformat()} | Hy3 free tier expiry: {expiration_date.isoformat()}", fg="blue")
        
        if 0 <= delta_days <= 3:
            click.secho(
                f"⚠️ WARNING: tencent/hy3:free expires in {delta_days} day(s) "
                f"(on {expiration_date.isoformat()})!\n"
                f"Please ensure fallback configurations (openai/gpt-oss-120b) are tested.",
                fg="yellow",
                bold=True,
            )
        elif delta_days < 0:
            click.secho(
                f"⚠️ WARNING: tencent/hy3:free EXPIRED {abs(delta_days)} day(s) ago "
                f"(on {expiration_date.isoformat()})!\n"
                f"Automatic fallback cascade to openai/gpt-oss-120b on Groq will be triggered.",
                fg="red",
                bold=True,
            )
        else:
            click.secho(f"ℹ️ tencent/hy3:free remains active for {delta_days} more days.", fg="cyan")
        click.secho("=" * 70 + "\n", fg="blue")
    except Exception as exc:
        click.secho(f"Failed to check Hy3 expiration date: {exc}", fg="yellow")


# ---------------------------------------------------------------------------
# CLI Command Setup
# ---------------------------------------------------------------------------

@click.group()
def main() -> None:
    """Multi-Agent Ecosystem Command Line Interface."""
    pass


@main.group()
def run() -> None:
    """Run a multi-agent orchestration graph."""
    pass


@run.command(name="vibe-coding")
@click.argument("idea")
def run_vibe_coding(idea: str) -> None:
    """Execute System A: Architect -> Coder -> Test Executor -> Debugger with Git rollback."""
    check_hy3_expiration()
    validate_api_keys()
    click.secho(f"🚀 Launching System A (Vibe Coding) for: '{idea}'", fg="green", bold=True)

    graph = get_vibe_coding_graph()
    initial_state = {
        "idea": idea,
        "spec": None,
        "artifact": None,
        "test_logs": None,
        "debug_report": None,
        "fix_attempts": 0,
        "git_checkpoint_sha": None,
        "error": None,
    }

    try:
        final_state = graph.invoke(initial_state)
    except Exception as exc:
        click.secho(f"❌ Execution failed: {exc}", fg="red", bold=True)
        sys.exit(1)

    if final_state.get("error"):
        click.secho(f"❌ Pipeline terminated with error: {final_state['error']}", fg="red", bold=True)
        sys.exit(1)

    dr = final_state.get("debug_report")
    attempts = final_state.get("fix_attempts")

    click.echo("\n" + "=" * 50)
    click.secho("🏁 PIPELINE COMPLETE", fg="green", bold=True)
    click.echo("=" * 50)
    
    if dr and dr.passed:
        click.secho(f"✔ SUCCESS: All tests passed on attempt {attempts}/3!", fg="green", bold=True)
        if final_state.get("git_checkpoint_sha"):
            click.secho(f"📦 Git Checkpoint SHA: {final_state['git_checkpoint_sha'][:7]}", fg="green")
        
        # Display files created
        artifact = final_state.get("artifact")
        if artifact:
            click.echo("\nFiles Created/Modified:")
            for fp in artifact.files.keys():
                click.secho(f"  • {fp}", fg="cyan")
    else:
        click.secho(f"❌ FAILURE: Tests failed to pass after {attempts} cycles.", fg="red", bold=True)
        click.secho("🔄 Git state has been rolled back to original clean HEAD commit.", fg="yellow")

    # Display Quota Tracker Status
    router = get_router()
    summary = router.quota.status_summary()
    if summary:
        click.echo("\nRemaining Quotas Today:")
        for label, stats in summary.items():
            click.echo(f"  • {label}: Used {stats['used']}, Remaining {stats['remaining']}")


@run.command(name="deep-research")
@click.argument("topic")
@click.option("--thread-id", default=None, help="Optional thread ID to resume a previous execution checkpoint.")
def run_deep_research(topic: str, thread_id: Optional[str]) -> None:
    """Execute System B: Safety -> Context Compression -> Web Search -> Grounding -> Synthesizer."""
    check_hy3_expiration()
    validate_api_keys()
    
    # Auto-generate a thread-id if none provided
    tid = thread_id or f"research-{abs(hash(topic)) % 100000}"
    
    click.secho(f"🚀 Launching System B (Deep Research) | Thread: {tid}", fg="green", bold=True)
    click.secho(f"🔎 Topic: '{topic}'", fg="green")

    graph = get_deep_research_graph()
    config = {"configurable": {"thread_id": tid}}

    initial_state = {
        "query": topic,
        "safety": None,
        "trends": None,
        "search_results": None,
        "grounded_report": None,
        "final_report": None,
        "error": None,
    }

    try:
        # If thread-id is provided, check if we should resume from savepoint by passing None inputs
        # Otherwise, pass initial_state to start fresh
        inputs = None if thread_id else initial_state
        final_state = graph.invoke(inputs, config=config)
    except Exception as exc:
        click.secho(f"❌ Execution failed: {exc}", fg="red", bold=True)
        click.secho(f"💡 You can resume this execution from the failure point by running:", fg="yellow")
        click.secho(f"   python cli.py run deep-research \"{topic}\" --thread-id {tid}", fg="cyan")
        sys.exit(1)

    if final_state.get("error"):
        click.secho(f"❌ Pipeline terminated with error: {final_state['error']}", fg="red", bold=True)
        sys.exit(1)

    safety = final_state.get("safety")
    if safety and not safety.is_safe:
        click.secho("⚠️ PIPELINE ABORTED: Topic classification is UNSAFE.", fg="red", bold=True)
        click.echo(f"Reasons: {', '.join(safety.reasons)}")
        sys.exit(1)

    click.echo("\n" + "=" * 50)
    click.secho("🏁 EXECUTIVE SYNTHESIS REPORT", fg="green", bold=True)
    click.echo("=" * 50)

    report = final_state.get("final_report")
    if report:
        click.secho(report.content, fg="white")
        click.echo("\nSources Cited:")
        for idx, src in enumerate(report.sources, 1):
            click.secho(f"  [{idx}] {src}", fg="cyan")
    else:
        click.secho("No report was generated.", fg="yellow")

    # Display Quota Tracker Status
    router = get_router()
    summary = router.quota.status_summary()
    if summary:
        click.echo("\nRemaining Quotas Today:")
        for label, stats in summary.items():
            click.echo(f"  • {label}: Used {stats['used']}, Remaining {stats['remaining']}")


if __name__ == "__main__":
    main()
