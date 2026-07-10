"""
Execute a PipelinePlan: run /vibe and/or /research steps, optionally chaining
prior outputs so research can inform code (and vice versa when ordered that way).
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from schemas.requests import PipelinePlan, PipelineStep

logger = logging.getLogger(__name__)

ProgressCb = Optional[Callable[[str], None]]


def _emit(cb: ProgressCb, msg: str) -> None:
    if cb:
        cb(msg)
    logger.info(msg)


def _run_research(prompt: str) -> dict[str, Any]:
    from graphs.deep_research_graph import invoke_deep_research_pipeline

    return invoke_deep_research_pipeline(prompt)


def _run_vibe(prompt: str) -> dict[str, Any]:
    from graphs.vibe_coding_graph import invoke_vibe_coding_pipeline

    return invoke_vibe_coding_pipeline(prompt)


def _summarize_step_output(action: str, result: dict[str, Any]) -> str:
    if action == "research":
        content = result.get("content") or ""
        sources = result.get("sources") or []
        err = result.get("error")
        if err:
            return f"[research error] {err}"
        if result.get("is_safe") is False:
            return f"[research unsafe] {', '.join(result.get('safety_reasons') or [])}"
        src = "\n".join(f"- {s}" for s in sources[:12])
        body = content[:3000] + ("…" if len(content) > 3000 else "")
        return f"[research report]\n{body}\n\nSources:\n{src}" if src else body
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


def execute_plan(
    plan: PipelinePlan,
    *,
    progress: ProgressCb = None,
) -> dict[str, Any]:
    """Run each plan step in order. Returns aggregate result for the CLI."""
    prior_blobs: list[str] = []
    step_results: list[dict[str, Any]] = []

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
        if step.uses_prior and prior_blobs:
            prompt = (
                f"{prompt}\n\n"
                f"--- Context from prior pipeline steps (use as input) ---\n"
                + "\n\n".join(prior_blobs[-3:])
            )

        _emit(progress, f"step {i}/{len(plan.steps)}: {action} …")
        try:
            if action == "research":
                raw = _run_research(prompt)
            else:
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

        blob = _summarize_step_output(action, raw)
        prior_blobs.append(blob)
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
                "summary": blob[:1500],
            }
        )

    all_ok = all(s.get("ok") for s in step_results) if step_results else False
    lines = [plan.summary or "Execution finished", ""]
    for s in step_results:
        flag = "ok" if s.get("ok") else "FAIL"
        lines.append(f"[{flag}] step {s['index']} {s['action']}")
        if s.get("error"):
            lines.append(f"  error: {s['error']}")
        elif s.get("summary"):
            lines.append(f"  {s['summary'][:400]}")
    return {
        "ok": all_ok,
        "plan": plan.model_dump(),
        "steps": step_results,
        "text": "\n".join(lines),
    }
