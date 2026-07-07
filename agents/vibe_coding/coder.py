"""
Coder agent using PydanticAI definition.
Responsible for writing the actual source code matching the Architect's TechnicalSpec.
"""

from __future__ import annotations

import json
from pydantic_ai import Agent
from schemas.vibe_coding import CodeArtifact, TechnicalSpec
from core.router import call_agent

SYSTEM_PROMPT = """You are an expert programmer.
Your goal is to write full, working code matching the provided Technical Specification.
Implement all files requested.
You MUST output your response strictly as a JSON object matching this schema:
{
  "files": {
     "relative/path/to/file1.py": "full source code for file1",
     "relative/path/to/file2.py": "full source code for file2"
  },
  "summary": "Detailed summary of the changes and files implemented."
}

Only return raw JSON. Do not wrap in markdown code blocks like ```json ... ```.
"""

# Official PydanticAI Agent definition
coder_agent = Agent(
    "test",
    output_type=CodeArtifact,
    system_prompt=SYSTEM_PROMPT,
)


def run_coder(spec: TechnicalSpec, router_instance=None) -> CodeArtifact:
    """Run the Coder agent to implement the files requested in the TechnicalSpec."""
    prompt_payload = (
        f"Architecture design:\n{spec.architecture}\n\n"
        f"Files to create/modify:\n{spec.files_to_create}\n\n"
        f"Test cases to pass:\n{spec.test_cases}"
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt_payload},
    ]

    # In vibe_coding, the coder uses openrouter cohere/north-mini-code:free
    caller = router_instance or call_agent
    if hasattr(caller, "call_agent"):
        resp = caller.call_agent(
            provider="openrouter",
            model="cohere/north-mini-code:free",
            messages=messages,
        )
    else:
        resp = caller(
            provider="openrouter",
            model="cohere/north-mini-code:free",
            messages=messages,
        )

    content = resp.content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[-1]
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        content = content.strip()

    return CodeArtifact.model_validate_json(content)
