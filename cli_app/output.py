"""
Structured CLI output (WAVE-17).

Every user-facing CLI command emits one *envelope*: a small dict with
``status``/``message``/``timestamp``/``errorCode``/``detail`` (plus optional
``context``). The envelope is rendered two ways with the same information:

- Human-readable block (indentation + separators) for terminals.
- JSON for pipelines, log shippers and automation (``--json``).

Stream policy (POSIX-aligned): final results go to stdout, progress and
diagnostics go to stderr. Exit codes: 0 = OK, 1 = ERROR, 2 = usage error,
130 = interrupted (SIGINT / SIGTERM).

Error codes follow an IBM-style ``MAE-<nnnn>`` catalog where each code has an
Explanation and an Action so operators can act deterministically instead of
guessing from a freeform string.
"""

from __future__ import annotations

import json
import signal
import sys
from datetime import datetime, timezone
from typing import Any, Optional

STATUS_OK = "OK"
STATUS_WARNING = "WARNING"
STATUS_ERROR = "ERROR"

_EXIT_OK = 0
_EXIT_ERR = 1
_EXIT_USAGE = 2
_EXIT_INTERRUPTED = 130

# ---------------------------------------------------------------------------
# Error-code catalog (MAE-<nnnn>).
# ---------------------------------------------------------------------------

ERROR_CODES: dict[str, dict[str, str]] = {
    "MAE-0000": {
        "title": "Generic error",
        "explanation": "An unexpected failure occurred.",
        "action": "Retry the operation. If it persists, re-run with verbose logging.",
    },
    "MAE-1000": {
        "title": "Planner failed",
        "explanation": "The planner AI could not produce a valid pipeline plan.",
        "action": "Check provider/model availability with `multiagent providers` and retry `/do`.",
    },
    "MAE-1001": {
        "title": "Planner context error",
        "explanation": "The planner could not enrich its context (project files / chat history).",
        "action": "This is usually transient; retry the command.",
    },
    "MAE-2000": {
        "title": "Pipeline execution failed",
        "explanation": "One or more plan steps failed to complete successfully.",
        "action": "Inspect the step details in the report and retry with /do.",
    },
    "MAE-2100": {
        "title": "Vibe-coding failed",
        "explanation": "System A could not implement the requested change.",
        "action": "Read the error detail and adjust the request or fix environment issues (venv/test runner).",
    },
    "MAE-2200": {
        "title": "Deep research failed",
        "explanation": "System B could not produce a report.",
        "action": "Check network/search availability and the query; retry or resume by thread.",
    },
    "MAE-3000": {
        "title": "Tool call rejected",
        "explanation": "A mutating/shell tool was rejected by the user or approval flow.",
        "action": "Approve the command if intended, or rephrase the request.",
    },
    "MAE-3100": {
        "title": "Tool execution error",
        "explanation": "A host tool failed while running.",
        "action": "Read the tool output in `detail` to diagnose.",
    },
    "MAE-4000": {
        "title": "Config invalid",
        "explanation": "Configuration value was missing or malformed.",
        "action": "Check the value with `multiagent config show` and fix it.",
    },
    "MAE-4100": {
        "title": "API key missing",
        "explanation": "A provider key required by the current roles is not set.",
        "action": "Set it with `multiagent keys set <provider>`.",
    },
    "MAE-5000": {
        "title": "Quota exhausted",
        "explanation": "The free-tier quota for today is exhausted or too low.",
        "action": "Check `multiagent quota`; wait for reset or change roles to another provider.",
    },
    "MAE-9000": {
        "title": "Interrupted",
        "explanation": "The operation was interrupted by the user or the system.",
        "action": "Resubmit the command when ready.",
    },
}

_DEFAULT_CODE = "MAE-0000"


def status_for(ok: bool, *, warning: bool = False) -> str:
    if not ok:
        return STATUS_ERROR
    return STATUS_WARNING if warning else STATUS_OK


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Envelope construction.
# ---------------------------------------------------------------------------


