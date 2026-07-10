"""
Bounded codebase context for chat and planner.

- Read specific project files mentioned in a prompt (or discovered nearby).
- Inject graphify only when the session is in this MultiAgent project and
  either the session is starting or ``graphify-out/graph.json`` changed.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
GRAPH_JSON = ROOT / "graphify-out" / "graph.json"

# Hard caps — never dump whole trees into the model.
_MAX_FILES = 6
_MAX_CHARS_PER_FILE = 4000
_MAX_TOTAL_FILE_CHARS = 12000
_SKIP_DIR_PARTS = {
    ".git",
    "venv",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "graphify-out",
    ".mypy_cache",
    ".ruff_cache",
}
_SKIP_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".so",
    ".dll",
    ".exe",
    ".bin",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".db",
    ".sqlite",
}
_SECRET_NAMES = {".env", ".env.local", ".env.production", "secrets.yaml", "credentials.json"}

_PATH_RE = re.compile(
    r"(?P<p>(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.[A-Za-z0-9]{1,12}"
    r"|[A-Za-z0-9_.-]+\.(?:py|md|yaml|yml|toml|json|txt|sh|fish|ini|cfg))"
)


def in_multiagent_project(cwd: Optional[Path] = None) -> bool:
    """True when the MultiAgent package root is usable (graph + tools live there).

    Graphify and host tools always operate on *this* checkout (ROOT), not on
    whatever directory the user launched multiagent from. Previously we required
    cwd ∈ MultiAgent, which made free-chat invent graphify when started elsewhere.
    """
    try:
        root = ROOT.resolve()
        return (root / "cli_app").is_dir() and (root / "graphs").is_dir()
    except Exception:
        return False


def graph_mtime() -> Optional[float]:
    try:
        if GRAPH_JSON.exists():
            return GRAPH_JSON.stat().st_mtime
    except OSError:
        pass
    return None


def should_use_graphify(
    *,
    session_graph_mtime: Optional[float] = None,
    session_graph_used: bool = False,
    cwd: Optional[Path] = None,
    force: bool = False,
) -> bool:
    """Whether graphify is available for this project.

    Free-chat re-queries every turn when available (see *force* / caller).
    *session_* args kept for compatibility; mtime is used only when force=False.
    """
    if not in_multiagent_project(cwd):
        return False
    if not GRAPH_JSON.exists():
        return False
    mtime = graph_mtime()
    if mtime is None:
        return False
    if force:
        return True
    if not session_graph_used:
        return True
    if session_graph_mtime is None:
        return True
    return mtime > session_graph_mtime


_FOLDER_PHRASE_RE = re.compile(
    r"(?:carpeta|folder|directorio|directory|paquete|package|módulo|modulo|module)"
    r"\s+[«\"'`]?([A-Za-z_][A-Za-z0-9_.-]*)[»\"'`]?",
    re.I,
)
# Bare identifiers that often name project packages (disambiguate .agents vs agents)
_BARE_DIR_RE = re.compile(
    r"\b(agents|graphs|cli_app|core|schemas|tests|skills|config|vibe_coding|deep_research)\b",
    re.I,
)


def extract_path_candidates(text: str) -> list[str]:
    """Pull path-like tokens from free text (order preserved, de-duplicated)."""
    found: list[str] = []
    seen: set[str] = set()

    def _add(p: str) -> None:
        p = p.strip().strip("'\"`")
        if not p or p in seen:
            return
        if p.startswith("http://") or p.startswith("https://"):
            return
        seen.add(p)
        found.append(p)

    for m in _PATH_RE.finditer(text or ""):
        _add(m.group("p"))
    for m in _FOLDER_PHRASE_RE.finditer(text or ""):
        _add(m.group(1))
    for m in _BARE_DIR_RE.finditer(text or ""):
        _add(m.group(1))
    return found


def _is_safe_path(path: Path, root: Path) -> bool:
    try:
        resolved = path.resolve()
        root_r = root.resolve()
        if not str(resolved).startswith(str(root_r)):
            return False
        if resolved.name in _SECRET_NAMES:
            return False
        parts = set(resolved.parts)
        if parts & _SKIP_DIR_PARTS:
            return False
        if resolved.suffix.lower() in _SKIP_SUFFIXES:
            return False
        if not resolved.is_file():
            return False
        # Size guard (~200 KB)
        if resolved.stat().st_size > 200_000:
            return False
        return True
    except OSError:
        return False


def resolve_readable_path(raw: str, *, root: Optional[Path] = None) -> Optional[Path]:
    base = (root or ROOT).resolve()
    p = Path(raw)
    candidates = []
    if p.is_absolute():
        candidates.append(p)
    else:
        candidates.append(base / p)
        try:
            candidates.append(Path.cwd() / p)
        except Exception:
            pass
    for c in candidates:
        if _is_safe_path(c, base):
            return c.resolve()
    return None


def read_project_files(
    paths: list[str],
    *,
    root: Optional[Path] = None,
    max_files: int = _MAX_FILES,
    max_chars_each: int = _MAX_CHARS_PER_FILE,
    max_total: int = _MAX_TOTAL_FILE_CHARS,
) -> str:
    """Read a bounded set of project files; return a single context block."""
    base = (root or ROOT).resolve()
    chunks: list[str] = []
    total = 0
    n = 0
    for raw in paths:
        if n >= max_files or total >= max_total:
            break
        path = resolve_readable_path(raw, root=base)
        if path is None:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.debug("skip unreadable %s: %s", path, exc)
            continue
        # Relativize for the model
        try:
            label = str(path.relative_to(base))
        except ValueError:
            label = str(path)
        body = text
        if len(body) > max_chars_each:
            body = body[: max_chars_each - 20].rstrip() + "\n…[truncated]"
        if total + len(body) > max_total:
            remain = max_total - total
            if remain < 200:
                break
            body = body[: remain - 20].rstrip() + "\n…[truncated]"
        chunks.append(f"--- FILE: {label} ---\n{body}\n--- END FILE ---")
        total += len(body)
        n += 1
    if not chunks:
        return ""
    return "\n\n".join(chunks)


def _is_safe_dir(path: Path, root: Path) -> bool:
    try:
        resolved = path.resolve()
        root_r = root.resolve()
        if not str(resolved).startswith(str(root_r)):
            return False
        if not resolved.is_dir():
            return False
        if set(resolved.parts) & _SKIP_DIR_PARTS:
            return False
        return True
    except OSError:
        return False


def resolve_project_dir(raw: str, *, root: Optional[Path] = None) -> Optional[Path]:
    """Resolve a folder name/path under the project root (not .venv etc.)."""
    base = (root or ROOT).resolve()
    name = (raw or "").strip().strip("/").strip("'\"`")
    if not name:
        return None
    candidates = [
        base / name,
        base / name.replace(".", "/"),
    ]
    # Prefer exact package dirs over hidden twins: agents before .agents when
    # user said "agents" (not ".agents").
    if not name.startswith("."):
        candidates = [c for c in candidates if c.name != f".{name}"]
    for c in candidates:
        if _is_safe_dir(c, base):
            return c.resolve()
    # Search one level deep (e.g. deep_research under agents/)
    try:
        for child in base.iterdir():
            if not child.is_dir() or child.name in _SKIP_DIR_PARTS:
                continue
            if child.name == name and _is_safe_dir(child, base):
                return child.resolve()
            nested = child / name
            if _is_safe_dir(nested, base):
                return nested.resolve()
    except OSError:
        pass
    return None


def list_project_dir(
    raw: str,
    *,
    root: Optional[Path] = None,
    max_entries: int = 40,
) -> str:
    """Return a bounded directory listing for a project folder."""
    base = (root or ROOT).resolve()
    path = resolve_project_dir(raw, root=base)
    if path is None:
        return ""
    try:
        rel = str(path.relative_to(base))
    except ValueError:
        rel = str(path)
    entries: list[str] = []
    try:
        items = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError as exc:
        return f"--- DIR: {rel} (unreadable: {exc}) ---"
    for item in items:
        if item.name in _SKIP_DIR_PARTS:
            continue
        if item.name.startswith(".") and item.name not in (".agents",):
            continue
        kind = "dir " if item.is_dir() else "file"
        entries.append(f"  [{kind}] {item.name}")
        if len(entries) >= max_entries:
            entries.append("  …")
            break
    body = "\n".join(entries) if entries else "  (empty)"
    return f"--- DIR: {rel}/ ---\n{body}\n--- END DIR ---"


def gather_dir_context(prompt: str, *, root: Optional[Path] = None) -> str:
    """List project directories named in the prompt (agents ≠ .agents)."""
    base = (root or ROOT).resolve()
    names = extract_path_candidates(prompt)
    # Always try phrases like "carpeta agents"
    chunks: list[str] = []
    seen: set[str] = set()
    for name in names:
        # Skip clear file paths for dir listing
        if "." in Path(name).name and Path(name).suffix:
            continue
        key = name.strip("/").lower()
        if key in seen:
            continue
        block = list_project_dir(name, root=base)
        if block:
            seen.add(key)
            chunks.append(block)
    return "\n\n".join(chunks)


def gather_file_context(prompt: str, extra_paths: Optional[list[str]] = None) -> str:
    """Extract paths from *prompt* (+ extras) and read them if safe."""
    candidates = extract_path_candidates(prompt)
    if extra_paths:
        for p in extra_paths:
            if p and p not in candidates:
                candidates.append(p)
    return read_project_files(candidates)


def paths_from_graph_snippet(snippet: str) -> list[str]:
    """Best-effort extract source_file paths from a graphify text dump."""
    if not snippet:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(
        r"(?:source_file|src|file)[=:\s\[]+([A-Za-z0-9_./-]+\.[A-Za-z0-9]{1,12})",
        snippet,
        flags=re.I,
    ):
        p = m.group(1)
        if p not in seen:
            seen.add(p)
            found.append(p)
    # Bracket paths like [cli_app/tui.py]
    for m in re.finditer(r"\[([A-Za-z0-9_./-]+\.[A-Za-z0-9]{1,12})\]", snippet):
        p = m.group(1)
        if p not in seen:
            seen.add(p)
            found.append(p)
    return found[:20]
