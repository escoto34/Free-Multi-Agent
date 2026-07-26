"""
Coder agent for System A (Vibe Coding).

Implements the Architect's TechnicalSpec. When existing file contents are
provided, merges changes while preserving useful logic not contradicted by
the idea (unless it is redundant in context).
"""

from __future__ import annotations

from typing import Optional

from agents.vibe_coding.web_quality import WEB_LANDING_QUALITY_RULES
from core.agent_runtime import run_structured_agent
from core.prompt_fragments import (
    GROUNDED_FACTS_RULES,
    NO_INVENT_RULES,
    NO_JSON_CODEBLOCK,
    STATIC_SITE_RULES,
)
from schemas.vibe_coding import CodeArtifact, TechnicalSpec

SYSTEM_PROMPT = (
    "You are an expert programmer working on an EXISTING codebase.\n"
    "\n"
    "Your job is to implement the Technical Specification with MINIMAL disruption.\n"
    "\n"
    "## Preservation rules (critical)\n"
    "1. If EXISTING FILE CONTENTS are provided for a path, treat them as the source of truth.\n"
    "2. MERGE your changes into that code. Prefer surgical edits over full rewrites.\n"
    "3. PRESERVE useful logic that is NOT part of the user idea but is still valuable:\n"
    "   helpers, edge-case handling, comments that document non-obvious behavior,\n"
    "   imports still needed, public APIs other modules may rely on, error handling.\n"
    "4. You may REMOVE or rewrite logic ONLY when:\n"
    "   - it directly conflicts with the new idea / tests, OR\n"
    "   - it is clearly redundant or dead in the new context (duplicate of new code,\n"
    "     unused after the change, or obsolete with the new design).\n"
    "5. Do NOT drop unrelated functions/classes just because the idea did not mention them.\n"
    "6. For brand-new paths (no existing content), write complete, working files.\n"
    "7. Output the FULL final content of every file you touch (not a unified diff).\n"
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
    + '  "files": {\n'
    + '     "relative/path/to/file1.py": "full source code for file1",\n'
    + '     "relative/path/to/file2.py": "full source code for file2"\n'
    + '  },\n'
    + '  "summary": "What you changed AND what existing logic you intentionally preserved or removed (and why)."\n'
    + '}\n'
    + "\n"
    + NO_JSON_CODEBLOCK
)


def _format_existing_block(existing_files: dict[str, str]) -> str:
    if not existing_files:
        return (
            "EXISTING FILE CONTENTS: (none — all paths are new; implement from scratch)\n"
        )
    parts = [
        "EXISTING FILE CONTENTS (preserve useful logic; merge, do not casually rewrite):\n"
    ]
    for path, content in existing_files.items():
        parts.append(f"### FILE: {path}\n```\n{content}\n```\n")
    return "\n".join(parts)


def run_coder(
    spec: TechnicalSpec,
    router_instance=None,
    existing_files: Optional[dict[str, str]] = None,
    assessment=None,
    selection_out=None,
    task_text: Optional[str] = None,
    **runtime_kwargs,
) -> CodeArtifact:
    """Implement the TechnicalSpec, merging into *existing_files* when present."""
    existing_files = existing_files or {}
    prompt_payload = (
        f"Architecture design:\n{spec.architecture}\n\n"
        f"Files to create/modify:\n{spec.files_to_create}\n\n"
        f"Test cases to pass:\n{spec.test_cases}\n\n"
        f"{_format_existing_block(existing_files)}"
    )
    system = SYSTEM_PROMPT
    try:
        from core.skills import build_vibe_skills_block

        # Prefer full task_text (includes GROUNDED FACTS); fall back to architecture.
        skills_block = build_vibe_skills_block(
            (task_text or "") + "\n" + (spec.architecture or "")
        )
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
