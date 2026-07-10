"""
Read existing repo files so the Coder can merge changes without wiping
useful logic that is outside the user's idea.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Caps so free-tier context does not explode on huge files.
MAX_CHARS_PER_FILE = 14_000
MAX_TOTAL_CHARS = 48_000
# Head+tail when truncating so both imports and bottom helpers stay visible.
TRUNC_HEAD = 9_000
TRUNC_TAIL = 4_000


def _safe_resolve(repo_root: Path, rel: str) -> Optional[Path]:
    if not isinstance(rel, str) or not rel.strip():
        return None
    candidate = Path(rel.strip())
    if candidate.is_absolute():
        return None
    resolved = (repo_root / candidate).resolve()
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        return None
    return resolved


def _truncate(content: str, limit: int = MAX_CHARS_PER_FILE) -> str:
    if len(content) <= limit:
        return content
    head = content[:TRUNC_HEAD]
    tail = content[-TRUNC_TAIL:]
    omitted = len(content) - TRUNC_HEAD - TRUNC_TAIL
    return (
        f"{head}\n\n"
        f"# ... [{omitted} chars omitted for context budget] ...\n\n"
        f"{tail}"
    )


def read_existing_sources(
    repo_root: Path,
    relative_paths: list[str],
    *,
    max_per_file: int = MAX_CHARS_PER_FILE,
    max_total: int = MAX_TOTAL_CHARS,
) -> dict[str, str]:
    """Load existing file text for paths the Architect plans to touch.

    Returns a map of relative_path → content (possibly truncated).
    Missing files are omitted (greenfield paths).
    """
    out: dict[str, str] = {}
    total = 0
    root = repo_root.resolve()
    for rel in relative_paths:
        if total >= max_total:
            logger.warning(
                "Existing-source budget full (%d chars); skipping remaining paths",
                max_total,
            )
            break
        path = _safe_resolve(root, rel)
        if path is None or not path.is_file():
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("Could not read %s: %s", rel, exc)
            continue
        budget_left = max_total - total
        capped = _truncate(raw, min(max_per_file, budget_left))
        out[rel.replace("\\", "/")] = capped
        total += len(capped)
        logger.info(
            "Loaded existing source %s (%d chars, truncated=%s)",
            rel,
            len(capped),
            len(raw) > len(capped),
        )
    return out


_SYM_RE = re.compile(
    r"^(?:async\s+)?def\s+(\w+)\s*\(|^class\s+(\w+)\s*[\(:]",
    re.MULTILINE,
)


def extract_top_level_symbols(source: str) -> set[str]:
    """Names of top-level functions/classes (rough, language-agnostic-ish for py)."""
    names: set[str] = set()
    for m in _SYM_RE.finditer(source or ""):
        names.add(m.group(1) or m.group(2))
    return names


def missing_preserved_symbols(old: str, new: str) -> list[str]:
    """Symbols present in *old* but absent from *new* (likely accidental drops)."""
    old_syms = extract_top_level_symbols(old)
    if not old_syms:
        return []
    missing = sorted(s for s in old_syms if s not in (new or ""))
    return missing
