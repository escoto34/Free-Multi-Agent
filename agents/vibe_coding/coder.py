"""
Coder agent for System A (Vibe Coding).

Implements the Architect's TechnicalSpec. When existing file contents are
provided, merges changes while preserving useful logic not contradicted by
the idea (unless it is redundant in context).
"""

from __future__ import annotations

from typing import Optional

from core.agent_runtime import run_structured_agent
from schemas.vibe_coding import CodeArtifact, TechnicalSpec

SYSTEM_PROMPT = """You are an expert programmer working on an EXISTING codebase.

Your job is to implement the Technical Specification with MINIMAL disruption.

## Preservation rules (critical)
1. If EXISTING FILE CONTENTS are provided for a path, treat them as the source of truth.
2. MERGE your changes into that code. Prefer surgical edits over full rewrites.
3. PRESERVE useful logic that is NOT part of the user idea but is still valuable:
   helpers, edge-case handling, comments that document non-obvious behavior,
   imports still needed, public APIs other modules may rely on, error handling.
4. You may REMOVE or rewrite logic ONLY when:
   - it directly conflicts with the new idea / tests, OR
   - it is clearly redundant or dead in the new context (duplicate of new code,
     unused after the change, or obsolete with the new design).
5. Do NOT drop unrelated functions/classes just because the idea did not mention them.
6. For brand-new paths (no existing content), write complete, working files.
7. Output the FULL final content of every file you touch (not a unified diff).

## Grounded research facts (when present in the idea / architecture)
8. Copy brand hex colors, WhatsApp (wa.me) links, social URLs, logo image URLs,
   and address strings EXACTLY from GROUNDED FACTS / research context.
9. NEVER invent: emails, phones, map lat/lng or embeds for wrong cities, doctor
   gender/experience/bios, reviews, or a different color palette (e.g. generic green).
10. Prefer real remote logo URLs from research over placeholder image files.
    Do not write fake .png/.jpg that are plain text. Use inline SVG if no URL.
11. If research lists a gap (no email, no hours), do not invent those fields in the UI.
12. Static marketing pages: keep dependencies minimal; tests as simple pytest
    file reads unless the spec requires otherwise.
13. Do NOT create Next.js / package.json / Jest projects for a brand landing page
    unless the user explicitly asked for that stack. Prefer index.html + css + js
    in one folder with pytest content tests.

You MUST output your response strictly as a JSON object matching this schema:
{
  "files": {
     "relative/path/to/file1.py": "full source code for file1",
     "relative/path/to/file2.py": "full source code for file2"
  },
  "summary": "What you changed AND what existing logic you intentionally preserved or removed (and why)."
}

Only return raw JSON. Do not wrap in markdown code blocks like ```json ... ```.
"""


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
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
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
