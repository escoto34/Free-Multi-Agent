"""
Terminal toolbox catalog for MultiAgent.

Loads ``config/cli_toolbox.yaml`` and exposes:

- PATH probes (``which``) for doctor reports
- task-based suggestions
- free-text search
- profiles (core, git, docker, …)

Used by ``/tools`` slash commands, ``multiagent tools …`` outer CLI, and the
host chat tool ``toolbox_query`` — so the agent never invents tool names.

Runtime integration (chat host tools)
-------------------------------------
Capabilities map host intents (list dir, find files, search text, …) to the
first catalog tool installed on PATH. ``cli_app.tools`` prefers those binaries
automatically; shell commands may be softly rewritten (``ls``→``eza``, …).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CATALOG = PACKAGE_ROOT / "config" / "cli_toolbox.yaml"

# Extra common binary aliases when distros rename packages (e.g. Debian fd-find).
_BIN_FALLBACKS: dict[str, list[str]] = {
    "fd": ["fdfind", "fd"],
    "bat": ["batcat", "bat"],
    "rg": ["rg"],
    "delta": ["delta"],
    "rip": ["rip"],
}

# Host intent → ordered catalog tool ids (first installed wins).
CAPABILITY_PREFERENCE: dict[str, tuple[str, ...]] = {
    "list_dir": ("eza", "tre"),
    "find_files": ("fd",),
    "search_text": ("ripgrep",),
    "view_file": ("bat",),
    "disk_usage": ("dust", "dua-cli"),
    "disk_free": ("duf",),
    "processes": ("procs", "bottom", "btop"),
    "http": ("httpie", "xh"),
    "json": ("jq", "jless"),
    "yaml": ("yq", "dasel"),
    "git_ui": ("lazygit",),
    "docker_ui": ("lazydocker",),
    "safe_delete": ("rip2",),
    "replace_text": ("sd",),
    "watch_files": ("watchexec", "entr"),
    "diff": ("git-delta", "difftastic"),
}

# Soft shell rewrite: classic first token → modern (only simple leading cmds).
# Do NOT rewrite rm/cp/mv pipelines aggressively — different semantics.
_SHELL_SOFT_REWRITE: list[tuple[re.Pattern[str], str, list[str]]] = [
    # (match first token, tool_id, argv_prefix when replacing that token)
    (re.compile(r"^ls\b"), "eza", ["eza"]),
    (re.compile(r"^tree\b"), "tre", ["tre"]),
    (re.compile(r"^cat\b"), "bat", ["bat", "-p", "--color=never", "--style=plain"]),
    (re.compile(r"^grep\b"), "ripgrep", ["rg"]),
    (re.compile(r"^egrep\b"), "ripgrep", ["rg", "-E"]),
    (re.compile(r"^fgrep\b"), "ripgrep", ["rg", "-F"]),
    (re.compile(r"^df\b"), "duf", ["duf"]),
    (re.compile(r"^du\b"), "dust", ["dust"]),
    (re.compile(r"^ps\b"), "procs", ["procs"]),
    (re.compile(r"^dig\b"), "dog", ["dog"]),
    (re.compile(r"^nano\b"), "micro", ["micro"]),
    (re.compile(r"^top\b"), "btop", ["btop"]),
    (re.compile(r"^htop\b"), "btop", ["btop"]),
]


@dataclass(frozen=True)
class ToolEntry:
    id: str
    name: str
    bin: str
    category: str
    tags: tuple[str, ...]
    replaces: tuple[str, ...]
    description: str
    install: dict[str, str] = field(default_factory=dict)

    @property
    def bins_to_try(self) -> list[str]:
        extras = _BIN_FALLBACKS.get(self.bin, [])
        seen: list[str] = []
        for b in [self.bin, *extras]:
            if b and b not in seen:
                seen.append(b)
        return seen


@dataclass
class ProbeResult:
    tool: ToolEntry
    installed: bool
    resolved_bin: Optional[str] = None
    path: Optional[str] = None


@dataclass
class Catalog:
    version: int
    tools: list[ToolEntry]
    profiles: dict[str, dict[str, Any]]
    by_id: dict[str, ToolEntry] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.by_id = {t.id: t for t in self.tools}


def _as_str_tuple(val: Any) -> tuple[str, ...]:
    if not val:
        return ()
    if isinstance(val, str):
        return (val,)
    return tuple(str(x) for x in val)


def load_catalog(path: Optional[Path] = None) -> Catalog:
    """Load and validate the toolbox catalog YAML."""
    p = path or DEFAULT_CATALOG
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    tools_raw = raw.get("tools") or []
    tools: list[ToolEntry] = []
    for row in tools_raw:
        if not isinstance(row, dict):
            continue
        tid = str(row.get("id") or "").strip()
        if not tid:
            continue
        bin_name = str(row.get("bin") or tid).strip()
        install = row.get("install") or {}
        if not isinstance(install, dict):
            install = {}
        tools.append(
            ToolEntry(
                id=tid,
                name=str(row.get("name") or tid),
                bin=bin_name,
                category=str(row.get("category") or "general"),
                tags=_as_str_tuple(row.get("tags")),
                replaces=_as_str_tuple(row.get("replaces")),
                description=str(row.get("description") or "").strip(),
                install={str(k): str(v) for k, v in install.items()},
            )
        )
    profiles = raw.get("profiles") or {}
    if not isinstance(profiles, dict):
        profiles = {}
    return Catalog(
        version=int(raw.get("version") or 1),
        tools=tools,
        profiles=profiles,
    )


@lru_cache(maxsize=4)
def get_catalog(path_str: Optional[str] = None) -> Catalog:
    return load_catalog(Path(path_str) if path_str else None)


def reload_catalog() -> Catalog:
    get_catalog.cache_clear()
    return get_catalog()


def probe_tool(tool: ToolEntry) -> ProbeResult:
    """Check whether any of the tool's binaries is on PATH."""
    for b in tool.bins_to_try:
        found = shutil.which(b)
        if found:
            return ProbeResult(tool=tool, installed=True, resolved_bin=b, path=found)
    return ProbeResult(tool=tool, installed=False)


