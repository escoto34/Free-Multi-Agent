"""
Debugger agent for System A (Vibe Coding).

Reviews test outputs and code. Provider/model/fallback from YAML.
When tencent/hy3:free expires, edit model_router.yaml only.
"""

from __future__ import annotations

import json
from typing import Optional

from core.agent_runtime import run_structured_agent
from schemas.vibe_coding import CodeArtifact, DebugReport

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


def run_debugger(
    artifact: CodeArtifact,
    test_logs: str,
    router_instance=None,
    fallback_override: Optional[dict[str, str]] = None,
) -> DebugReport:
    """Review code and test logs; return pass/fail + fix suggestion."""
    prompt_payload = (
        f"Source Code Files:\n{json.dumps(artifact.files, indent=2)}\n\n"
        f"Test execution logs/results:\n{test_logs}"
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt_payload},
    ]
    return run_structured_agent(
        "vibe_coding",
        "debugger",
        messages=messages,
        schema=DebugReport,
        router_instance=router_instance,
        fallback_override=fallback_override,
    )
