"""
Host-side tools for interactive chat (files, dirs, graphify, terminal).

The model emits JSON tool calls in fenced ```tool blocks; this module parses
and executes them under the project root with safety rails.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from cli_app.output import now_utc

logger = logging.getLogger(__name__)

# Package checkout (MultiAgent source + its graphify-out).
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
# Tests may reassign ROOT; production keeps it equal to PACKAGE_ROOT.
ROOT = PACKAGE_ROOT


def work_root() -> Path:
    """Directory where multiagent was *launched* (user project).

    File writes, shell, venv, and pip target this path — not the MultiAgent
    install tree — so ``hola_mundo.py`` lands in the user's cwd.
    """
    # When tests monkeypatch ROOT to a temp dir, treat that as the work root.
    if ROOT.resolve() != PACKAGE_ROOT.resolve():
        return ROOT.resolve()
    return Path.cwd().resolve()

# Tools that never mutate the system — no user approval required.
# Names aligned with OpenCode-style agents (read/list/grep/glob/bash…).
READ_TOOLS = frozenset(
    {
        "graphify_query",
        "list_dir",
        "list",  # alias
        "read_file",
        "read",  # alias
        "grep",
        "glob",
        "webfetch",
        "search_web",
        "git_log",
        "git_diff",
        "run_tests",
        "toolbox_query",
        "toolbox",  # alias
    }
)
# Mutating / shell tools — need approval unless always_approve.
WRITE_TOOLS = frozenset(
    {
        "write_file",
        "write",  # alias
        "edit_file",
        "edit",  # alias
        "apply_patch",
        "run_terminal",
        "bash",  # alias (OpenCode)
        "graphify_update",
        "create_venv",
        "pip_install",
        "run_pipeline",  # WAVE-17: heavy, may write files / spend quota
    }
)

# Normalize aliases → canonical name
_TOOL_ALIASES = {
    "list": "list_dir",
    "read": "read_file",
    "write": "write_file",
    "edit": "edit_file",
    "bash": "run_terminal",
    "shell": "run_terminal",
    "terminal": "run_terminal",
    "toolbox": "toolbox_query",
    "cli_tools": "toolbox_query",
}

_SKIP_DIR = {
    ".git",
    "venv",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
_SECRET_NAMES = {".env", ".env.local", ".env.production", "secrets.yaml", "credentials.json"}
_BLOCKED_CMD = re.compile(
    r"(rm\s+-rf\s+/|sudo\s+|mkfs|dd\s+if=|:(){:|:&};|"
    r"curl\s+[^\n]*\|\s*(ba)?sh|wget\s+[^\n]*\|\s*(ba)?sh|"
    r">\s*/etc/|chmod\s+-R\s+777\s+/|"
    r"format\s+[a-z]:|\bcacls|\bdeltree\s+[a-z]:|"
    r"net\s+user\s+\w+\s+\w+\s+/add|net\s+localgroup\s+administrators\s+\w+\s+/add|"
    r"reg\s+(add|delete|import)\b|"
    r"del\s+/(f|s|q)|rd\s+/s)",  # Windows destructive tools (incl. del /f /s /q, rd /s)
    re.I,
)

# ```tool\n{json}\n```  or  <tool name="x">{...}</tool>
_FENCE_TOOL_RE = re.compile(
    r"```tool\s*\n(?P<body>.*?)```",
    re.I | re.S,
)
_XML_TOOL_RE = re.compile(
    r"<tool(?:_call)?\s+name=[\"'](?P<name>[a-z_]+)[\"']\s*>\s*(?P<body>.*?)\s*</tool(?:_call)?>",
    re.I | re.S,
)


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    raw: str = ""


@dataclass
class ToolResult:
    name: str
    ok: bool
    output: str
    skipped: bool = False
    # WAVE-17 structured-output fields (additive)
    error_code: Optional[str] = None
    timestamp: str = field(default_factory=lambda: now_utc())


def tools_help_text() -> str:
    return """\
Available tools (OpenCode-style + MultiAgent). Emit ONE tool per turn when it
needs approval (write/bash/pip). Read tools may be batched.

```tool
{"name": "graphify_query", "args": {"query": "agents package"}}
```

```tool
{"name": "list_dir", "args": {"path": "agents"}}
```

```tool
{"name": "read_file", "args": {"path": "agents/planner.py"}}
```

```tool
{"name": "grep", "args": {"pattern": "def plan_", "path": "agents", "glob": "*.py"}}
```

```tool
{"name": "glob", "args": {"pattern": "agents/**/*.py"}}
```

```tool
{"name": "write_file", "args": {"path": "hola_mundo.py", "content": "print('Hola mundo')\\n"}}
```

```tool
{"name": "edit_file", "args": {"path": "file.py", "old": "exact old", "new": "replacement"}}
```

