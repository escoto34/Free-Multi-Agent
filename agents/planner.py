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
- Prefer the smallest plan that fulfills the request (1–2 steps typical; max 4).
- Prefer ONE research step for a single subject/brand (include location, brand,
  social, competitors as facets inside that one prompt). Do NOT run two sequential
  research pipelines for "entity" + "neighborhood" of the same task — that doubles
  latency. Only add a second research step if the user asked for two unrelated topics.
- Use BOTH when the user needs research AND code (research first, then vibe).
- Order: usually research first, then vibe with uses_prior=true so code is informed.
- When the user wants a website / landing page / brand site from research and does
  NOT name a framework (React, Next.js, Vue, etc.), the vibe step prompt MUST say:
  static HTML/CSS/JS in a dedicated folder + pytest content checks. Do NOT invent
  a full-stack Next.js/Jest plan — the host only runs pytest.
- CRITICAL: copy every user-named website/domain (e.g. brand.com, https://…)
  verbatim into the research step prompt. Deep research PRIMARY-fetches only
  URLs present in that step text. Dropping the official domain empties sources.
- Do NOT invent USP, financing slogans, competitor clinic names, doctor names,
  brand hex colors, phone numbers, or service lists in either step prompt unless
  the user already stated them. Leave facts for research; vibe must rely on prior
  research context for contact/brand assets.
- When the user asks to rebuild a brand site, research prompt should explicitly
  request brand colors, logo URLs, WhatsApp/social links, address, and services
  from the official site (and social). Vibe prompt should say: use only grounded
  facts from prior research; no invented contact or palette.
- Split only when parts truly need different pipelines (research vs vibe), not when
  one deep-research multi-facet search can cover the whole investigation.
- Pure Q&A about this MultiAgent tool itself → still pick research or vibe only if
  they truly need a pipeline; if neither fits, use a single "research" step that
  reframes as investigation OR a single "vibe" if they clearly want code.
- Never invent a third action. Only "vibe" or "research".
- prompts must be self-contained enough for the pipeline (plus prior context if uses_prior).
- When file context is present, mention relevant paths in the vibe prompts.
- Do not put Latin abbreviations that look like domains into prompts as bare tokens
  that could be scraped as sites; write "for example" instead of "e.g." when listing
  domains, or keep real domains only (foo.com).

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
