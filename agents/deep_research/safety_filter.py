"""
Safety Filter agent for System B (Deep Research).

Provider/model from config/model_router.yaml.
"""

from __future__ import annotations

from core.agent_runtime import run_structured_agent
from schemas.deep_research import SafetyClassification

SYSTEM_PROMPT = """You are a rigorous AI Safety and Moderation agent.
Assess the user query. Determine if the request is safe, ethical, and appropriate to research.
You MUST output your response strictly as a JSON object matching this schema:
{
  "is_safe": true_or_false,
  "reasons": ["Explain why the query is unsafe or inappropriate, if applicable (empty if safe)."]
}

Only return raw JSON. Do not wrap in markdown code blocks like ```json ... ```.
"""


def run_safety_filter(query: str, router_instance=None) -> SafetyClassification:
    """Classify whether the research query is safe to process."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Assess this research query: {query}"},
    ]
    return run_structured_agent(
        "deep_research",
        "safety_filter",
        messages=messages,
        schema=SafetyClassification,
        router_instance=router_instance,
    )