```tool
{"name": "apply_patch", "args": {"patch": "*** Begin Patch\\n*** Update File: a.py\\n@@\\n-old\\n+new\\n*** End Patch"}}
```

```tool
{"name": "run_terminal", "args": {"command": "ls -la agents", "timeout": 60}}
```
(aliases: bash, shell — same as run_terminal)

```tool
{"name": "create_venv", "args": {"path": ".venv"}}
```

```tool
{"name": "pip_install", "args": {"packages": ["requests"], "venv": ".venv"}}
```

```tool
{"name": "webfetch", "args": {"url": "https://example.com", "max_chars": 8000}}
```

```tool
{"name": "search_web", "args": {"query": "LangGraph 0.3 release notes", "max_chars": 4000}}
```
(no API key; DuckDuckGo lite. READ tool — no approval.)

```tool
{"name": "git_log", "args": {"count": 20, "path": "cli_app"}}
```

```tool
{"name": "git_diff", "args": {"ref": "HEAD~2", "path": "cli_app/tools.py"}}
```
(omit ref = unstaged changes. READ tools — no approval.)

```tool
{"name": "run_tests", "args": {"path": "tests/test_tools.py", "timeout": 300}}
```
(omit path = full suite. Uses the project venv if present. READ tool — no approval.)

```tool
{"name": "graphify_update", "args": {}}
```

```tool
{"name": "toolbox_query", "args": {"query": "search code fast", "mode": "suggest"}}
```
modes: suggest (default) | doctor | search | show | alt | runtime
(alias: toolbox)

```tool
{"name": "run_pipeline", "args": {"task": "research coqui vivo v5 then build a page", "use_gpt_researcher": false}}
```
(Cheap reads only: planner + vibe/research executed here, may write files and
spend quota. REQUIRES approval.) Optional args: provider / model (planner override).

Modern catalog (automatic):
- list_dir → eza/tre when installed (else Python listing)
- grep → rg (ripgrep)
- glob → fd when installed (else pathlib)
- read_file → bat -p when installed (else plain read)
- run_terminal soft-upgrades ls/cat/grep/df/du/ps/… when modern bins exist
Prefer host tools over inventing shell; for ad-hoc shell use modern names.

Rules:
- Use tools for real repo facts. Never invent tool output or shell results.
- agents/ is the Python package; .agents/ is editor rules only.
- Creating files: always call write_file (do not only describe the file).
- write/edit/bash/venv/pip paths are relative to the user's launch cwd
  (where they started multiagent), NOT the MultiAgent install directory.
