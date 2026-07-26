"""
Architect agent for System A (Vibe Coding).

Produces a TechnicalSpec from a software requirements prompt.
Prefers surgical file lists so the Coder does not rewrite the whole repo.
"""

from __future__ import annotations

from agents.vibe_coding.web_quality import WEB_LANDING_QUALITY_RULES
from core.agent_runtime import run_structured_agent
from core.prompt_fragments import (
    GROUNDED_FACTS_RULES,
    NO_JSON_CODEBLOCK,
    STATIC_SITE_RULES,
)
from schemas.vibe_coding import TechnicalSpec

SYSTEM_PROMPT = (
    "You are an expert software architect working on an EXISTING project\n"
    "(or a greenfield one when the idea is a new app).\n"
    "\n"
    "Analyze the user request and generate a complete, structured Technical Specification.\n"
    "You MUST output your response strictly as a JSON object matching this schema:\n"
    '{\n'
    '  "architecture": "Detailed description of architecture and patterns. Explain HOW to integrate with existing code: what to add, what to change, what to leave alone.",\n'
    '  "test_cases": ["List of critical unit test cases to verify the code."],\n'
    '  "files_to_create": ["List of relative file paths that need to be created OR modified."]\n'
    '}\n'
    "\n"
    "Rules for files_to_create:\n"
    "- List ONLY paths that must change for this idea. Prefer the smallest set.\n"
    "- Prefer NEW dedicated modules for green features instead of rewriting large core files.\n"
    "- If modifying an existing file is necessary, list it — the Coder will be given that file's current contents and must MERGE, not erase unrelated logic.\n"
    "- Do not list every file in the project \"just in case\".\n"
    "- architecture should call out \"preserve X / do not remove Y\" when relevant.\n"
    "- files_to_create must list every path including the pytest file(s).\n"
    "\n"
    + GROUNDED_FACTS_RULES
    + "\n"
    + STATIC_SITE_RULES
    + "\n"
    + "- test_cases MUST describe GOOD assertions (substring / regex). Explicitly FORBID\n"
    + '  fragile checks like assert "@" not in html (CSS @media contains @).\n'
    + "- test_cases should check mailto: absence via safe patterns, not bare \"@\".\n"
    + "\n"
    + WEB_LANDING_QUALITY_RULES
    + "\n\n"
    + NO_JSON_CODEBLOCK
)


def run_architect(idea: str, router_instance=None) -> TechnicalSpec:
    """Design the technical specification for the given idea."""
    system = SYSTEM_PROMPT
    try:
        from core.skills import build_vibe_skills_block

        skills_block = build_vibe_skills_block(idea or "")
        if skills_block:
            system = f"{SYSTEM_PROMPT}\n\n{skills_block}"
    except Exception:
        pass
    messages = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": (
                f"Design a surgical spec for this idea (minimize files touched; "
                f"preserve existing useful logic elsewhere).\n"
                f"If GROUNDED FACTS FROM PRIOR RESEARCH are present, quote them "
                f"into the architecture and do not invent brand/contact/location.\n\n"
                f"{idea}"
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
