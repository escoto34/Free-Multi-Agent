"""
Debugger agent for System A (Vibe Coding).

Reviews test outputs and code. Provider/model/fallback from YAML.
"""

from __future__ import annotations

import json
from typing import Optional

from agents.vibe_coding.web_quality import WEB_LANDING_QUALITY_RULES
from core.agent_runtime import run_structured_agent
from core.prompt_fragments import NO_JSON_CODEBLOCK
from schemas.vibe_coding import CodeArtifact, DebugReport

SYSTEM_PROMPT = (
    "You are an expert debugger and QA engineer.\n"
    "Your task is to analyze the source code and the output of unit tests.\n"
    "Determine if all unit test requirements are met and if the code is correct.\n"
    "You MUST output your response strictly as a JSON object matching this schema:\n"
    '{\n'
    '  "passed": true_or_false,\n'
    '  "issues": ["List of error logs, failing assertions, or code bugs found."],\n'
    '  "suggested_fix": "Detailed description of the required fix (or null if passed)"\n'
    '}\n'
    "\n"
    "Rules:\n"
    "- If logs say OVERALL: PASS and static checks passed, set passed=true.\n"
    "- If logs show NODE/JEST PROJECT DETECTED or stack mismatch, set passed=false and\n"
    "  suggested_fix must be: rewrite as static HTML/CSS/JS + pytest content tests in a\n"
    "  dedicated folder; drop Next.js/Jest unless the user required Node.\n"
    "- If grounded brand strings (hex, wa.me, logo URL) are missing, require adding them.\n"
    "- Do not suggest installing Selenium or npm for simple marketing sites.\n"
    "\n"
    "## Critical: do not mis-diagnose content tests\n"
    "- If a test fails because HTML contains \"@\" from CSS `@media` / `@keyframes` /\n"
    "  `@import` / `@font-face`, the TEST is wrong — NOT because a real email exists.\n"
    "  suggested_fix must rewrite the test to check `mailto:` absence and/or an\n"
    "  email-shaped regex. NEVER tell the coder to delete all \"@\" from CSS.\n"
    "- If WEB QUALITY LINT FAILED about bare-\"@\" asserts or type=\"email\" with no\n"
    "  research email: fix tests and/or remove invented email UI; keep WhatsApp CTAs.\n"
    "- PRESERVATION WARNING about missing symbols like `soup` is OK when tests drop\n"
    "  BeautifulSoup intentionally — do not reintroduce bs4 just to keep the symbol.\n"
    "- Prefer fixing both a weak page (stub layout, missing grounded strings) AND bad\n"
    "  tests in one suggested_fix when both are broken.\n"
    "\n"
    + WEB_LANDING_QUALITY_RULES
    + "\n\n"
    + NO_JSON_CODEBLOCK
)


def run_debugger(
    artifact: CodeArtifact,
    test_logs: str,
    router_instance=None,
    fallback_override: Optional[dict[str, str]] = None,
    assessment=None,
    selection_out=None,
    **runtime_kwargs,
) -> DebugReport:
    """Review code and test logs; return pass/fail + fix suggestion."""
    # Cap source dump so free models do not truncate the JSON schema reply
    files_preview: dict[str, str] = {}
    for path, code in (artifact.files or {}).items():
        c = code or ""
        if len(c) > 4000:
            c = c[:4000] + "\n…[truncated]…"
        files_preview[path] = c
    prompt_payload = (
        f"Source Code Files:\n{json.dumps(files_preview, indent=2)}\n\n"
        f"Test execution logs/results:\n{test_logs[:12000]}"
    )
    system = SYSTEM_PROMPT
    try:
        from core.skills import build_vibe_skills_block

        # Match landing skills from logs/paths (html, test_content, @media, etc.)
        skills_block = build_vibe_skills_block(prompt_payload)
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
        "debugger",
        messages=messages,
        schema=DebugReport,
        router_instance=router_instance,
        fallback_override=fallback_override,
        assessment=assessment,
        selection_out=selection_out,
        task_text=prompt_payload,
        **runtime_kwargs,
    )
