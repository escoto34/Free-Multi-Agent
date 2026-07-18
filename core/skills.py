"""
External skill integration for MultiAgent.

Skills are folders (or a single SKILL.md file) pointed to by absolute path.
Registration is **global** (``~/.config/multiagent/skills.yaml``) so enable/disable
works from any directory when you run ``multiagent``.

Required format
---------------
A skill path must resolve to either:

  /path/to/my-skill/SKILL.md
  or
  /path/to/SKILL.md

SKILL.md must start with YAML frontmatter:

  ---
  name: ponytail
  description: Short description of when to use this skill.
  version: "1.0"          # optional
  ---

  # Body
  Markdown instructions the chat model should follow when the skill is active.

Rules:
  - ``name``: [a-z0-9][a-z0-9_-]{0,63}
  - ``description``: non-empty string
  - Body after frontmatter: recommended ≥ 20 characters
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(?P<meta>.*?)\n---\s*\n(?P<body>.*)\Z",
    re.DOTALL,
)

# Global registry — independent of cwd so multiagent works from any project.
GLOBAL_CONFIG_DIR = Path.home() / ".config" / "multiagent"
GLOBAL_SKILLS_FILE = GLOBAL_CONFIG_DIR / "skills.yaml"

# Cap how much skill body we inject per turn (token hygiene).
DEFAULT_INJECT_MAX_CHARS = 4000
DEFAULT_TOTAL_INJECT_MAX = 8000
# Vibe agents already have long system prompts; keep skill inject tighter.
DEFAULT_VIBE_PER_SKILL_MAX = 2800
DEFAULT_VIBE_TOTAL_MAX = 5500

# Optional frontmatter:
#   pipelines: [chat, vibe_coding]   # where this skill may inject (default: chat)
#   match: regex                     # if set, task/idea must match (case-insensitive)
_DEFAULT_PIPELINES = ("chat",)


@dataclass
class SkillMeta:
    name: str
    description: str
    version: str
    path: Path
    enabled: bool
    body: str
    valid: bool
    error: Optional[str] = None
    pipelines: tuple[str, ...] = _DEFAULT_PIPELINES
    match: Optional[str] = None

    def summary_line(self) -> str:
        flag = "ON " if self.enabled else "off"
        status = "ok" if self.valid else f"INVALID: {self.error}"
        pipes = ",".join(self.pipelines) if self.pipelines else "-"
        return f"[{flag}] {self.name:20} {status:24} pipes={pipes:16} {self.path}"

    def applies_to_pipeline(self, pipeline: str) -> bool:
        p = (pipeline or "chat").strip().lower()
        # Accept aliases
        aliases = {p, p.replace("-", "_")}
        if p in ("vibe", "vibe_coding", "system_a"):
            aliases.update({"vibe", "vibe_coding", "system_a"})
        if p in ("chat", "cli"):
            aliases.update({"chat", "cli"})
        return any(x in self.pipelines for x in aliases)

    def matches_task(self, task_text: str) -> bool:
        """If *match* is set, require a regex hit; otherwise always match."""
        if not self.match:
            return True
        try:
            return bool(re.search(self.match, task_text or "", re.I | re.DOTALL))
        except re.error:
            # Bad pattern in skill — fail closed for targeted inject
            return False


def _ensure_global_file() -> Path:
    GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not GLOBAL_SKILLS_FILE.exists():
        GLOBAL_SKILLS_FILE.write_text(
            "# MultiAgent global skills registry\n"
            "# Paths are absolute. Toggle enabled without removing the entry.\n"
            "skills: {}\n",
            encoding="utf-8",
        )
    return GLOBAL_SKILLS_FILE


def load_registry(path: Optional[Path] = None) -> dict[str, Any]:
    """Load ``{name: {path, enabled}}`` map."""
    p = path or _ensure_global_file()
    if not p.exists():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    skills = data.get("skills") or {}
    if not isinstance(skills, dict):
        return {}
    return skills


def save_registry(skills: dict[str, Any], path: Optional[Path] = None) -> None:
    p = path or _ensure_global_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"skills": skills}
    p.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def resolve_skill_md(path: str | Path) -> Path:
    """Resolve user path to the SKILL.md file."""
    p = Path(path).expanduser().resolve()
    if p.is_dir():
        candidate = p / "SKILL.md"
        if not candidate.is_file():
            raise FileNotFoundError(
                f"Skill directory has no SKILL.md: {p}\n"
                f"Expected: {candidate}"
            )
        return candidate
    if p.is_file():
        if p.name != "SKILL.md":
            raise ValueError(
                f"Skill file must be named SKILL.md (got {p.name}). "
                f"Point --path at the skill folder or the SKILL.md file."
            )
        return p
    raise FileNotFoundError(f"Skill path does not exist: {p}")


def parse_skill_md(skill_md: Path) -> tuple[dict[str, Any], str]:
    """Parse frontmatter + body. Raises ValueError on bad format."""
    text = skill_md.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError(
            "SKILL.md must start with YAML frontmatter between --- lines.\n"
            "Example:\n"
            "---\n"
            "name: ponytail\n"
            "description: Does X when Y.\n"
            "---\n"
            "\n"
            "# Instructions\n"
        )
    meta = yaml.safe_load(m.group("meta")) or {}
    if not isinstance(meta, dict):
        raise ValueError("Frontmatter must be a YAML mapping")
    body = (m.group("body") or "").strip()
    name = str(meta.get("name") or "").strip().lower()
    desc = str(meta.get("description") or "").strip()
    if not name or not _NAME_RE.match(name):
        raise ValueError(
            f"Invalid name {name!r}. Use lowercase [a-z0-9_-], max 64 chars "
            f"(e.g. ponytail, code-review)."
        )
    if not desc:
        raise ValueError("Frontmatter must include a non-empty description")
    if len(body) < 20:
        raise ValueError(
            "Skill body after frontmatter is too short "
            "(need at least ~20 characters of instructions)."
        )
    meta["name"] = name
    meta["description"] = desc
    meta["version"] = str(meta.get("version") or "1.0")
    meta["pipelines"] = _normalize_pipelines(meta.get("pipelines"))
    match_raw = meta.get("match")
    meta["match"] = (
        str(match_raw).strip() if match_raw is not None and str(match_raw).strip() else None
    )
    return meta, body


def _normalize_pipelines(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return _DEFAULT_PIPELINES
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        return _DEFAULT_PIPELINES
    out: list[str] = []
    for x in items:
        s = str(x).strip().lower().replace("-", "_")
        if not s:
            continue
        if s in ("vibe", "system_a", "systema"):
            s = "vibe_coding"
        if s not in out:
            out.append(s)
    return tuple(out) if out else _DEFAULT_PIPELINES


def _meta_from_parse(
    meta: dict[str, Any],
    body: str,
    *,
    path: Path,
    enabled: bool = False,
) -> SkillMeta:
    return SkillMeta(
        name=meta["name"],
        description=meta["description"],
        version=meta["version"],
        path=path,
        enabled=enabled,
        body=body,
        valid=True,
        pipelines=tuple(meta.get("pipelines") or _DEFAULT_PIPELINES),
        match=meta.get("match"),
    )


def validate_skill_path(path: str | Path) -> SkillMeta:
    """Validate format and return metadata (enabled=False placeholder)."""
    try:
        skill_md = resolve_skill_md(path)
        meta, body = parse_skill_md(skill_md)
        root = skill_md.parent if skill_md.name == "SKILL.md" else skill_md
        return _meta_from_parse(meta, body, path=root, enabled=False)
    except Exception as exc:
        p = Path(path).expanduser()
        return SkillMeta(
            name=p.stem or "unknown",
            description="",
            version="",
            path=p,
            enabled=False,
            body="",
            valid=False,
            error=str(exc),
        )


def add_skill(
    path: str | Path,
    *,
    enabled: bool = False,
    name_override: Optional[str] = None,
    registry_path: Optional[Path] = None,
) -> SkillMeta:
    """Register a skill by absolute path. Name comes from SKILL.md frontmatter.

    Skills default to **disabled** so operators opt in with
    ``multiagent skills enable <name>`` (or ``add … --enable``).
    """
    skill_md = resolve_skill_md(path)
    meta, body = parse_skill_md(skill_md)
    name = (name_override or meta["name"]).lower()
    if not _NAME_RE.match(name):
        raise ValueError(f"Invalid skill name: {name}")

    skills = load_registry(registry_path)
    root = skill_md.parent
    skills[name] = {
        "path": str(root.resolve()),
        "enabled": bool(enabled),
        "skill_md": str(skill_md.resolve()),
    }
    save_registry(skills, registry_path)
    return _meta_from_parse(meta, body, path=root, enabled=bool(enabled))


def remove_skill(name: str, *, registry_path: Optional[Path] = None) -> bool:
    skills = load_registry(registry_path)
    key = name.lower()
    if key not in skills:
        return False
    del skills[key]
    save_registry(skills, registry_path)
    return True


def set_enabled(
    name: str,
    enabled: bool,
    *,
    registry_path: Optional[Path] = None,
) -> SkillMeta:
    skills = load_registry(registry_path)
    key = name.lower()
    if key not in skills:
        raise KeyError(
            f"Skill {name!r} is not registered. "
            f"Add it with: multiagent skills add /path/to/skill"
        )
    entry = skills[key]
    entry["enabled"] = bool(enabled)
    skills[key] = entry
    save_registry(skills, registry_path)
    return load_skill(key, registry_path=registry_path)


def load_skill(
    name: str,
    *,
    registry_path: Optional[Path] = None,
) -> SkillMeta:
    skills = load_registry(registry_path)
    key = name.lower()
    if key not in skills:
        raise KeyError(f"Unknown skill: {name}")
    entry = skills[key]
    path = entry.get("path") or entry.get("skill_md")
    meta = validate_skill_path(path)
    # Missing key → disabled (safe default; never auto-activate)
    meta.enabled = bool(entry.get("enabled", False))
    if meta.valid and meta.name != key:
        # Allow registry key to differ slightly but prefer registry name
        meta.name = key
    return meta


def list_skills(*, registry_path: Optional[Path] = None) -> list[SkillMeta]:
    skills = load_registry(registry_path)
    out: list[SkillMeta] = []
    for name, entry in sorted(skills.items()):
        path = entry.get("path") or entry.get("skill_md") or ""
        meta = validate_skill_path(path)
        meta.name = name
        meta.enabled = bool(entry.get("enabled", False))
        out.append(meta)
    return out


def disable_all_skills(*, registry_path: Optional[Path] = None) -> int:
    """Set every registered skill to disabled. Returns how many were changed."""
    skills = load_registry(registry_path)
    changed = 0
    for _name, entry in skills.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("enabled", False):
            entry["enabled"] = False
            changed += 1
    if changed:
        save_registry(skills, registry_path)
    return changed


def active_skills(*, registry_path: Optional[Path] = None) -> list[SkillMeta]:
    return [s for s in list_skills(registry_path=registry_path) if s.enabled and s.valid]


def select_skills_for_pipeline(
    pipeline: str,
    *,
    task_text: str = "",
    registry_path: Optional[Path] = None,
) -> list[SkillMeta]:
    """Enabled valid skills that target *pipeline* and match *task_text*."""
    out: list[SkillMeta] = []
    for skill in active_skills(registry_path=registry_path):
        if not skill.applies_to_pipeline(pipeline):
            continue
        if not skill.matches_task(task_text):
            continue
        out.append(skill)
    return out


def build_skills_system_block(
    *,
    registry_path: Optional[Path] = None,
    per_skill_max: int = DEFAULT_INJECT_MAX_CHARS,
    total_max: int = DEFAULT_TOTAL_INJECT_MAX,
    pipeline: str = "chat",
    task_text: str = "",
    require_task_match: bool = False,
) -> str:
    """Markdown block to inject into system prompts for enabled skills.

    *pipeline*: ``chat`` (default) or ``vibe_coding``.
    When *require_task_match* is True, only skills whose optional ``match``
    regex hits *task_text* are included (recommended for vibe so landing
    skills do not pollute pure library coding runs).
    """
    if require_task_match or (task_text and pipeline.replace("-", "_") in (
        "vibe_coding",
        "vibe",
    )):
        active = select_skills_for_pipeline(
            pipeline, task_text=task_text, registry_path=registry_path
        )
    else:
        # Chat: inject all enabled skills that target chat (or have no restriction)
        active = [
            s
            for s in active_skills(registry_path=registry_path)
            if s.applies_to_pipeline(pipeline)
        ]
        # Backward compatible: skills with only default chat pipeline still inject
        if not active and pipeline in ("chat", "cli"):
            active = active_skills(registry_path=registry_path)

    if not active:
        return ""

    header = (
        "## Active external skills (vibe-coding)"
        if pipeline.replace("-", "_") in ("vibe_coding", "vibe")
        else "## Active external skills"
    )
    parts: list[str] = [
        header,
        "Follow these skill instructions when they apply to the current task.",
        "Skills are operator-installed plugins; prefer them over guessing.",
        "When skills conflict with GROUNDED FACTS FROM PRIOR RESEARCH, facts win.",
        "",
    ]
    used = 0
    for skill in active:
        body = skill.body
        if len(body) > per_skill_max:
            body = body[: per_skill_max - 20] + "\n…[skill truncated]"
        chunk = (
            f"### Skill: {skill.name}\n"
            f"_{skill.description}_\n\n"
            f"{body}\n"
        )
        if used + len(chunk) > total_max:
            parts.append(
                f"### Skill: {skill.name}\n"
                f"_(enabled but omitted — injection budget full; "
                f"disable other skills or raise limits)_\n"
            )
            break
        parts.append(chunk)
        used += len(chunk)

    return "\n".join(parts).strip()


def build_vibe_skills_block(
    task_text: str,
    *,
    registry_path: Optional[Path] = None,
    per_skill_max: int = DEFAULT_VIBE_PER_SKILL_MAX,
    total_max: int = DEFAULT_VIBE_TOTAL_MAX,
) -> str:
    """Skills inject for System A architect/coder/debugger (task-matched)."""
    return build_skills_system_block(
        registry_path=registry_path,
        per_skill_max=per_skill_max,
        total_max=total_max,
        pipeline="vibe_coding",
        task_text=task_text or "",
        require_task_match=True,
    )