def probe_all(
    catalog: Optional[Catalog] = None,
    *,
    ids: Optional[Iterable[str]] = None,
) -> list[ProbeResult]:
    cat = catalog or get_catalog()
    if ids is None:
        tools = cat.tools
    else:
        want = {i.lower() for i in ids}
        tools = [t for t in cat.tools if t.id in want]
    return [probe_tool(t) for t in tools]


def list_profiles(catalog: Optional[Catalog] = None) -> list[dict[str, Any]]:
    cat = catalog or get_catalog()
    out: list[dict[str, Any]] = []
    for name, meta in sorted(cat.profiles.items()):
        ids = list(meta.get("tools") or [])
        out.append(
            {
                "name": name,
                "description": str(meta.get("description") or ""),
                "count": len(ids),
                "tools": ids,
            }
        )
    return out


def profile_tool_ids(profile: str, catalog: Optional[Catalog] = None) -> list[str]:
    cat = catalog or get_catalog()
    key = profile.strip().lower()
    if key in ("all", "*", "full"):
        return [t.id for t in cat.tools]
    meta = cat.profiles.get(key)
    if not meta:
        known = ", ".join(sorted(cat.profiles)) or "(none)"
        raise KeyError(f"Unknown profile {profile!r}. Known: {known}, all")
    return list(meta.get("tools") or [])


def format_install_hint(tool: ToolEntry) -> str:
    if not tool.install:
        return "(no install hint)"
    # Prefer common user managers first
    order = ("brew", "cargo", "pip", "apt", "npm", "go")
    parts: list[str] = []
    for k in order:
        if k in tool.install:
            pkg = tool.install[k]
            if k == "brew":
                parts.append(f"brew install {pkg}")
            elif k == "cargo":
                parts.append(f"cargo install {pkg}")
            elif k == "pip":
                parts.append(f"pip install {pkg}")
            elif k == "apt":
                parts.append(f"sudo apt install {pkg}")
            elif k == "npm":
                parts.append(f"npm i -g {pkg}")
            elif k == "go":
                parts.append(f"go install {pkg}")
    for k, v in tool.install.items():
        if k not in order:
            parts.append(f"{k}: {v}")
    return " · ".join(parts) if parts else "(no install hint)"


