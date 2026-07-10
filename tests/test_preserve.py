"""Tests for existing-source preservation helpers and coder merge wiring."""

from __future__ import annotations

from pathlib import Path

from agents.vibe_coding.preserve import (
    extract_top_level_symbols,
    missing_preserved_symbols,
    read_existing_sources,
)
from agents.vibe_coding.coder import _format_existing_block, run_coder
from schemas.vibe_coding import CodeArtifact, TechnicalSpec


def test_read_existing_sources_loads_and_skips_missing(tmp_path: Path):
    (tmp_path / "pkg").mkdir()
    target = tmp_path / "pkg" / "util.py"
    target.write_text(
        "def keep_me():\n    return 1\n\ndef also_keep():\n    return 2\n",
        encoding="utf-8",
    )
    got = read_existing_sources(
        tmp_path,
        ["pkg/util.py", "pkg/does_not_exist.py", "../escape.py"],
    )
    assert "pkg/util.py" in got
    assert "keep_me" in got["pkg/util.py"]
    assert "pkg/does_not_exist.py" not in got


def test_extract_and_missing_symbols():
    old = "def alpha():\n    pass\n\nclass Beta:\n    pass\n\ndef gamma():\n    pass\n"
    new = "def alpha():\n    return 1\n\nclass Beta:\n    x = 1\n"
    assert extract_top_level_symbols(old) == {"alpha", "Beta", "gamma"}
    assert missing_preserved_symbols(old, new) == ["gamma"]
    assert missing_preserved_symbols(old, old) == []


def test_format_existing_block_includes_files():
    block = _format_existing_block({"a.py": "def x():\n    pass\n"})
    assert "### FILE: a.py" in block
    assert "def x()" in block
    empty = _format_existing_block({})
    assert "none" in empty.lower()


def test_run_coder_passes_existing_into_prompt(monkeypatch):
    captured: dict = {}

    def fake_run(*args, **kwargs):
        captured["messages"] = kwargs.get("messages")
        return CodeArtifact(
            files={"a.py": "def x():\n    return 1\n\ndef y():\n    return 2\n"},
            summary="merged",
        )

    monkeypatch.setattr("agents.vibe_coding.coder.run_structured_agent", fake_run)

    spec = TechnicalSpec(
        architecture="add y next to x",
        test_cases=["y works"],
        files_to_create=["a.py"],
    )
    out = run_coder(
        spec,
        existing_files={"a.py": "def x():\n    return 0\n"},
    )
    assert out.summary == "merged"
    user = captured["messages"][1]["content"]
    assert "EXISTING FILE CONTENTS" in user
    assert "def x()" in user
    assert "PRESERVE" in captured["messages"][0]["content"] or "preserve" in captured[
        "messages"
    ][0]["content"].lower()


def test_coder_node_loads_disk_and_calls_run_coder(tmp_path: Path, monkeypatch):
    """Integration-ish: coder_node reads disk before run_coder."""
    from graphs.vibe_coding_graph import coder_node
    from schemas.vibe_coding import TechnicalSpec, CodeArtifact

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    util = repo_dir / "util.py"
    util.write_text(
        "def useful_helper():\n    return 'keep'\n\ndef main():\n    return 1\n",
        encoding="utf-8",
    )

    seen: dict = {}

    def fake_coder(spec, router_instance=None, existing_files=None):
        seen["existing"] = existing_files
        return CodeArtifact(
            files={
                "util.py": (
                    "def useful_helper():\n    return 'keep'\n\n"
                    "def main():\n    return 2\n"
                )
            },
            summary="bumped main, kept helper",
        )

    monkeypatch.setattr("graphs.vibe_coding_graph.run_coder", fake_coder)
    monkeypatch.setattr(
        "graphs.vibe_coding_graph._resolve_repo_root",
        lambda: repo_dir,
    )

    state = {
        "idea": "make main return 2",
        "spec": TechnicalSpec(
            architecture="change main only",
            test_cases=["main is 2"],
            files_to_create=["util.py"],
        ),
        "artifact": None,
        "test_logs": None,
        "debug_report": None,
        "fix_attempts": 0,
        "git_checkpoint_sha": None,
        "user_wip_stashed": False,
        "error": None,
    }
    out = coder_node(state)
    assert out.get("error") is None
    assert seen["existing"] and "util.py" in seen["existing"]
    assert "useful_helper" in seen["existing"]["util.py"]
    assert (repo_dir / "util.py").read_text(encoding="utf-8").count("useful_helper") == 1
