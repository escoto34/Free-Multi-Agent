"""
Planner agent: given a free-form user prompt, choose System A (/vibe),
System B (/research), or both as complementary ordered steps.
"""

from __future__ import annotations

from typing import Any, Optional

from core.agent_config import get_agent_config
from core.agent_runtime import run_structured_agent
from schemas.requests import PipelinePlan

SYSTEM_PROMPT = """You are the MultiAgent pipeline planner.

The product has exactly two heavy pipelines:
1. "vibe" — System A vibe-coding: Architect → Coder → tests → Debugger.
   Use for implementing/changing code or project files in a Git repo.
2. "research" — System B deep-research: safety → search → grounding → synthesis.
   Use for factual research, surveys, comparisons, citations from the web.

You may receive PROJECT CONTEXT blocks (file excerpts and/or a knowledge-graph
snippet). Treat them as authoritative for local code facts; do not invent paths.

Given the USER PROMPT, output a JSON plan with ordered steps. Each step is:
{
  "action": "vibe" | "research",
  "prompt": "focused sub-prompt for that pipeline only",
  "rationale": "why this step",
  "uses_prior": true/false   // true if this step should receive prior step outputs
}

Rules:
- Prefer the smallest plan that fulfills the request (1–3 steps; max 6).
- Use BOTH when the user needs research AND code (e.g. research APIs then implement).
- Order: usually research first, then vibe with uses_prior=true so code is informed.
- Split a multi-part prompt into separate steps (different parts of the request).
- Pure Q&A about this MultiAgent tool itself → still pick research or vibe only if
  they truly need a pipeline; if neither fits, use a single "research" step that
  reframes as investigation OR a single "vibe" if they clearly want code.
- Never invent a third action. Only "vibe" or "research".
- prompts must be self-contained enough for the pipeline (plus prior context if uses_prior).
- When file context is present, mention relevant paths in the vibe prompts.

Return ONLY valid JSON matching:
{
  "summary": "short overview",
  "steps": [ ... ]
}
"""


def plan_pipelines(
    user_prompt: str,
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    router_instance=None,
    context: Optional[str] = None,
) -> PipelinePlan:
    """Ask the planner model for a PipelinePlan.

    If *provider*/*model* are set, they override ``cli.planner`` YAML config
    for this call (user-chosen planner AI).

    *context* is optional project context (file reads + optional graphify).
    """
    user_body = f"USER PROMPT:\n{user_prompt.strip()}"
    if context and context.strip():
        user_body = (
            f"=== PROJECT CONTEXT ===\n{context.strip()}\n"
            f"=== END CONTEXT ===\n\n{user_body}"
        )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": user_body,
        },
    ]

    if provider and model:
        from core.agent_runtime import invoke_router
        from core.agent_runtime import strip_fences

        cfg = get_agent_config("cli", "planner")
        fb = cfg.get("fallback") if isinstance(cfg, dict) else None
        resp = invoke_router(
            router_instance,
            provider=provider,
            model=model,
            messages=messages,
            fallback=fb,
        )
        return PipelinePlan.model_validate_json(strip_fences(resp.content))

    return run_structured_agent(
        "cli",
        "planner",
        messages=messages,
        schema=PipelinePlan,
        router_instance=router_instance,
    )


def format_plan(plan: PipelinePlan) -> str:
    lines = [f"Plan: {plan.summary or '(no summary)'}", ""]
    for i, step in enumerate(plan.steps, 1):
        prior = " +prior" if step.uses_prior else ""
        lines.append(f"{i}. [{step.action}]{prior}")
        lines.append(f"   {step.prompt[:200]}{'…' if len(step.prompt) > 200 else ''}")
        if step.rationale:
            lines.append(f"   why: {step.rationale[:160]}")
    return "\n".join(lines)