def doctor(
    profile: str = "core",
    *,
    catalog: Optional[Catalog] = None,
    show_installed: bool = True,
) -> str:
    """Human-readable doctor report for a profile (or all)."""
    cat = catalog or get_catalog()
    try:
        ids = profile_tool_ids(profile, cat)
    except KeyError as exc:
        return str(exc)

    # Preserve profile order; skip unknown ids quietly
    tools: list[ToolEntry] = []
    for i in ids:
        t = cat.by_id.get(i)
        if t:
            tools.append(t)

    results = [probe_tool(t) for t in tools]
    present = [r for r in results if r.installed]
    missing = [r for r in results if not r.installed]

    lines: list[str] = [
        f"Toolbox doctor — profile: {profile}",
        f"  catalog v{cat.version} · {len(results)} tools checked",
        f"  installed: {len(present)} · missing: {len(missing)}",
        "",
    ]
    if show_installed and present:
        lines.append("Installed:")
        for r in present:
            bin_s = r.resolved_bin or r.tool.bin
            lines.append(f"  ✔ {r.tool.name:16} ({bin_s})  {r.tool.description[:60]}")
        lines.append("")
    if missing:
        lines.append("Missing (suggested installs):")
        for r in missing:
            lines.append(f"  ✖ {r.tool.name:16}  {r.tool.description[:50]}")
            lines.append(f"      → {format_install_hint(r.tool)}")
        lines.append("")
    else:
        lines.append("Nothing missing for this profile. Nice.")
        lines.append("")

    if profile == "core":
        lines.append("Other profiles: " + ", ".join(sorted(cat.profiles)) + ", all")
        lines.append("  multiagent tools doctor --profile git")
        lines.append("  /tools doctor git")
    return "\n".join(lines).rstrip() + "\n"


_TASK_ALIASES: list[tuple[re.Pattern[str], list[str]]] = [
    # (pattern, tags or ids boost)
    (re.compile(r"\b(list|ls|dir|tree|archivos|listar)\b", re.I), ["ls", "tree", "files", "listing"]),
    (re.compile(r"\b(search|grep|buscar|find text|código|code search)\b", re.I), ["search", "grep", "code", "ast"]),
    (re.compile(r"\b(find file|find files|buscar archivo|locate)\b", re.I), ["find", "files", "search"]),
    (re.compile(r"\b(git|commit|branch|pr|pull request|merge)\b", re.I), ["git", "github", "gitlab", "diff", "tui"]),
    (re.compile(r"\b(docker|container|imagen|image layer)\b", re.I), ["docker", "containers", "images", "layers"]),
    (re.compile(r"\b(k8s|kubernetes|kubectl|pod|helm)\b", re.I), ["kubernetes", "k8s", "logs", "charts"]),
    (re.compile(r"\b(disk|disco|du |df |espacio|storage)\b", re.I), ["disk", "du", "df", "cleanup"]),
    (re.compile(r"\b(json|yaml|csv|datos|data|xml)\b", re.I), ["json", "yaml", "csv", "data", "tables"]),
    (re.compile(r"\b(http|api|rest|curl|request)\b", re.I), ["http", "api", "rest"]),
    (re.compile(r"\b(dns|ping|red|network|latency|bandwidth)\b", re.I), ["dns", "network", "ping", "bandwidth"]),
    (re.compile(r"\b(monitor|cpu|memoria|process|proceso|top)\b", re.I), ["cpu", "monitor", "processes", "top"]),
    (re.compile(r"\b(secret|seguridad|security|vuln|cve|lint bash|shellcheck)\b", re.I), ["secrets", "security", "vulns", "bash", "lint"]),
    (re.compile(r"\b(llm|ai|agent|ollama|prompt|modelo)\b", re.I), ["llm", "ai", "local", "coding"]),
    (re.compile(r"\b(python|venv|pip|ruff)\b", re.I), ["python", "venv", "packaging", "lint"]),
    (re.compile(r"\b(backup|sync|cloud|rclone|restic)\b", re.I), ["backup", "sync", "cloud"]),
    (re.compile(r"\b(markdown|readme|docs|document)\b", re.I), ["markdown", "docs", "readme"]),
    (re.compile(r"\b(prompt|shell history|historial|cd inteligente)\b", re.I), ["history", "prompt", "cd", "shell"]),
    (re.compile(r"\b(rm |borrar|delete safe|papelera|trash)\b", re.I), ["rm", "trash", "safety"]),
    (re.compile(r"\b(replace|sed |refactor text)\b", re.I), ["sed", "replace", "edit"]),
    (re.compile(r"\b(benchmark|bench|hyperfine|rendimiento)\b", re.I), ["benchmark", "performance"]),
    (re.compile(r"\b(version|asdf|nvm|pyenv|runtime)\b", re.I), ["versions", "runtime"]),
    (re.compile(r"\b(tmux|multiplex|session|zellij)\b", re.I), ["tmux", "multiplexer"]),
    (re.compile(r"\b(editor|vim|helix|nano)\b", re.I), ["editor", "lsp", "text"]),
]


