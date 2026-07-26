"""
Planner agent: given a free-form user prompt, choose System A (/vibe),
System B (/research), or both as complementary ordered steps.
"""

from __future__ import annotations

from typing import Any, Optional

from core.agent_config import get_agent_config
from core.agent_runtime import run_structured_agent
from core.prompt_fragments import PLANNER_NO_INVENT, STATIC_SITE_RULES
from schemas.requests import PipelinePlan

SYSTEM_PROMPT = (
    "You are the MultiAgent pipeline planner.\n"
    "\n"
    "The product has exactly two heavy pipelines:\n"
    '1. "vibe" — System A vibe-coding: Architect → Coder → tests → Debugger.\n'
    "   Use for implementing/changing code or project files in a Git repo.\n"
    '2. "research" — System B deep-research: safety → search → grounding → synthesis.\n'
    "   Use for factual research, surveys, comparisons, citations from the web.\n"
    "\n"
    "You may receive PROJECT CONTEXT blocks (file excerpts and/or a knowledge-graph\n"
    "snippet). Treat them as authoritative for local code facts; do not invent paths.\n"
    "\n"
    "Given the USER PROMPT, output a JSON plan with ordered steps. Each step is:\n"
    "{\n"
    '  "action": "vibe" | "research",\n'
    '  "prompt": "focused sub-prompt for that pipeline only",\n'
    '  "rationale": "why this step",\n'
    '  "uses_prior": true/false\n'
    "}\n"
    "\n"
    "Rules:\n"
    "- Prefer the smallest plan that fulfills the request (1-2 steps typical; max 4).\n"
    "- Prefer ONE research step for a single subject/brand (include location, brand,\n"
    "  social, competitors as facets inside that one prompt).\n"
    "- Use BOTH when the user needs research AND code (research first, then vibe).\n"
    "- Order: usually research first, then vibe with uses_prior=true so code is informed.\n"
    + PLANNER_NO_INVENT
    + "\n"
    + "- CRITICAL: copy every user-named website/domain verbatim into the research step prompt.\n"
    + "  Deep research PRIMARY-fetches only URLs present in that step text.\n"
    + "- Split only when parts truly need different pipelines (research vs vibe), not when\n"
    + "  one deep-research multi-facet search can cover the whole investigation.\n"
    + "- Never invent a third action. Only \"vibe\" or \"research\".\n"
    + "- prompts must be self-contained enough for the pipeline (plus prior context if uses_prior).\n"
    + "- When file context is present, mention relevant paths in the vibe prompts.\n"
    + "- Do not put Latin abbreviations that look like domains into prompts as bare tokens\n"
    + '  that could be scraped as sites; write "for example" instead of "e.g."\n'
    + "\n"
    + STATIC_SITE_RULES
    + "\n"
    + "Return ONLY valid JSON matching:\n"
    + "{\n"
    + '  "summary": "short overview",\n'
    + '  "steps": [ ... ]\n'
    + "}\n"
)


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
        # Explicit provider/model (tests): still score difficulty for reasoning kwargs.
        from core.agent_runtime import invoke_router, strip_fences
        from core.difficulty_scorer import score_task_difficulty

        cfg = get_agent_config("cli", "planner")
        fb = cfg.get("fallback") if isinstance(cfg, dict) else None
        assess = score_task_difficulty(
            user_body, role_path="cli.planner", subtask="planner"
        )
        resp = invoke_router(
            router_instance,
            provider=provider,
            model=model,
            messages=messages,
            fallback=fb,
            assessment=assess,
            role_path="cli.planner",
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