- Prefer create_venv + pip_install for Python packages.
- Mutating tools (write/edit/bash/pip/venv) require user approval unless always-approve.
- Do not invent citations like 【file†L1】. Do not use "→ skipped:".
"""


def parse_tool_calls(text: str) -> list[ToolCall]:
    """Extract tool calls from model output."""
    calls: list[ToolCall] = []
    seen: set[str] = set()

    def _add(name: str, args: dict[str, Any], raw: str) -> None:
        name = (name or "").strip().lower()
        name = _TOOL_ALIASES.get(name, name)
        if not name:
            return
        key = f"{name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
        if key in seen:
            return
        seen.add(key)
        calls.append(ToolCall(name=name, args=args or {}, raw=raw))

    for m in _FENCE_TOOL_RE.finditer(text or ""):
        body = m.group("body").strip()
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            # try to salvage single-quoted JSON-ish
            try:
                data = json.loads(body.replace("'", '"'))
            except Exception:
                continue
        if isinstance(data, dict):
            _add(str(data.get("name") or ""), dict(data.get("args") or {}), m.group(0))

    for m in _XML_TOOL_RE.finditer(text or ""):
        body = m.group("body").strip()
        args: dict[str, Any] = {}
        if body:
            try:
                parsed = json.loads(body)
                if isinstance(parsed, dict):
                    args = parsed
            except Exception:
                args = {"raw": body}
        _add(m.group("name"), args, m.group(0))

    return calls


def strip_tool_blocks(text: str) -> str:
    """Remove tool call fences/XML from visible assistant text."""
    out = _FENCE_TOOL_RE.sub("", text or "")
    out = _XML_TOOL_RE.sub("", out)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out


# Venv dirs are allowed for create_venv / pip_install / run_terminal, but not
# for casual write_file of secrets. Track "venv-allowed" separately.
_VENV_DIR_NAMES = frozenset({"venv", ".venv", "env", ".env-venv"})


def _safe_under_root(
    path: Path, *, allow_venv: bool = False, base: Optional[Path] = None
) -> Path:
    root = (base or work_root()).resolve()
    resolved = path.resolve()
    if not str(resolved).startswith(str(root)):
        raise PermissionError(f"path escapes work root: {path}")
    if resolved.name in _SECRET_NAMES:
        raise PermissionError(f"refusing secret file: {resolved.name}")
    if not allow_venv:
        for p in resolved.parts:
            if p in _SKIP_DIR and p not in root.parts:
                raise PermissionError(f"refusing path under {p}")
    else:
        # Still block other noise dirs, but allow venv/.venv
        for p in resolved.parts:
            if p in _SKIP_DIR and p not in _VENV_DIR_NAMES and p not in root.parts:
                raise PermissionError(f"refusing path under {p}")
    return resolved


def _resolve_rel(rel: str, *, allow_venv: bool = False, base: Optional[Path] = None) -> Path:
    """Resolve a relative path under the launch cwd (work root), not package root."""
    root = (base or work_root()).resolve()
    raw = (rel or "").strip()
    # Only strip a single leading "./" prefix — do NOT use lstrip("./") which
    # would turn ".venv" into "venv".
    if raw.startswith("./"):
        raw = raw[2:]
    raw = raw.strip("/")
    if not raw or raw in (".",):
        return root
    return _safe_under_root(root / raw, allow_venv=allow_venv, base=root)


def _venv_python(venv_path: Path) -> Path:
    """Return python executable inside a venv (POSIX or Windows)."""
    unix = venv_path / "bin" / "python"
    win = venv_path / "Scripts" / "python.exe"
    if unix.exists():
        return unix
    if win.exists():
        return win
    return unix  # default expectation on Linux


def _venv_pip(venv_path: Path) -> list[str]:
    """Return argv prefix to run pip from a venv."""
    py = _venv_python(venv_path)
    return [str(py), "-m", "pip"]


def _looks_like_pip_or_venv(cmd: str) -> bool:
    c = (cmd or "").lower()
    return any(
        k in c
        for k in (
            "pip install",
            "pip3 install",
            "python -m pip",
            "python3 -m pip",
            " -m venv",
            "virtualenv ",
            "uv pip",
            "uv venv",
            "poetry add",
            "poetry install",
        )
    )


def _guarded_shell(
    cmd: str,
    *,
    timeout: int = 60,
    no_upgrade: bool = False,
    raw: bool = False,
) -> tuple[Optional[int], str]:
    """WAVE-04 hardened shell runner shared by run_terminal and the read-only
    shell tools (git_log, git_diff, run_tests).

    Applies the same ``_BLOCKED_CMD`` denylist + modern-catalog soft-upgrade as
    ``run_terminal`` so new tools inherit the hardened path instead of calling
    ``subprocess`` directly. Returns ``(None, reason)`` for a blocked command,
    else ``(returncode, formatted_body)``.
    """
    from core.toolbox import soft_rewrite_shell_command

    if _BLOCKED_CMD.search(cmd):
        return None, f"blocked dangerous command: {cmd[:80]}"
    upgrade_note = None
    if not no_upgrade and not raw:
        cmd, upgrade_note = soft_rewrite_shell_command(cmd)
    proc = subprocess.run(
        cmd,
        shell=True,
        cwd=str(work_root()),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = (proc.stdout or "")[-6000:]
    err = (proc.stderr or "")[-2000:]
    body = out
    if err:
        body = (body + "\n[stderr]\n" + err).strip()
    if not body:
        body = f"(exit {proc.returncode}, no output)"
    else:
        body = f"(exit {proc.returncode})\n{body}"
    if upgrade_note:
        body = f"[{upgrade_note}]\n{body}"
    return proc.returncode, body


def _find_test_python() -> str:
    """Pick a Python interpreter that can run the project's test suite."""
    for cand in (
        work_root() / "venv" / "bin" / "python",
        work_root() / ".venv" / "bin" / "python",
    ):
        if cand.exists():
            return str(cand)
    return "python3"


def _run_pipeline_tool(args: dict[str, Any], ctx: Optional[dict[str, Any]]) -> ToolResult:
    """WAVE-17: run the planner -> execute_plan flow inside a chat turn.

    Heavy tool (approval-required, listed in WRITE_TOOLS). Passes the recent
    conversation to the planner as chat context so /do-style intent survives.
    Progress is forwarded to the caller's progress callback (usually stderr).
    """
    task = str(args.get("task") or args.get("prompt") or "").strip()
    if not task:
        return ToolResult(
            "run_pipeline",
            False,
            "run_pipeline requires a 'task' argument",
            error_code="MAE-3100",
        )
    chat_context = ""
    progress = None
    session = (ctx or {}).get("session")
    if session is not None:
        try:
            from cli_app.commands import _chat_context_for_planner

            chat_context = _chat_context_for_planner(session)
        except Exception:
            chat_context = ""
        progress = (ctx or {}).get("progress")

    from cli_app.pipeline_cli import run_pipeline

    use_gpt = bool(args.get("use_gpt_researcher"))
    provider = args.get("provider") or None
    model = args.get("model") or None
    try:
        out = run_pipeline(
            task,
            use_gpt_researcher=use_gpt,
            provider=provider,
            model=model,
            progress=progress,
            chat_context=chat_context,
        )
    except Exception as exc:
        return ToolResult(
            "run_pipeline", False, f"run_pipeline failed: {exc}", error_code="MAE-2000"
        )
    body = (out.get("text") or "")[:3000]
    if out.get("ok"):
        return ToolResult("run_pipeline", True, f"[run_pipeline OK]\n{body}")
    return ToolResult(
        "run_pipeline",
        False,
        f"[run_pipeline FAIL]\n{body}",
        error_code=out.get("error_code") or "MAE-2000",
    )