def suggest(
    task: str,
    *,
    catalog: Optional[Catalog] = None,
    limit: int = 8,
    only_missing: bool = False,
    only_installed: bool = False,
) -> str:
    """Suggest tools for a free-form task description."""
    cat = catalog or get_catalog()
    q = (task or "").strip()
    if not q:
        return (
            "Usage: /tools suggest <task>\n"
            "Examples:\n"
            "  /tools suggest search code fast\n"
            "  /tools suggest docker image size\n"
            "  /tools suggest safe delete files\n"
        )

    tag_scores: dict[str, int] = {}
    for pat, tags in _TASK_ALIASES:
        if pat.search(q):
            for t in tags:
                tag_scores[t.lower()] = tag_scores.get(t.lower(), 0) + 3

    # token overlap with id/name/tags/description/replaces
    tokens = {t.lower() for t in re.findall(r"[a-zA-Z0-9_+-]+", q) if len(t) > 1}
    scored: list[tuple[int, ToolEntry, ProbeResult]] = []
    for tool in cat.tools:
        score = 0
        blob_tags = {x.lower() for x in tool.tags}
        for t, w in tag_scores.items():
            if t in blob_tags or t == tool.id or t in {r.lower() for r in tool.replaces}:
                score += w
        for tok in tokens:
            if tok == tool.id or tok == tool.name.lower() or tok == tool.bin.lower():
                score += 10
            elif tok in blob_tags:
                score += 4
            elif tok in {r.lower() for r in tool.replaces}:
                score += 6
            elif tok in tool.description.lower():
                score += 1
            elif tok in tool.category.lower():
                score += 2
        if score <= 0:
            continue
        pr = probe_tool(tool)
        if only_missing and pr.installed:
            continue
        if only_installed and not pr.installed:
            continue
        scored.append((score, tool, pr))

    scored.sort(key=lambda x: (-x[0], x[1].id))
    top = scored[: max(1, min(limit, 20))]
    if not top:
        return (
            f"No strong matches for {q!r}.\n"
            "Try: /tools search <keyword>  or  /tools doctor core\n"
        )

    lines = [f"Suggestions for: {q}", ""]
    for score, tool, pr in top:
        flag = "✔ installed" if pr.installed else "✖ missing"
        alt = f"  (replaces: {', '.join(tool.replaces)})" if tool.replaces else ""
        lines.append(f"  {tool.name:14} [{flag}]  {tool.description}{alt}")
        if not pr.installed:
            lines.append(f"                 install: {format_install_hint(tool)}")
        lines.append(f"                 tags: {', '.join(tool.tags) or '—'} · score={score}")
    lines.append("")
    lines.append("Tip: /tools show <id> · /tools doctor core · /tools search yaml")
    return "\n".join(lines) + "\n"


