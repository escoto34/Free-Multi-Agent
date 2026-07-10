"""Tests for global skill registry and SKILL.md format validation."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.skills import (
    active_skills,
    add_skill,
    build_skills_system_block,
    list_skills,
    parse_skill_md,
    remove_skill,
    resolve_skill_md,
    set_enabled,
    validate_skill_path,
)


def _write_skill(dir_path: Path, name: str = "ponytail", body: str | None = None) -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    text = (
        f"---\n"
        f"name: {name}\n"
        f"description: Example skill for tests about {name}.\n"
        f"version: \"1.0\"\n"
        f"---\n\n"
        f"{body or '# Hello\n\nDo the thing carefully and list steps.'}\n"
    )
    p = dir_path / "SKILL.md"
    p.write_text(text, encoding="utf-8")
    return dir_path


def test_parse_and_validate_ok(tmp_path: Path):
    skill_dir = _write_skill(tmp_path / "ponytail")
    md = resolve_skill_md(skill_dir)
    meta, body = parse_skill_md(md)
    assert meta["name"] == "ponytail"
    assert "thing" in body
    m = validate_skill_path(skill_dir)
    assert m.valid
    assert m.name == "ponytail"


def test_reject_missing_frontmatter(tmp_path: Path):
    p = tmp_path / "bad"
    p.mkdir()
    (p / "SKILL.md").write_text("# no frontmatter\n" + ("x" * 40), encoding="utf-8")
    m = validate_skill_path(p)
    assert not m.valid
    assert m.error


def test_reject_bad_name(tmp_path: Path):
    p = tmp_path / "x"
    p.mkdir()
    (p / "SKILL.md").write_text(
        "---\nname: BAD NAME\ndescription: hi there enough\n---\n\n# Body with enough text here\n",
        encoding="utf-8",
    )
    m = validate_skill_path(p)
    assert not m.valid


def test_registry_add_enable_disable(tmp_path: Path):
    reg = tmp_path / "skills.yaml"
    skill_dir = _write_skill(tmp_path / "ponytail", name="ponytail")
    meta = add_skill(skill_dir, enabled=True, registry_path=reg)
    assert meta.enabled
    assert meta.name == "ponytail"

    rows = list_skills(registry_path=reg)
    assert len(rows) == 1
    assert rows[0].enabled

    set_enabled("ponytail", False, registry_path=reg)
    rows = list_skills(registry_path=reg)
    assert rows[0].enabled is False
    assert active_skills(registry_path=reg) == []

    set_enabled("ponytail", True, registry_path=reg)
    active = active_skills(registry_path=reg)
    assert len(active) == 1

    block = build_skills_system_block(registry_path=reg)
    assert "ponytail" in block
    assert "Active external skills" in block

    assert remove_skill("ponytail", registry_path=reg)
    assert list_skills(registry_path=reg) == []


def test_slash_skills_list(tmp_path: Path, monkeypatch):
    from cli_app.commands import dispatch
    from cli_app.session import ConversationSession

    reg = tmp_path / "skills.yaml"
    skill_dir = _write_skill(tmp_path / "ponytail")
    add_skill(skill_dir, enabled=True, registry_path=reg)

    monkeypatch.setattr(
        "core.skills.list_skills",
        lambda registry_path=None: list_skills(registry_path=reg),
    )
    monkeypatch.setattr(
        "core.skills.active_skills",
        lambda registry_path=None: active_skills(registry_path=reg),
    )
    monkeypatch.setattr("core.skills.GLOBAL_SKILLS_FILE", reg)

    r = dispatch("/skills", ConversationSession())
    assert r.ok
    assert "ponytail" in r.text
    assert "ON" in r.text or "on" in r.text.lower()
