"""Tests for global skill registry and SKILL.md format validation."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.skills import (
    active_skills,
    add_skill,
    build_skills_system_block,
    build_vibe_skills_block,
    list_skills,
    parse_skill_md,
    remove_skill,
    resolve_skill_md,
    select_skills_for_pipeline,
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


def test_add_skill_defaults_to_disabled(tmp_path: Path):
    reg = tmp_path / "skills.yaml"
    skill_dir = _write_skill(tmp_path / "ponytail", name="ponytail")
    meta = add_skill(skill_dir, registry_path=reg)
    assert meta.enabled is False
    assert active_skills(registry_path=reg) == []


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


def test_disable_all_skills(tmp_path: Path):
    from core.skills import disable_all_skills

    reg = tmp_path / "skills.yaml"
    a = _write_skill(tmp_path / "a", name="skill-a")
    b = _write_skill(tmp_path / "b", name="skill-b")
    add_skill(a, enabled=True, registry_path=reg)
    add_skill(b, enabled=True, registry_path=reg)
    assert len(active_skills(registry_path=reg)) == 2
    n = disable_all_skills(registry_path=reg)
    assert n == 2
    assert active_skills(registry_path=reg) == []
    assert all(not s.enabled for s in list_skills(registry_path=reg))


def test_vibe_pipeline_match_injection(tmp_path: Path):
    reg = tmp_path / "skills.yaml"
    skill_dir = tmp_path / "vibe-landing"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: vibe-landing\n"
        "description: Static brand landings for multiagent vibe.\n"
        "version: \"1.0\"\n"
        "pipelines: [chat, vibe_coding]\n"
        "match: landing|website|html\n"
        "---\n\n"
        "# Landing skill\n\n"
        "Build a static hero and WhatsApp CTA only from grounded facts.\n",
        encoding="utf-8",
    )
    add_skill(skill_dir, enabled=True, registry_path=reg)

    hit = build_vibe_skills_block(
        "Build a brand landing website with HTML",
        registry_path=reg,
    )
    assert "vibe-landing" in hit
    assert "WhatsApp" in hit or "hero" in hit.lower()

    miss = build_vibe_skills_block(
        "Refactor the quota tracker SQLite schema only",
        registry_path=reg,
    )
    assert miss == ""

    selected = select_skills_for_pipeline(
        "vibe_coding",
        task_text="static website for clinic",
        registry_path=reg,
    )
    assert len(selected) == 1
    assert selected[0].name == "vibe-landing"


def test_bundled_vibe_skills_parse():
    root = Path(__file__).resolve().parents[1]
    for name in ("vibe-landing", "vibe-content-tests"):
        skill_dir = root / "skills" / name
        assert skill_dir.is_dir(), skill_dir
        m = validate_skill_path(skill_dir)
        assert m.valid, m.error
        assert "vibe_coding" in m.pipelines
        assert m.match


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