def search(
    query: str,
    *,
    catalog: Optional[Catalog] = None,
    limit: int = 15,
) -> str:
    cat = catalog or get_catalog()
    q = (query or "").strip().lower()
    if not q:
        return "Usage: /tools search <keyword>\n"

    hits: list[tuple[int, ToolEntry]] = []
    for tool in cat.tools:
        score = 0
        if q == tool.id or q == tool.name.lower() or q == tool.bin.lower():
            score = 100
        elif q in tool.id or q in tool.name.lower() or q in tool.bin.lower():
            score = 50
        elif q in tool.category.lower():
            score = 30
        elif any(q in t.lower() for t in tool.tags):
            score = 40
        elif any(q in r.lower() for r in tool.replaces):
            score = 45
        elif q in tool.description.lower():
            score = 20
        if score:
            hits.append((score, tool))
    hits.sort(key=lambda x: (-x[0], x[1].id))
    hits = hits[: max(1, min(limit, 40))]
    if not hits:
        return f"No tools matched {query!r}.\n"

    lines = [f"Search: {query!r} ({len(hits)} shown)", ""]
    for _, tool in hits:
        pr = probe_tool(tool)
        flag = "✔" if pr.installed else "·"
        lines.append(
            f"  {flag} {tool.id:16} [{tool.category:10}] {tool.description[:70]}"
        )
    return "\n".join(lines) + "\n"


def show_tool(tool_id: str, *, catalog: Optional[Catalog] = None) -> str:
    cat = catalog or get_catalog()
    key = (tool_id or "").strip().lower()
    tool = cat.by_id.get(key)
    if not tool:
        # fuzzy by name/bin
        for t in cat.tools:
            if t.name.lower() == key or t.bin.lower() == key:
                tool = t
                break
    if not tool:
        return f"Unknown tool {tool_id!r}. Try /tools search {tool_id}\n"

    pr = probe_tool(tool)
    lines = [
        f"{tool.name}  (id={tool.id})",
        f"  binary:      {tool.bin}"
        + (f" → {pr.path}" if pr.installed and pr.path else "  [not on PATH]"),
        f"  category:    {tool.category}",
        f"  tags:        {', '.join(tool.tags) or '—'}",
        f"  replaces:    {', '.join(tool.replaces) or '—'}",
        f"  description: {tool.description}",
        f"  install:     {format_install_hint(tool)}",
    ]
    return "\n".join(lines) + "\n"


