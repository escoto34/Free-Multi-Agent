"""
Architect agent using PydanticAI definition.
Responsible for producing a TechnicalSpec from a software requirements prompt.
"""

from __future__ import annotations

import json
from pydantic_ai import Agent
from schemas.vibe_coding import TechnicalSpec
from core.router import call_agent

SYSTEM_PROMPT = """You are an expert software architect.
Analyze the user request and generate a complete, structured Technical Specification.
You MUST output your response strictly as a JSON object matching this schema:
{
  "architecture": "Detailed description of architecture and patterns.",
  "test_cases": ["List of critical unit test cases to verify the code."],
  "files_to_create": ["List of relative file paths that need to be created."]
}

Ensure your response is valid JSON only. Do not wrap in markdown code blocks like ```json ... ```. Just return raw JSON.
"""

# Official PydanticAI Agent definition
architect_agent = Agent(
    "test",
    output_type=TechnicalSpec,
    system_prompt=SYSTEM_PROMPT,
)


def run_architect(idea: str, router_instance=None) -> TechnicalSpec:
    """Run the Architect agent to design the technical specification for the given idea.

    Uses the router for quota-gated, fallback-cascaded calls.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Design spec for this idea: {idea}"},
    ]

    # In vibe_coding, the architect uses cohere command-a-plus-05-2026
    # If the provided router_instance is None, delegates to the default singleton router.
    caller = router_instance or call_agent
    if hasattr(caller, "call_agent"):
        resp = caller.call_agent(
            provider="cohere",
            model="command-a-plus-05-2026",
            messages=messages,
        )
    else:
        resp = caller(
            provider="cohere",
            model="command-a-plus-05-2026",
            messages=messages,
        )

    # Clean potential markdown wrapping if present
    content = resp.content.strip()
    if content.startswith("```"):
        # Remove ```json or ``` at start
        content = content.split("\n", 1)[-1]
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        content = content.strip()

    return TechnicalSpec.model_validate_json(content)
