"""
Debugger agent for System A (Vibe Coding).

Reviews test outputs and code. Provider/model/fallback from YAML.
When tencent/hy3:free expires, edit model_router.yaml only.
"""

from __future__ import annotations

import json
from typing import Optional

from agents.vibe_coding.web_quality import WEB_LANDING_QUALITY_RULES
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

Rules:
- If logs say OVERALL: PASS and static checks passed, set passed=true.
- If logs show NODE/JEST PROJECT DETECTED or stack mismatch, set passed=false and
  suggested_fix must be: rewrite as static HTML/CSS/JS + pytest content tests in a
  dedicated folder; drop Next.js/Jest unless the user required Node.
- If grounded brand strings (hex, wa.me, logo URL) are missing, require adding them.
- Do not suggest installing Selenium or npm for simple marketing sites.

## Critical: do not mis-diagnose content tests
- If a test fails because HTML contains "@" from CSS `@media` / `@keyframes` /
  `@import` / `@font-face`, the TEST is wrong — NOT because a real email exists.
  suggested_fix must rewrite the test to check `mailto:` absence and/or an
  email-shaped regex. NEVER tell the coder to delete all "@" from CSS.
- If WEB QUALITY LINT FAILED about bare-"@" asserts or type="email" with no
  research email: fix tests and/or remove invented email UI; keep WhatsApp CTAs.
- PRESERVATION WARNING about missing symbols like `soup` is OK when tests drop
  BeautifulSoup intentionally — do not reintroduce bs4 just to keep the symbol.
- Prefer fixing both a weak page (stub layout, missing grounded strings) AND bad
  tests in one suggested_fix when both are broken.

""" + WEB_LANDING_QUALITY_RULES + """

Only return raw JSON. Do not wrap in markdown code blocks like ```json ... ```.
"""


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
