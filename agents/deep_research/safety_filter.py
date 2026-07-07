"""
Safety Filter agent using PydanticAI definition.
Checks research topics for safety, compliance, and ethical standards.
"""

from __future__ import annotations

from pydantic_ai import Agent
from schemas.deep_research import SafetyClassification
from core.router import call_agent

SYSTEM_PROMPT = """You are a rigorous AI Safety and Moderation agent.
Assess the user query. Determine if the request is safe, ethical, and appropriate to research.
You MUST output your response strictly as a JSON object matching this schema:
{
  "is_safe": true_or_false,
  "reasons": ["Explain why the query is unsafe or inappropriate, if applicable (empty if safe)."]
}

Only return raw JSON. Do not wrap in markdown code blocks like ```json ... ```.
"""

# Official PydanticAI Agent definition
safety_filter_agent = Agent(
    "test",
    output_type=SafetyClassification,
    system_prompt=SYSTEM_PROMPT,
)


def run_safety_filter(query: str, router_instance=None) -> SafetyClassification:
    """Run the Safety Filter agent to classify if the research query is safe."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Assess this research query: {query}"},
    ]

    # In deep_research, the safety filter uses groq openai/gpt-oss-safeguard-20b
    caller = router_instance or call_agent
    if hasattr(caller, "call_agent"):
        resp = caller.call_agent(
            provider="groq",
            model="openai/gpt-oss-safeguard-20b",
            messages=messages,
        )
    else:
        resp = caller(
            provider="groq",
            model="openai/gpt-oss-safeguard-20b",
            messages=messages,
        )

    content = resp.content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[-1]
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        content = content.strip()

    return SafetyClassification.model_validate_json(content)
