"""
Execute a PipelinePlan: run /vibe and/or /research steps, optionally chaining
prior outputs so research can inform code (and vice versa when ordered that way).
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from cli_app.research_constraints import format_grounded_constraints_block
from schemas.requests import PipelinePlan, PipelineStep

logger = logging.getLogger(__name__)

ProgressCb = Optional[Callable[[str], None]]

# Compact blob fed into later steps (token budget). Full report is shown to the user.
# Must stay under schemas.requests._PIPELINE_INPUT_MAX once the step prompt is prepended.
_PRIOR_RESEARCH_CHARS = 16000
_PRIOR_BLOB_CHARS = 24000
_PRIOR_CONSTRAINTS_CHARS = 5500


def _emit(cb: ProgressCb, msg: str) -> None:
    if cb:
        cb(msg)
    logger.info(msg)


def ensure_origin_urls_in_research_prompt(
    step_prompt: str,
    origin_prompt: str = "",
) -> str:
    """Re-inject user-named official domains the planner may have dropped.

    System B only HTTP-fetches PRIMARY sources from the *research step* text.
    If the planner rewrites the brief and omits e.g. ``brand.example.com``, the
    pipeline reports empty sources even when the original /do named the site.
    """
    if not (origin_prompt or "").strip():
        return step_prompt

    try:
        from agents.deep_research.source_fetch import (
            extract_user_domains,
            extract_user_urls,
        )
    except Exception:
        return step_prompt

    origin_urls = extract_user_urls(origin_prompt, max_urls=8)
    origin_domains = extract_user_domains(origin_prompt)
    if not origin_urls and not origin_domains:
        return step_prompt

    prompt = step_prompt or ""
    prompt_l = prompt.lower()
    missing_hosts = [d for d in origin_domains if d.lower() not in prompt_l]
    if not missing_hosts:
        return prompt

    lines = [
        prompt.rstrip(),
        "",
        "=== USER-NAMED OFFICIAL WEBSITES (from original /do task — MUST fetch & cite) ===",
        "The planner may have rewritten this brief; the user still named these sites.",
        "HTTP-fetch them as PRIMARY SOURCES. Extract brand colors, logo/image URLs,",
        "WhatsApp (wa.me), phone, address, and social links from those pages.",
        "Do NOT claim the official website is missing if the host fetch succeeds.",
    ]
    for u in origin_urls:
        lines.append(f"- {u}")
    if not origin_urls:
        for d in missing_hosts:
            lines.append(f"- https://{d}")
    lines.append("=== END USER-NAMED OFFICIAL WEBSITES ===")
    logger.info(
        "Research prompt enriched with origin domains dropped by planner: %s",
        ", ".join(missing_hosts),
    )
    return "\n".join(lines)


def _run_research(prompt: str) -> dict[str, Any]:
    from graphs.deep_research_graph import invoke_deep_research_pipeline

    return invoke_deep_research_pipeline(prompt)


def _run_vibe(prompt: str) -> dict[str, Any]:
    from graphs.vibe_coding_graph import invoke_vibe_coding_pipeline

    return invoke_vibe_coding_pipeline(prompt)


def _format_research_report(
    result: dict[str, Any],
    *,
    max_content: Optional[int] = None,
    max_sources: int = 20,
) -> str:
    """Human-facing research body (optionally capped for prior-step context)."""
    content = result.get("content") or ""
    sources = result.get("sources") or []
    err = result.get("error")
    if err:
        return f"[research error] {err}"
    if result.get("is_safe") is False:
        return f"[research unsafe] {', '.join(result.get('safety_reasons') or [])}"

    body = content
    if max_content is not None and len(body) > max_content:
        body = body[:max_content] + "…"

    parts = [f"[research report]\n{body}"]
    if sources:
        src = "\n".join(f"- {s}" for s in sources[:max_sources])
        parts.append(f"\nSources:\n{src}")
    return "\n".join(parts)


def _summarize_step_output(action: str, result: dict[str, Any]) -> str:
    """Compact text for chaining into later steps (not the full CLI display)."""
    if action == "research":
        # Lead with strict grounded constraints so vibe cannot ignore brand/contact.
        constraints = format_grounded_constraints_block(
            result.get("content") or "",
            list(result.get("sources") or []),
            max_chars=_PRIOR_CONSTRAINTS_CHARS,
        )
        text = _format_research_report(
            result,
            max_content=_PRIOR_RESEARCH_CHARS,
            max_sources=12,
        )
        combined = f"{constraints}\n\n{text}"
        if len(combined) > _PRIOR_BLOB_CHARS:
            return combined[:_PRIOR_BLOB_CHARS] + "…"
        return combined
    # vibe
    if result.get("error"):
        return f"[vibe error] {result['error']}"
    files = result.get("files_written") or []
    paths = ", ".join(f.get("path", "?") for f in files) or "(none)"
    return (
        f"[vibe] passed={result.get('passed')} "
        f"attempts={result.get('fix_attempts')} files={paths}\n"
        f"summary={result.get('summary') or ''}"
    )


def _display_step_output(action: str, result: dict[str, Any]) -> str:
    """Full text shown to the user in /do results."""
    if action == "research":
        return _format_research_report(result)
    return _summarize_step_output(action, result)


def execute_plan(
    plan: PipelinePlan,
    *,
    progress: ProgressCb = None,
    origin_prompt: str = "",
) -> dict[str, Any]:
    """Run each plan step in order. Returns aggregate result for the CLI.

    *origin_prompt* is the original /do task (after optional EN translation).
    Research steps are enriched with any official domains named there so the
    planner cannot drop primary URLs and empty the PRIMARY source fetch.
    """
    prior_blobs: list[str] = []
    step_results: list[dict[str, Any]] = []
    origin = (origin_prompt or "").strip()

    for i, step in enumerate(plan.steps, 1):
        action = (step.action or "").strip().lower()
        if action not in ("vibe", "research"):
            step_results.append(
                {
                    "index": i,
                    "action": action,
                    "ok": False,
                    "error": f"unknown action {action!r} (only vibe|research)",
                }
            )
            continue

        prompt = step.prompt.strip()
        if action == "research" and origin:
            prompt = ensure_origin_urls_in_research_prompt(prompt, origin)
        if step.uses_prior and prior_blobs:
            prior = "\n\n".join(prior_blobs[-3:])
            if action == "vibe":
                prompt = (
                    f"{prompt}\n\n"
                    "=== PRIOR RESEARCH CONTEXT (authoritative for facts) ===\n"
                    "Implement using GROUNDED FACTS first. Never invent contact,\n"
                    "brand colors, maps, doctor bios, or reviews not listed there.\n"
                    "Static landing (HTML/CSS/JS) unless the user named a framework.\n"
                    "Do NOT require an email form if EMAILS are none/gap — use wa.me.\n"
                    "Content tests: never assert bare \"@\" absent (CSS @media has @);\n"
                    "use mailto: / email-regex. Ship a usable hero+services+contact page.\n"
                    f"{prior}\n"
                    "=== END PRIOR RESEARCH CONTEXT ==="
                )
            else:
                prompt = (
                    f"{prompt}\n\n"
                    f"--- Context from prior pipeline steps (use as input) ---\n"
                    f"{prior}"
                )

        _emit(progress, f"step {i}/{len(plan.steps)}: {action} …")
        try:
            if action == "research":
                _emit(progress, "deep-research: safety → search → ground → synthesize")
                raw = _run_research(prompt)
            else:
                _emit(progress, "vibe-coding: architect → code → test …")
                raw = _run_vibe(prompt)
        except Exception as exc:
            step_results.append(
                {
                    "index": i,
                    "action": action,
                    "ok": False,
                    "error": str(exc),
                    "prompt": step.prompt,
                    "rationale": step.rationale,
                }
            )
            prior_blobs.append(f"[{action} failed] {exc}")
            continue

        chain_blob = _summarize_step_output(action, raw)
        display = _display_step_output(action, raw)
        prior_blobs.append(chain_blob)
        ok = not raw.get("error") and raw.get("is_safe") is not False
        if action == "vibe":
            ok = ok and (raw.get("passed") is not False or raw.get("passed") is None)
            # treat explicit failed tests as not-ok for summary
            if raw.get("passed") is False:
                ok = False

        step_results.append(
            {
                "index": i,
                "action": action,
                "ok": ok,
                "prompt": step.prompt,
                "rationale": step.rationale,
                "result": raw,
                "summary": chain_blob[:1500],
                "display": display,
            }
        )

    all_ok = all(s.get("ok") for s in step_results) if step_results else False
    lines = [plan.summary or "Execution finished", ""]
    for s in step_results:
        flag = "ok" if s.get("ok") else "FAIL"
        lines.append(f"[{flag}] step {s['index']} {s['action']}")
        if s.get("error"):
            lines.append(f"  error: {s['error']}")
        elif s.get("display"):
            # Full research report / vibe summary — do not truncate for the user.
            lines.append(s["display"])
        elif s.get("summary"):
            lines.append(s["summary"])
    return {
        "ok": all_ok,
        "plan": plan.model_dump(),
        "steps": step_results,
        "text": "\n".join(lines),
    }