def make_envelope(
    *,
    ok: Optional[bool] = None,
    status: Optional[str] = None,
    message: str = "",
    detail: Any = None,
    error_code: Optional[str] = None,
    context: Optional[dict[str, Any]] = None,
    timestamp: Optional[str] = None,
) -> dict[str, Any]:
    """Build a full envelope (asserting the exact field set)."""
    if status is None:
        status = status_for(bool(ok) if ok is not None else True)
    if error_code is None and status == STATUS_ERROR:
        error_code = "MAE-0000"
    env: dict[str, Any] = {
        "status": status,
        "message": message,
        "timestamp": timestamp or now_utc(),
    }
    if error_code is not None:
        env["errorCode"] = error_code
    if detail is not None:
        env["detail"] = detail
    if context:
        env["context"] = context
    return env


# ---------------------------------------------------------------------------
# Renderers (same information, two formats).
# ---------------------------------------------------------------------------


def render_json(env: dict[str, Any]) -> str:
    return json.dumps(env, ensure_ascii=False, indent=2)


def render_block(env: dict[str, Any]) -> str:
    """Human-readable block with the fields aligned and separators."""
    lines: list[str] = []
    lines.append(f"Timestamp : {env.get('timestamp') or '-'}")
    lines.append(f"Status    : {env.get('status') or '?'}")
    lines.append(f"Message   : {env.get('message') or ''}")
    if env.get("errorCode"):
        lines.append(f"Error Code: {env['errorCode']}")
    ec = env.get("errorCode")
    if ec:
        meta = error_code_info(ec)
        if meta:
            lines.append(f"Explanation: {meta['explanation']}")
            lines.append(f"Action     : {meta['action']}")
    detail = env.get("detail")
    if detail is not None:
        if isinstance(detail, str):
            dtext = detail
        else:
            try:
                dtext = json.dumps(detail, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                dtext = str(detail)
        lines.append(f"Detail     : {dtext}")
    ctx = env.get("context")
    if ctx:
        lines.append(f"Context    : {json.dumps(ctx, ensure_ascii=False)}")
    lines.append("-" * 47)
    return "\n".join(lines)


def error_code_info(code: str) -> Optional[dict[str, str]]:
    return ERROR_CODES.get(code) or ERROR_CODES.get(_DEFAULT_CODE)


# ---------------------------------------------------------------------------
# stdout/stderr helpers + exit codes.
# ---------------------------------------------------------------------------


def eprint(msg: str = "") -> None:
    """Diagnostics / progress → stderr (never pollute stdout with results)."""
    print(msg, file=sys.stderr, flush=True)


def emit(
    env: dict[str, Any],
    *,
    json_mode: bool = False,
    exit_code: Optional[int] = None,
) -> None:
    """Print the envelope to stdout (JSON or block) and optionally exit."""
    if json_mode:
        print(render_json(env))
    else:
        print(render_block(env))
    if exit_code is not None:
        raise SystemExit(exit_code)


def exit_code_for_status(status: str) -> int:
    if status == STATUS_ERROR:
        return _EXIT_ERR
    if status == STATUS_WARNING:
        return _EXIT_ERR
    return _EXIT_OK


# ---------------------------------------------------------------------------
# Signal handling (headless only).
# ---------------------------------------------------------------------------

_JSON_MODE = {"value": False}
_HANDLERS: list = []


def install_signal_handlers(json_mode: bool = False) -> None:
    """On SIGINT/SIGTERM emit a final structured envelope then exit 130.

    ``json_mode`` is captured so the final message matches the output format.
    Best-effort: skipped when already installing in this process.
    """
    _JSON_MODE["value"] = json_mode

    def _handler(signum: int, _frame: Any) -> None:
        env = make_envelope(
            ok=False,
            error_code="MAE-9000",
            message=f"Interrupted by signal {signum}",
            context={"signal": signal.Signals(signum).name},
        )
        if _JSON_MODE["value"]:
            print(render_json(env))
        else:
            print(render_block(env), file=sys.stderr)
        sys.exit(_EXIT_INTERRUPTED)

    if _HANDLERS:
        return
    _HANDLERS.append(_handler)
    try:
        signal.signal(signal.SIGINT, _handler)
        signal.signal(signal.SIGTERM, _handler)
    except (ValueError, OSError):
        pass  # not main thread — skip


def restore_signal_handlers() -> None:
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, signal.SIG_DFL)
        except (ValueError, OSError):
            pass
    _HANDLERS.clear()