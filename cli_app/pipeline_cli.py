"""
Headless pipeline entry point (WAVE-13).

The ``/do`` pipeline flow (planner -> execute_plan) was TUI-only. This exposes
the exact same flow as a plain function so the outer CLI (and CI/cron/other
programs) can run a pipeline without an interactive TUI or a ConversationSession.
No new orchestration logic — only a non-TUI entry point to existing functions.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

ProgressCb = Optional[Callable[[str], None]]


def _resolve_planner(provider: Optional[str], model: Optional[str]) -> tuple[str, str]:
    """Resolve planner provider/model: explicit override, else cli.planner YAML."""
    if provider and model:
        return provider, model
    try:
        from core.agent_config import get_agent_config

        cfg = get_agent_config("cli", "planner")
        return str(cfg.get("provider") or "groq"), str(
            cfg.get("model") or "openai/gpt-oss-120b"
        )
    except Exception:
        return "groq", "openai/gpt-oss-120b"


def run_pipeline(
    task: str,
    *,
    use_gpt_researcher: bool = False,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    progress: ProgressCb = None,
) -> dict:
    """Plan and execute a pipeline for *task*; return the aggregate result.

    Mirrors the internal guts of ``commands._do`` but without a session.
    """
    from agents.planner import plan_pipelines, format_plan
    from cli_app.orchestrate import execute_plan

    def _prog(msg: str) -> None:
        if progress:
            try:
                progress(msg)
            except Exception:
                pass

    prov, m = _resolve_planner(provider, model)

    # Systems A/B work best in English — translate when the task is otherwise.
    from cli_app.language import to_english_for_pipelines
    from core.agent_runtime import invoke_router

    _prog("planning…")
    try:
        from core.agent_config import get_agent_config

        chat = (get_agent_config("cli", "chat") or {})
    except Exception:
        chat = {}
    pipeline_prompt = to_english_for_pipelines(
        task,
        invoke_fn=invoke_router,
        provider=str(chat.get("provider") or prov),
        model=str(chat.get("model") or m),
        fallback=chat.get("fallback"),
    ) or task

    try:
        plan = plan_pipelines(pipeline_prompt, provider=prov, model=m)
    except Exception as exc:
        return {
            "ok": False,
            "text": f"Planner failed ({prov}/{m}): {exc}",
            "plan": None,
            "steps": [],
        }

    plan_text = format_plan(plan)
    engine = "GPT-Researcher" if use_gpt_researcher else "native"
    _prog(f"plan ready — running {len(plan.steps)} step(s) ({engine})")
    try:
        result = execute_plan(
            plan,
            progress=_prog,
            origin_prompt=pipeline_prompt,
            use_gpt_researcher=use_gpt_researcher,
        )
    except Exception as exc:
        return {
            "ok": False,
            "text": f"Plan:\n{plan_text}\n\nExecution failed: {exc}",
            "plan": plan.model_dump(),
            "steps": [],
        }

    text = f"Planner: {prov}/{m}  engine: {engine}\n\n{plan_text}\n\n---\n\n{result.get('text', '')}"
    return {
        "ok": bool(result.get("ok")),
        "text": text,
        "plan": result.get("plan"),
        "steps": result.get("steps"),
    }