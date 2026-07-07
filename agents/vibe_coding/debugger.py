"""
Debugger agent using PydanticAI definition.
Responsible for reviewing test outputs and code, deciding if validation passed,
listing issues, and proposing precise code-level fixes.
"""

from __future__ import annotations

import json
from typing import Optional
from pydantic_ai import Agent
from schemas.vibe_coding import DebugReport, CodeArtifact
from core.router import call_agent

SYSTEM_PROMPT = """You are an expert debugger and QA engineer.
Your task is to analyze the source code and the output of unit tests.
Determine if all unit test requirements are met and if the code is correct.
You MUST output your response strictly as a JSON object matching this schema:
{
  "passed": true_or_false,
  "issues": ["List of error logs, failing assertions, or code bugs found."],
  "suggested_fix": "Detailed description of the required fix (or null if passed)"
}

Only return raw JSON. Do not wrap in markdown code blocks like ```json ... ```.
"""

# Official PydanticAI Agent definition
debugger_agent = Agent(
    "test",
    output_type=DebugReport,
    system_prompt=SYSTEM_PROMPT,
)


def run_debugger(
    artifact: CodeArtifact,
    test_logs: str,
    router_instance=None,
    fallback_override: Optional[dict[str, str]] = None,
) -> DebugReport:
    """Run the Debugger agent to review the code and test logs.

    Uses OpenRouter tencent/hy3:free with fallback override options.
    """
    prompt_payload = (
        f"Source Code Files:\n{json.dumps(artifact.files, indent=2)}\n\n"
        f"Test execution logs/results:\n{test_logs}"
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt_payload},
    ]

    # In vibe_coding, the debugger uses openrouter tencent/hy3:free
    # Role-specific fallback override: provider=groq, model=openai/gpt-oss-120b
    # passed to call_agent.
    fb = fallback_override or {
        "provider": "groq",
        "model": "openai/gpt-oss-120b",
    }

    caller = router_instance or call_agent
    if hasattr(caller, "call_agent"):
        resp = caller.call_agent(
            provider="openrouter",
            model="tencent/hy3:free",
            messages=messages,
            fallback=fb,
        )
    else:
        resp = caller(
            provider="openrouter",
            model="tencent/hy3:free",
            messages=messages,
            fallback=fb,
        )

    content = resp.content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[-1]
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        content = content.strip()

    return DebugReport.model_validate_json(content)