def list_tools(
    *,
    category: Optional[str] = None,
    catalog: Optional[Catalog] = None,
    check: bool = False,
) -> str:
    cat = catalog or get_catalog()
    tools = cat.tools
    if category:
        c = category.lower()
        tools = [t for t in tools if t.category.lower() == c]
        if not tools:
            cats = sorted({t.category for t in cat.tools})
            return f"No tools in category {category!r}. Categories: {', '.join(cats)}\n"

    by_cat: dict[str, list[ToolEntry]] = {}
    for t in tools:
        by_cat.setdefault(t.category, []).append(t)

    lines = [f"Toolbox catalog v{cat.version} — {len(tools)} tools", ""]
    for cat_name in sorted(by_cat):
        lines.append(f"[{cat_name}]")
        for t in sorted(by_cat[cat_name], key=lambda x: x.id):
            if check:
                pr = probe_tool(t)
                flag = "✔" if pr.installed else "·"
                lines.append(f"  {flag} {t.id:16} {t.description[:64]}")
            else:
                lines.append(f"  · {t.id:16} {t.description[:64]}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def alternatives(classic: str, *, catalog: Optional[Catalog] = None) -> str:
    """Map a classic Unix tool name to modern replacements in the catalog."""
    cat = catalog or get_catalog()
    key = (classic or "").strip().lower()
    if not key:
        return "Usage: /tools alt <classic-cmd>   e.g. /tools alt ls\n"
    hits = [t for t in cat.tools if key in {r.lower() for r in t.replaces} or key == t.id]
    # also search tags
    if not hits:
        hits = [t for t in cat.tools if key in {x.lower() for x in t.tags}]
    if not hits:
        return f"No catalog alternatives for {classic!r}. Try /tools search {classic}\n"
    lines = [f"Modern alternatives to {classic!r}:", ""]
    for t in hits:
        pr = probe_tool(t)
        flag = "✔" if pr.installed else "✖"
        lines.append(f"  {flag} {t.name:14} {t.description}")
        if not pr.installed:
            lines.append(f"      → {format_install_hint(t)}")
    return "\n".join(lines) + "\n"


def query_for_agent(
    question: str,
    *,
    mode: str = "suggest",
    catalog: Optional[Catalog] = None,
    limit: int = 6,
) -> str:
    """Compact answer for the chat ``toolbox_query`` host tool."""
    mode = (mode or "suggest").lower().strip()
    if mode in ("doctor", "status"):
        profile = (question or "core").strip() or "core"
        # allow "doctor git" style
        parts = profile.split()
        if parts and parts[0].lower() == "doctor":
            profile = parts[1] if len(parts) > 1 else "core"
        return doctor(profile, catalog=catalog, show_installed=False)
    if mode in ("search", "find"):
        return search(question, catalog=catalog, limit=limit)
    if mode in ("show", "info"):
        return show_tool(question, catalog=catalog)
    if mode in ("alt", "alternatives", "replace"):
        return alternatives(question, catalog=catalog)
    if mode in ("runtime", "available", "caps", "capabilities"):
        return runtime_brief(catalog=catalog)
    return suggest(question, catalog=catalog, limit=limit)


# ── Runtime: use modern catalog tools by capability ─────────────────


@dataclass(frozen=True)
class ResolvedBinary:
    capability: str
    tool_id: str
    name: str
    bin: str
    path: str


def which_tool(tool_id: str, *, catalog: Optional[Catalog] = None) -> Optional[ProbeResult]:
    cat = catalog or get_catalog()
    tool = cat.by_id.get(tool_id)
    if not tool:
        return None
    pr = probe_tool(tool)
    return pr if pr.installed else None


def resolve_capability(
    capability: str,
    *,
    catalog: Optional[Catalog] = None,
) -> Optional[ResolvedBinary]:
    """Return the first installed catalog tool for a host capability."""
    cat = catalog or get_catalog()
    key = (capability or "").strip().lower()
    prefs = CAPABILITY_PREFERENCE.get(key)
    if not prefs:
        return None
    for tid in prefs:
        pr = which_tool(tid, catalog=cat)
        if pr and pr.path and pr.resolved_bin:
            return ResolvedBinary(
                capability=key,
                tool_id=tid,
                name=pr.tool.name,
                bin=pr.resolved_bin,
                path=pr.path,
            )
    return None


def resolve_bin_path(tool_id: str, *, catalog: Optional[Catalog] = None) -> Optional[str]:
    pr = which_tool(tool_id, catalog=catalog)
    return pr.path if pr else None


@lru_cache(maxsize=1)
def _runtime_probe_cache() -> tuple[tuple[str, str, str], ...]:
    """Cached (capability, tool_id, bin) for installed capabilities."""
    rows: list[tuple[str, str, str]] = []
    for cap in CAPABILITY_PREFERENCE:
        r = resolve_capability(cap)
        if r:
            rows.append((cap, r.tool_id, r.bin))
    return tuple(rows)


def clear_runtime_cache() -> None:
    _runtime_probe_cache.cache_clear()
    get_catalog.cache_clear()


def runtime_brief(*, catalog: Optional[Catalog] = None, max_lines: int = 24) -> str:
    """Compact block injected into the agent system/seed context."""
    # catalog arg reserved for tests; cache uses default catalog
    _ = catalog
    rows = list(_runtime_probe_cache())[:max_lines]
    if not rows:
        return (
            "MODERN TOOLBOX: none of the preferred modern CLIs are on PATH. "
            "Host tools use Python fallbacks. Run /tools doctor core to install."
        )
    lines = [
        "MODERN TOOLBOX (installed — host tools prefer these automatically):",
    ]
    for cap, tid, bin_name in rows:
        lines.append(f"  · {cap:12} → {tid} ({bin_name})")
    lines.append(
        "Prefer host tools list_dir/grep/glob/read_file (they use modern bins). "
        "For ad-hoc shell, prefer modern names (eza, rg, fd, bat, dust, duf, procs). "
        "Classic ls/cat/grep/df/du/ps are auto-upgraded when safe."
    )
    return "\n".join(lines)


def _run_cmd(
    argv: list[str],
    *,
    cwd: Optional[Path] = None,
    timeout: int = 30,
) -> tuple[int, str, str]:
    proc = subprocess.run(
        argv,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def modern_list_dir(
    path: Path,
    *,
    cwd: Optional[Path] = None,
    tree: bool = False,
    timeout: int = 20,
) -> Optional[tuple[str, str]]:
    """List directory with eza/tre if available. Returns (backend_label, output)."""
    path = path.resolve()
    if not path.is_dir():
        return None

    if tree:
        r = resolve_capability("list_dir")
        # prefer eza -T or tre
        tre_pr = which_tool("tre")
        if tre_pr and tre_pr.path:
            code, out, err = _run_cmd(
                [tre_pr.path, str(path)],
                cwd=cwd,
                timeout=timeout,
            )
            if code == 0 and out.strip():
                return ("tre", out.strip())
        eza = which_tool("eza")
        if eza and eza.path:
            code, out, err = _run_cmd(
                [eza.path, "-T", "-L", "2", "--group-directories-first", str(path)],
                cwd=cwd,
                timeout=timeout,
            )
            if code == 0 and out.strip():
                return ("eza -T", out.strip())
        return None

    eza = which_tool("eza")
    if eza and eza.path:
        code, out, err = _run_cmd(
            [
                eza.path,
                "-la",
                "--group-directories-first",
                "--git",
                "--color=never",
                str(path),
            ],
            cwd=cwd,
            timeout=timeout,
        )
        if code == 0 and out.strip():
            return ("eza", out.strip())
        # retry without --git if repo issues
        code, out, err = _run_cmd(
            [eza.path, "-la", "--group-directories-first", "--color=never", str(path)],
            cwd=cwd,
            timeout=timeout,
        )
        if code == 0 and out.strip():
            return ("eza", out.strip())

    tre_pr = which_tool("tre")
    if tre_pr and tre_pr.path:
        code, out, err = _run_cmd([tre_pr.path, str(path)], cwd=cwd, timeout=timeout)
        if code == 0 and out.strip():
            return ("tre", out.strip())
    return None


def modern_find_files(
    pattern: str,
    base: Path,
    *,
    cwd: Optional[Path] = None,
    max_hits: int = 80,
    timeout: int = 30,
) -> Optional[tuple[str, str]]:
    """Find files with fd if available."""
    fd = which_tool("fd")
    if not fd or not fd.path:
        return None
    base = base.resolve()
    # fd treats pattern as regex; for glob-like **/*.py use -g
    argv = [fd.path, "--color", "never", "-H"]
    if any(ch in pattern for ch in "*?[{") or pattern.startswith("**/"):
        argv.extend(["-g", pattern])
    else:
        argv.append(pattern)
    if base.is_dir():
        argv.append(str(base))
    else:
        argv.extend([".", str(base.parent)])
    code, out, err = _run_cmd(argv, cwd=cwd or base, timeout=timeout)
    # fd exits 1 when no matches — still ok
    lines = [ln for ln in (out or "").splitlines() if ln.strip()][:max_hits]
    if code not in (0, 1) and not lines:
        return None
    return ("fd", "\n".join(lines) if lines else "(no matches)")


def modern_view_file(
    path: Path,
    *,
    cwd: Optional[Path] = None,
    max_chars: int = 12000,
    timeout: int = 15,
) -> Optional[tuple[str, str]]:
    """View file with bat (plain, no ANSI) if available."""
    bat = which_tool("bat")
    if not bat or not bat.path:
        return None
    path = path.resolve()
    if not path.is_file():
        return None
    code, out, err = _run_cmd(
        [
            bat.path,
            "-p",
            "--color=never",
            "--style=plain",
            "--paging=never",
            str(path),
        ],
        cwd=cwd,
        timeout=timeout,
    )
    if code != 0:
        return None
    text = out or ""
    if len(text) > max_chars:
        text = text[:max_chars] + "\n…[truncated]"
    return ("bat", text)


def modern_search_text(
    pattern: str,
    base: Path,
    *,
    glob: str = "",
    max_hits: int = 40,
    cwd: Optional[Path] = None,
    timeout: int = 30,
) -> Optional[tuple[str, str]]:
    """Search with rg if available."""
    rg = which_tool("ripgrep")
    if not rg or not rg.path:
        return None
    argv = [rg.path, "-n", "--no-heading", "-S", "--color", "never", pattern]
    if glob:
        argv.extend(["-g", glob])
    argv.append(str(base))
    try:
        code, out, err = _run_cmd(argv, cwd=cwd, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    lines = (out or "").splitlines()[:max_hits]
    # rg exit 1 = no match
    if code not in (0, 1) and not lines:
        return None
    return ("rg", "\n".join(lines) if lines else "(no matches)")


def soft_rewrite_shell_command(cmd: str) -> tuple[str, Optional[str]]:
    """Rewrite leading classic utilities to modern catalog tools when installed.

    Only rewrites the first pipeline segment's leading command. Returns
    (possibly_new_cmd, note_or_None).
    """
    raw = (cmd or "").strip()
    if not raw:
        return raw, None

    # Don't touch complex shell that starts with env assignments or builtins we skip
    if raw.startswith(("!", "[[", "((", "source ", ".", "cd ")):
        return raw, None

    # Split on first pipe/and/or to only rewrite the left-most simple command head
    # but still allow `ls -la | head` → `eza -la | head`
    for pat, tool_id, prefix in _SHELL_SOFT_REWRITE:
        if not pat.search(raw):
            continue
        pr = which_tool(tool_id)
        if not pr or not pr.path:
            continue
        # Replace first token with modern absolute path + extra flags from prefix[1:]
        m = re.match(r"^(\S+)(\s*)(.*)$", raw, re.S)
        if not m:
            continue
        rest = m.group(3)
        # prefix is like ["eza"] or ["bat", "-p", ...]
        new_head = " ".join([pr.path, *prefix[1:]])
        if rest:
            new_cmd = f"{new_head} {rest}"
        else:
            new_cmd = new_head
        note = f"auto-upgraded `{m.group(1)}` → {tool_id} ({pr.resolved_bin})"
        return new_cmd, note
    return raw, None


def help_text() -> str:
    return """\
Toolbox — modern terminal tools catalog (PATH doctor + suggestions)

  /tools                      Short overview + core doctor summary
  /tools doctor [profile]     Check PATH for profile (default: core)
  /tools suggest <task>       Recommend tools for a task
  /tools search <keyword>     Search catalog
  /tools show <id>            Details + install hints
  /tools list [category]      List catalog (optional category)
  /tools alt <classic>        Modern alternatives (ls, grep, cat, …)
  /tools profiles             List doctor profiles

Profiles: core, git, docker, k8s, disk, net, monitor, data, security, ai,
          modern-rust, all

Outer CLI:
  multiagent tools doctor [--profile core]
  multiagent tools suggest "search code"
  multiagent tools search yaml
  multiagent tools show eza
  multiagent tools list --check
"""
