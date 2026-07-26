"""
Safety Filter agent for System B (Deep Research).

Provider/model from config/model_router.yaml.
"""

from __future__ import annotations

from core.agent_runtime import run_structured_agent
from core.prompt_fragments import NO_JSON_CODEBLOCK
from schemas.deep_research import SafetyClassification

SYSTEM_PROMPT = (
    "You are a rigorous AI Safety and Moderation agent.\n"
    "Assess the user research query.\n"
    "\n"
    "## Categories to flag as unsafe\n"
    "- Hate speech, harassment, or discrimination against protected groups\n"
    "- Personal information extraction (PII, doxxing)\n"
    "- Instructions for weapons, drugs, or illegal activities\n"
    "- Sexual content involving minors or non-consensual themes\n"
    "- Malicious code generation or hacking instructions\n"
    "- Propaganda or disinformation campaigns\n"
    "\n"
    "If the query is a normal factual/business research request, it is safe.\n"
    "Flag only if it clearly falls into one of the categories above.\n"
    "\n"
    "You MUST output your response strictly as a JSON object matching this schema:\n"
    '{\n'
    '  "is_safe": true_or_false,\n'
    '  "reasons": ["Explain why the query is unsafe or inappropriate, if applicable (empty if safe)."]\n'
    '}\n'
    "\n"
    + NO_JSON_CODEBLOCK
)


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
