"""
Architect agent for System A (Vibe Coding).

Produces a TechnicalSpec from a software requirements prompt.
Prefers surgical file lists so the Coder does not rewrite the whole repo.
"""

from __future__ import annotations

from core.agent_runtime import run_structured_agent
from schemas.vibe_coding import TechnicalSpec

SYSTEM_PROMPT = """You are an expert software architect working on an EXISTING project
(or a greenfield one when the idea is a new app).

Analyze the user request and generate a complete, structured Technical Specification.
You MUST output your response strictly as a JSON object matching this schema:
{
  "architecture": "Detailed description of architecture and patterns. Explain HOW to integrate with existing code: what to add, what to change, what to leave alone.",
  "test_cases": ["List of critical unit test cases to verify the code."],
  "files_to_create": ["List of relative file paths that need to be created OR modified."]
}

Rules for files_to_create:
- List ONLY paths that must change for this idea. Prefer the smallest set.
- Prefer NEW dedicated modules for green features instead of rewriting large core files.
- If modifying an existing file is necessary, list it — the Coder will be given that file's current contents and must MERGE, not erase unrelated logic.
- Do not list every file in the project "just in case".
- architecture should call out "preserve X / do not remove Y" when relevant.

Ensure your response is valid JSON only. Do not wrap in markdown code blocks like ```json ... ```. Just return raw JSON.
"""


def run_architect(idea: str, router_instance=None) -> TechnicalSpec:
    """Design the technical specification for the given idea."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Design a surgical spec for this idea (minimize files touched; "
                f"preserve existing useful logic elsewhere):\n{idea}"
            ),
        },
    ]
    return run_structured_agent(
        "vibe_coding",
        "architect",
        messages=messages,
        schema=TechnicalSpec,
        router_instance=router_instance,
    )
