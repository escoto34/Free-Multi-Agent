"""
Coordinator-implementer agent for System A (Vibe Coding) — WAVE-18.

The former architect + coder roles are folded into ONE call: the agent
plans (surgical file list + test cases) and immediately writes the full
implementation, producing a CodeArtifact. The repo tree (paths only) is
provided because existing file *contents* cannot be pre-read before the
file list is decided. Merge discipline and preservation are enforced
after the call by the host (preservation-warning diff) and by the
debugger fix loop.
"""

from __future__ import annotations

from agents.vibe_coding.web_quality import WEB_LANDING_QUALITY_RULES
from core.agent_runtime import run_structured_agent
from core.prompt_fragments import (
    GROUNDED_FACTS_RULES,
    NO_INVENT_RULES,
    NO_JSON_CODEBLOCK,
    STATIC_SITE_RULES,
)
from schemas.vibe_coding import CodeArtifact

SYSTEM_PROMPT = (
    "You are an expert software architect AND implementer working on an EXISTING\n"
    "project (or a greenfield one when the idea is a new app).\n"
    "\n"
    "You receive: the user request, and the REPO FILE TREE (existing file paths).\n"
    "Plan FIRST, then implement in the SAME response — one call, two duties.\n"
    "\n"
    "## Planning rules (architect duty)\n"
    "- Decide the SMALLEST set of files to create/modify. Prefer NEW dedicated\n"
    "  modules for green features instead of rewriting large core files.\n"
    "- If you must modify an existing file (it is in the REPO FILE TREE), you are\n"
    "  responsible for preserving its useful logic: only change what the idea\n"
    "  needs, keep helpers, imports, edge-case handling, public APIs and error\n"
    "  handling intact. You do NOT see the file's current contents — be surgical\n"
    "  and explicit about what you keep.\n"
    "- List every output path (including the pytest file(s)) in files_to_create.\n"
    "- architecture should call out \"preserve X / do not remove Y\" when relevant.\n"
    "- test_cases MUST describe GOOD assertions (substring / regex). Explicitly\n"
    "  FORBID fragile checks like assert \"@\" not in html (CSS @media contains @).\n"
    "- test_cases should check mailto: absence via safe patterns, not bare \"@\".\n"
    "\n"
    "## Implementation rules (coder duty)\n"
    "1. For brand-new paths, write complete, working files.\n"
    "2. For existing paths, MERGE mentally: you only have the path, so be\n"
    "   conservative — never drop unrelated functions/classes the idea did not\n"
    "   mention. When in doubt, prefer a new file over rewriting an existing one.\n"
    "3. Output the FULL final content of every file you touch (not a unified diff).\n"
    "4. summary must state what changed AND what existing logic you preserved\n"
    "   (and why).\n"
    "\n"
    + GROUNDED_FACTS_RULES
    + "\n"
    + NO_INVENT_RULES
    + "\n"
    + STATIC_SITE_RULES
    + "\n"
    + WEB_LANDING_QUALITY_RULES
    + "\n\n"
    + "You MUST output your response strictly as a JSON object matching this schema:\n"
    + '{\n'
    + '  "files_to_create": ["relative/path/to/file1.py", "relative/path/to/test_file.py"],\n'
    + '  "test_cases": ["critical test / content-check descriptions"],\n'
    + '  "architecture": "short rationale + preservation requirements",\n'
    + '  "files": {\n'
    + '     "relative/path/to/file1.py": "full source code for file1",\n'
    + '     "relative/path/to/file2.py": "full source code for file2"\n'
    + '  },\n'
    + '  "summary": "What you changed AND what existing logic you intentionally preserved or removed (and why)."\n'
    + '}\n'
    + "\n"
    + "files_to_create MUST match the keys of files. Every path in files_to_create\n"
    + "must appear in files with full content.\n"
    + "\n"
    + NO_JSON_CODEBLOCK
)


def _format_tree_block(repo_tree: str) -> str:
    if not (repo_tree or "").strip():
        return (
            "REPO FILE TREE: (unavailable — treat every path you write as new)\n"
        )
    return (
        "REPO FILE TREE (existing paths only; contents not shown — if you modify\n"
        "one of these, preserve its logic carefully):\n"
        f"{repo_tree}\n"
        "=== END REPO FILE TREE ===\n"
    )


def run_coder(
    task_text: str,
    router_instance=None,
    repo_tree: str = "",
    assessment=None,
    selection_out=None,
    **runtime_kwargs,
) -> CodeArtifact:
    """Plan + implement *task_text* in one call, returning a CodeArtifact.

    *repo_tree* is the bounded list of existing repo paths (paths only) so the
    model can decide what to modify without us pre-reading candidate files.
    """
    prompt_payload = (
        f"USER REQUEST:\n{task_text}\n\n"
        f"{_format_tree_block(repo_tree)}"
        f"Now plan and implement. Return the full JSON artifact."
    )
    system = SYSTEM_PROMPT
    try:
        from core.skills import build_vibe_skills_block

        skills_block = build_vibe_skills_block(task_text or "")
        if skills_block:
            system = f"{SYSTEM_PROMPT}\n\n{skills_block}"
    except Exception:
        pass
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt_payload},
    ]
    return run_structured_agent(
        "vibe_coding",
        "coder",
        messages=messages,
        schema=CodeArtifact,
        router_instance=router_instance,
        assessment=assessment,
        selection_out=selection_out,
        task_text=task_text or prompt_payload,
        **runtime_kwargs,
    )