def exec_tool(name: str, args: dict[str, Any], *, ctx: Optional[dict[str, Any]] = None) -> ToolResult:
    """Execute a single tool; never raises — returns ToolResult.

    *ctx* (WAVE-17) is an optional call-context dict ``{"session": …, "progress": …}``
    supplied by the agent loop; only ``run_pipeline`` consumes it.
    """
    name = (name or "").strip().lower()
    name = _TOOL_ALIASES.get(name, name)
    try:
        if name == "run_pipeline":
            return _run_pipeline_tool(args, ctx)

        if name == "graphify_query":
            from cli_app.graph_rag import query_graph

            q = str(args.get("query") or args.get("q") or "").strip()
            if not q:
                return ToolResult(name, False, "query required")
            budget = int(args.get("budget") or 1200)
            out = query_graph(q, budget=budget)
            return ToolResult(name, True, out or "(empty graph result)")

        if name == "toolbox_query":
            from core.toolbox import query_for_agent

            q = str(
                args.get("query")
                or args.get("q")
                or args.get("task")
                or args.get("question")
                or ""
            ).strip()
            mode = str(args.get("mode") or args.get("action") or "suggest").strip()
            if not q and mode not in ("doctor", "status", "runtime", "available", "caps", "capabilities"):
                return ToolResult(
                    name,
                    False,
                    "query required (or mode=doctor/runtime)",
                )
            if not q and mode in ("doctor", "status"):
                q = "core"
            if not q and mode in ("runtime", "available", "caps", "capabilities"):
                q = "runtime"
            limit = int(args.get("limit") or 6)
            out = query_for_agent(q, mode=mode, limit=limit)
            if len(out) > 6000:
                out = out[:6000] + "\n…[truncated]"
            return ToolResult(name, True, out or "(empty)")

        if name == "graphify_update":
            proc = subprocess.run(
                ["graphify", "update", "."],
                cwd=str(work_root()),
                capture_output=True,
                text=True,
                timeout=180,
            )
            out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
            ok = proc.returncode == 0
            return ToolResult(name, ok, out[:4000] or f"exit {proc.returncode}")

        if name == "list_dir":
            from cli_app.context_tools import list_project_dir
            from core.toolbox import modern_list_dir

            path = str(args.get("path") or args.get("dir") or ".").strip() or "."
            tree = bool(args.get("tree") or args.get("recursive"))
            p = _resolve_rel(path)
            # Prefer modern catalog tools (eza / tre) when on PATH.
            if p.is_dir():
                modern = modern_list_dir(p, cwd=work_root(), tree=tree)
                if modern:
                    backend, body = modern
                    try:
                        rel = str(p.relative_to(work_root()))
                    except ValueError:
                        rel = str(p)
                    # Cap output size for the model
                    lines = body.splitlines()
                    if len(lines) > 120:
                        body = "\n".join(lines[:120]) + f"\n…[{len(lines) - 120} more lines]"
                    return ToolResult(
                        name,
                        True,
                        f"--- DIR: {rel}/  [via {backend}] ---\n{body}",
                    )
            out = list_project_dir(path, root=work_root())
            if not out:
                # try raw relative
                if p.is_dir():
                    lines = []
                    for item in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))[
                        :50
                    ]:
                        if item.name in _SKIP_DIR:
                            continue
                        kind = "dir" if item.is_dir() else "file"
                        lines.append(f"  [{kind}] {item.name}")
                    try:
                        rel = str(p.relative_to(work_root()))
                    except ValueError:
                        rel = str(p)
                    out = f"--- DIR: {rel}/  [via python] ---\n" + (
                        "\n".join(lines) or "  (empty)"
                    )
                else:
                    out = f"(not a directory or not found: {path})"
            elif "[via " not in out:
                out = out.replace("--- DIR:", "--- DIR:", 1)
                # annotate python path listing from context_tools if plain
                if out.startswith("--- DIR:"):
                    out = out.replace("--- DIR:", "--- DIR:", 1)
                    # insert backend tag after first line header
                    first, _, rest = out.partition("\n")
                    if "[via " not in first:
                        first = first.rstrip() + "  [via python]"
                        out = first + ("\n" + rest if rest else "")
            return ToolResult(name, True, out)

        if name == "read_file":
            from core.toolbox import modern_view_file

            path = str(args.get("path") or "").strip()
            if not path:
                return ToolResult(name, False, "path required")
            p = _resolve_rel(path)
            if not p.is_file():
                return ToolResult(name, False, f"not a file: {path}")
            if p.stat().st_size > 200_000:
                return ToolResult(name, False, "file too large (>200KB)")
            try:
                rel = str(p.relative_to(work_root()))
            except ValueError:
                rel = str(p)
            modern = modern_view_file(p, cwd=work_root(), max_chars=12000)
            if modern:
                backend, text = modern
                return ToolResult(
                    name, True, f"--- FILE: {rel}  [via {backend}] ---\n{text}"
                )
            text = p.read_text(encoding="utf-8", errors="replace")
            if len(text) > 12000:
                text = text[:12000] + "\n…[truncated]"
            return ToolResult(name, True, f"--- FILE: {rel}  [via python] ---\n{text}")

        if name == "write_file":
            path = str(args.get("path") or "").strip()
            content = args.get("content")
            if content is None:
                content = args.get("text")
            if not path or content is None:
                return ToolResult(name, False, "path and content required")
            p = _resolve_rel(path)
            if p.suffix.lower() in {".pyc", ".so", ".dll", ".exe", ".bin", ".db"}:
                return ToolResult(name, False, f"refusing binary-like extension: {p.suffix}")
            p.parent.mkdir(parents=True, exist_ok=True)
            text = str(content)
            if len(text) > 500_000:
                return ToolResult(name, False, "content too large")
            p.write_text(text, encoding="utf-8")
            try:
                rel = str(p.relative_to(work_root()))
            except ValueError:
                rel = str(p)
            return ToolResult(name, True, f"wrote {rel} ({len(text)} chars)")

        if name == "edit_file":
            path = str(args.get("path") or "").strip()
            old = args.get("old")
            if old is None:
                old = args.get("old_string")
            new = args.get("new")
            if new is None:
                new = args.get("new_string")
            if not path or old is None or new is None:
                return ToolResult(name, False, "path, old, and new required")
            p = _resolve_rel(path)
            if not p.is_file():
                return ToolResult(name, False, f"not a file: {path}")
            text = p.read_text(encoding="utf-8", errors="replace")
            old_s, new_s = str(old), str(new)
            if old_s not in text:
                return ToolResult(name, False, "old string not found in file")
            count = text.count(old_s)
            if count > 1 and not args.get("replace_all"):
                return ToolResult(
                    name,
                    False,
                    f"old string matches {count} times; set replace_all=true or make old unique",
                )
            if args.get("replace_all"):
                updated = text.replace(old_s, new_s)
            else:
                updated = text.replace(old_s, new_s, 1)
            p.write_text(updated, encoding="utf-8")
            try:
                rel = str(p.relative_to(work_root()))
            except ValueError:
                rel = str(p)
            return ToolResult(name, True, f"edited {rel}")

        if name == "create_venv":
            import sys

            rel = str(args.get("path") or args.get("venv") or ".venv").strip() or ".venv"
            # Force under project; allow venv dir names
            p = _resolve_rel(rel, allow_venv=True)
            if p.exists() and not (p / "pyvenv.cfg").exists() and any(p.iterdir()):
                return ToolResult(
                    name,
                    False,
                    f"path exists and is not an empty/venv dir: {rel}",
                )
            python = str(args.get("python") or sys.executable)
            # Only allow system/project pythons by name (no arbitrary binary path escape)
            cmd = [python, "-m", "venv", str(p)]
            timeout = int(args.get("timeout") or 120)
            timeout = max(30, min(timeout, 300))
            proc = subprocess.run(
                cmd,
                cwd=str(work_root()),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
            try:
                rel_out = str(p.relative_to(work_root()))
            except ValueError:
                rel_out = str(p)
            if proc.returncode != 0:
                return ToolResult(
                    name,
                    False,
                    f"venv failed (exit {proc.returncode}) for {rel_out}\n{out[:3000]}",
                )
            py = _venv_python(p)
            return ToolResult(
                name,
                True,
                f"created venv at {rel_out}\npython: {py}\n{out[:1500]}".strip(),
            )

        if name == "pip_install":
            packages = args.get("packages") or args.get("package") or args.get("reqs")
            if packages is None:
                return ToolResult(name, False, "packages required (list or string)")
            if isinstance(packages, str):
                # "requests httpx" or "requests,httpx"
                pkgs = [p.strip() for p in re.split(r"[\s,]+", packages) if p.strip()]
            elif isinstance(packages, (list, tuple)):
                pkgs = [str(p).strip() for p in packages if str(p).strip()]
            else:
                return ToolResult(name, False, "packages must be a list or string")
            if not pkgs:
                return ToolResult(name, False, "empty package list")
            # Basic package name safety (no shell metachar injection)
            for pkg in pkgs:
                if not re.match(r"^[A-Za-z0-9_.\[\]<>=!~,-]+$", pkg):
                    return ToolResult(name, False, f"invalid package token: {pkg!r}")

            rel = str(args.get("venv") or args.get("path") or ".venv").strip() or ".venv"
            venv_path = _resolve_rel(rel, allow_venv=True)
            if not (venv_path / "pyvenv.cfg").exists():
                # Auto-create venv if missing
                create_res = exec_tool("create_venv", {"path": rel})
                if not create_res.ok:
                    return ToolResult(
                        name,
                        False,
                        f"venv missing and create failed:\n{create_res.output}",
                    )

            pip_cmd = _venv_pip(venv_path)
            cmd = pip_cmd + ["install"]
            if args.get("upgrade"):
                cmd.append("--upgrade")
            if args.get("requirements") or args.get("requirement"):
                req = str(args.get("requirements") or args.get("requirement"))
                req_path = _resolve_rel(req, allow_venv=False)
                if not req_path.is_file():
                    return ToolResult(name, False, f"requirements file not found: {req}")
                cmd.extend(["-r", str(req_path)])
            else:
                cmd.extend(pkgs)

            timeout = int(args.get("timeout") or 300)
            timeout = max(60, min(timeout, 900))
            proc = subprocess.run(
                cmd,
                cwd=str(work_root()),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            out = (proc.stdout or "")[-5000:]
            err = (proc.stderr or "")[-2000:]
            body = out
            if err:
                body = (body + "\n[stderr]\n" + err).strip()
            try:
                rel_v = str(venv_path.relative_to(work_root()))
            except ValueError:
                rel_v = str(venv_path)
            header = f"pip install into {rel_v} (exit {proc.returncode})\ncmd: {' '.join(cmd)}\n"
            return ToolResult(name, proc.returncode == 0, header + (body or "(no output)"))

        if name == "grep":
            from core.toolbox import modern_search_text

            pattern = str(args.get("pattern") or args.get("regex") or args.get("q") or "")
            if not pattern:
                return ToolResult(name, False, "pattern required")
            path = str(args.get("path") or ".").strip() or "."
            base = _resolve_rel(path, allow_venv=False)
            gglob = str(args.get("glob") or args.get("include") or "").strip()
            max_hits = int(args.get("max_hits") or 40)
            modern = modern_search_text(
                pattern,
                base,
                glob=gglob,
                max_hits=max_hits,
                cwd=work_root(),
            )
            if modern:
                backend, body = modern
                header = f"[via {backend}] "
                return ToolResult(name, True, header + (body or "(no matches)"))
            # fallback to python walk if rg missing
            hits: list[str] = []
            try:
                for p in base.rglob(gglob or "*") if base.is_dir() else [base]:
                    if not p.is_file():
                        continue
                    if any(part in _SKIP_DIR for part in p.parts):
                        continue
                    try:
                        text = p.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        continue
                    for i, line in enumerate(text.splitlines(), 1):
                        if re.search(pattern, line):
                            try:
                                rel = p.relative_to(work_root())
                            except ValueError:
                                rel = p
                            hits.append(f"{rel}:{i}:{line[:200]}")
                            if len(hits) >= max_hits:
                                break
                    if len(hits) >= max_hits:
                        break
            except Exception as exc:
                return ToolResult(name, False, f"grep fallback failed: {exc}")
            body = "\n".join(hits) if hits else "(no matches)"
            return ToolResult(name, True, f"[via python] {body}")

        if name == "glob":
            from core.toolbox import modern_find_files

            pattern = str(args.get("pattern") or args.get("glob") or "**/*").strip()
            path = str(args.get("path") or ".").strip() or "."
            base = _resolve_rel(path, allow_venv=False)
            max_hits = int(args.get("max_hits") or 80)
            root_base = base if base.is_dir() else base.parent
            modern = modern_find_files(
                pattern, root_base, cwd=work_root(), max_hits=max_hits
            )
            # Prefer fd hits; if fd finds nothing, fall back to pathlib (fd and
            # pathlib-style globs like agents/**/*.py are not always equivalent).
            if modern:
                backend, body = modern
                if body and body.strip() and body.strip() != "(no matches)":
                    return ToolResult(name, True, f"[via {backend}]\n{body}")
            matches: list[str] = []
            try:
                for p in sorted(root_base.glob(pattern)):
                    if any(part in _SKIP_DIR for part in p.parts):
                        continue
                    try:
                        rel = str(p.relative_to(work_root()))
                    except ValueError:
                        rel = str(p)
                    matches.append(rel)
                    if len(matches) >= max_hits:
                        break
            except Exception as exc:
                return ToolResult(name, False, f"glob failed: {exc}")
            body = "\n".join(matches) if matches else "(no matches)"
            return ToolResult(name, True, f"[via python]\n{body}")

        if name == "apply_patch":
            # Minimal support: *** Update File: path\n then -/+ lines (simple)
            patch = str(args.get("patch") or args.get("diff") or "")
            if not patch.strip():
                return ToolResult(name, False, "patch required")
            # Prefer edit_file-style when possible; try path extraction
            m = re.search(r"(?:\*\*\*\s*Update File:\s*|--- a/|\+\+\+ b/)([^\n]+)", patch)
            if not m:
                return ToolResult(
                    name,
                    False,
                    "could not parse target file from patch; use edit_file instead",
                )
            path = m.group(1).strip()
            p = _resolve_rel(path)
            if not p.is_file():
                return ToolResult(name, False, f"not a file: {path}")
            # Extract first hunk -/+ pairs naively
            old_lines, new_lines = [], []
            for line in patch.splitlines():
                if line.startswith("---") or line.startswith("+++") or line.startswith("@@"):
                    continue
                if line.startswith("***"):
                    continue
                if line.startswith("-") and not line.startswith("---"):
                    old_lines.append(line[1:])
                elif line.startswith("+") and not line.startswith("+++"):
                    new_lines.append(line[1:])
            if not old_lines and not new_lines:
                return ToolResult(name, False, "empty hunk")
            text = p.read_text(encoding="utf-8", errors="replace")
            old = "\n".join(old_lines)
            new = "\n".join(new_lines)
            if old and old not in text:
                return ToolResult(name, False, "old hunk not found; use edit_file with exact text")
            if old:
                text = text.replace(old, new, 1)
            else:
                text = text + ("\n" if not text.endswith("\n") else "") + new
            p.write_text(text, encoding="utf-8")
            try:
                rel = str(p.relative_to(work_root()))
            except ValueError:
                rel = str(p)
            return ToolResult(name, True, f"patched {rel}")

        if name == "webfetch":
            # WAVE-13: route through the cache-aware fetch_url + html_to_text so
            # the model reads readable page text, not raw truncated HTML bytes.
            from agents.deep_research.contracts import SourceResultStatus
            from agents.deep_research.source_fetch import fetch_url

            url = str(args.get("url") or "").strip()
            if not url.startswith("http://") and not url.startswith("https://"):
                return ToolResult(name, False, "url must be http(s)")
            max_chars = int(args.get("max_chars") or 8000)
            max_chars = max(500, min(max_chars, 50000))
            src = fetch_url(
                url,
                timeout=20,
                max_chars=max_chars,
                extract_signals=False,
                follow_outbound=False,
            )
            if src.status is SourceResultStatus.SUCCESS and src.text.strip():
                return ToolResult(
                    name, True, f"URL: {url}\n\n{src.text[:max_chars]}"
                )
            reason = src.error or src.status.value
            return ToolResult(name, False, f"webfetch failed: {reason}")

        if name == "run_terminal":
            cmd = str(args.get("command") or args.get("cmd") or "").strip()
            if not cmd:
                return ToolResult(name, False, "command required")
            # Longer default for pip/venv style commands
            default_to = 300 if _looks_like_pip_or_venv(cmd) else 60
            timeout = int(args.get("timeout") or default_to)
            timeout = max(5, min(timeout, 900))
            rc, body = _guarded_shell(
                cmd,
                timeout=timeout,
                no_upgrade=bool(args.get("no_upgrade")),
                raw=bool(args.get("raw")),
            )
            if rc is None:
                return ToolResult(name, False, body)
            return ToolResult(name, rc == 0, body)

        if name in ("git_log", "git_diff"):
            # READ tools: structured git inspection without run_terminal approval.
            import shlex

            path = str(args.get("path") or args.get("directory") or "").strip()
            safe_path = f" -- {shlex.quote(path)}" if path else ""
            if name == "git_log":
                count = max(1, min(int(args.get("count") or 20), 200))
                cmd = f"git log --oneline --decorate -n {count}{safe_path}"
            else:
                ref = str(args.get("ref") or "").strip()
                safe_ref = f" {shlex.quote(ref)}" if ref else ""
                cmd = f"git diff{safe_ref}{safe_path}"
            rc, body = _guarded_shell(cmd, timeout=30, no_upgrade=True)
            if rc is None:
                return ToolResult(name, False, body)
            return ToolResult(name, rc == 0, body)

        if name == "run_tests":
            # READ-adjacent: runs the project suite via the hardened path so a
            # non-mutating test run needs no approval prompt.
            target = str(args.get("path") or args.get("target") or "").strip()
            timeout = max(30, min(int(args.get("timeout") or 300), 900))
            py = _find_test_python()
            pytest_cmd = f"{py} -m pytest -q"
            if target:
                import shlex

                pytest_cmd += f" {shlex.quote(target)}"
            rc, body = _guarded_shell(pytest_cmd, timeout=timeout, no_upgrade=True)
            if rc is None:
                return ToolResult(name, False, body)
            summary = "PASSED" if rc == 0 else "FAILED"
            return ToolResult(name, rc == 0, f"tests: {summary} (exit {rc})\n{body[-3000:]}")

        if name == "search_web":
            # READ tool: surfaces WAVE-11's DDG search chain to the chat agent.
            from agents.deep_research.source_fetch import search_duckduckgo

            q = str(args.get("query") or args.get("q") or "").strip()
            if not q:
                return ToolResult(name, False, "query required")
            max_chars = int(args.get("max_chars") or 4000)
            max_chars = max(500, min(max_chars, 20000))
            text = search_duckduckgo(q, max_chars=max_chars)
            if not text:
                return ToolResult(
                    name, False, "search returned no results (or the search failed)"
                )
            return ToolResult(name, True, text)

        return ToolResult(name, False, f"unknown tool: {name}")
    except subprocess.TimeoutExpired:
        return ToolResult(name, False, "timeout")
    except Exception as exc:
        logger.exception("tool %s failed", name)
        return ToolResult(name, False, f"error: {exc}")


def needs_approval(name: str) -> bool:
    return name in WRITE_TOOLS


ApprovalFn = Callable[[ToolCall], str]
# returns: approve | approve_all | reject | reject_all | always


def run_tools(
    calls: list[ToolCall],
    *,
    approve: Optional[ApprovalFn] = None,
    always_approve: bool = False,
    one_mutating_at_a_time: bool = True,
    ctx: Optional[dict[str, Any]] = None,
) -> tuple[list[ToolResult], bool, bool]:
    """Run tools with optional per-command approval (no batch approve-all).

    Mutating tools are prompted one-by-one. Returns
    (results, always_approve_now, rejected_once).
    """
    results: list[ToolResult] = []
    always = always_approve
    rejected_once = False

    # Process read tools first freely; mutating one-by-one in order
    ordered = list(calls)
    for call in ordered:
        if needs_approval(call.name) and not always:
            decision = "approve"
            if approve is not None:
                try:
                    decision = (approve(call) or "reject").strip().lower()
                except Exception as exc:
                    results.append(
                        ToolResult(
                            call.name,
                            False,
                            f"approval error: {exc}",
                            skipped=True,
                            error_code="MAE-3000",
                        )
                    )
                    rejected_once = True
                    if one_mutating_at_a_time:
                        # skip remaining mutating tools in this batch
                        continue
                    continue
            if decision in ("always", "always_approve", "always-approve", "!"):
                always = True
                decision = "approve"
            elif decision in ("reject", "r", "no", "n"):
                results.append(
                    ToolResult(
                        call.name,
                        False,
                        "rejected by user",
                        skipped=True,
                        error_code="MAE-3000",
                    )
                )
                rejected_once = True
                continue
            if decision not in ("approve", "yes", "y", "a", "ok", "accept"):
                results.append(
                    ToolResult(
                        call.name,
                        False,
                        f"rejected ({decision})",
                        skipped=True,
                        error_code="MAE-3000",
                    )
                )
                rejected_once = True
                continue

        if ctx is None:
            results.append(exec_tool(call.name, call.args))
        else:
            results.append(exec_tool(call.name, call.args, ctx=ctx))

    return results, always, rejected_once

def format_command_header(call: ToolCall) -> str:
    """Human-readable one-line command for approval UI header."""
    n = call.name
    a = call.args or {}
    if n == "run_terminal":
        return str(a.get("command") or a.get("cmd") or "run_terminal")
    if n == "write_file":
        return f"write_file {a.get('path', '')}"
    if n == "edit_file":
        return f"edit_file {a.get('path', '')}"
    if n == "pip_install":
        pkgs = a.get("packages") or a.get("package") or ""
        return f"pip_install {pkgs} (venv={a.get('venv', '.venv')})"
    if n == "create_venv":
        return f"create_venv {a.get('path', '.venv')}"
    if n == "graphify_update":
        return "graphify update ."
    if n == "apply_patch":
        return f"apply_patch {str(a.get('patch', ''))[:60]}…"
    if n == "run_pipeline":
        return f"run_pipeline {str(a.get('task', ''))[:80]}"
    return f"{n} {json.dumps(a, ensure_ascii=False)[:120]}"


def format_tool_results(results: list[ToolResult]) -> str:
    parts = ["=== TOOL RESULTS ==="]
    for r in results:
        status = "ok" if r.ok else ("skipped" if r.skipped else "err")
        parts.append(f"[{status}] {r.name}\n{r.output}")
    parts.append("=== END TOOL RESULTS ===")
    return "\n\n".join(parts)
