"""Tests for existing-source preservation helpers and coder merge wiring.

WAVE-18: the architect role was folded into the coder — the coder receives the
repo file *tree* (paths only) instead of pre-read contents, and the host reads
the touched files *after* the call to fire preservation warnings.
"""

from __future__ import annotations

from pathlib import Path

from agents.vibe_coding.preserve import (
    extract_top_level_symbols,
    missing_preserved_symbols,
    read_existing_sources,
)
from agents.vibe_coding.coder import _format_tree_block, run_coder
from schemas.vibe_coding import CodeArtifact


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


def test_format_tree_block_includes_paths():
    block = _format_tree_block("README.md\nsrc/app.py\n")
    assert "### REPO FILE TREE" not in block
    assert "src/app.py" in block
    assert "preserve its logic" in block
    empty = _format_tree_block("")
    assert "unavailable" in empty


def test_run_coder_passes_repo_tree_into_prompt(monkeypatch):
    captured: dict = {}

    def fake_run(*args, **kwargs):
        captured["messages"] = kwargs.get("messages")
        return CodeArtifact(
            files={"a.py": "def x():\n    return 1\n\ndef y():\n    return 2\n"},
            summary="merged",
        )

    monkeypatch.setattr("agents.vibe_coding.coder.run_structured_agent", fake_run)

    out = run_coder(
        "add y next to x",
        repo_tree="a.py\n",
    )
    assert out.summary == "merged"
    user = captured["messages"][1]["content"]
    assert "REPO FILE TREE" in user
    assert "a.py" in user
    system = captured["messages"][0]["content"]
    assert "preserve" in system.lower()


def test_coder_node_loads_disk_after_call_and_warns(tmp_path: Path, monkeypatch):
    """Integration-ish: coder_node passes the tree, then reads disk AFTER the
    call and fires the preservation warning when a symbol would be dropped."""
    from graphs.vibe_coding_graph import coder_node

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    util = repo_dir / "util.py"
    util.write_text(
        "def useful_helper():\n    return 'keep'\n\ndef main():\n    return 1\n",
        encoding="utf-8",
    )

    seen: dict = {}

    def fake_coder(task_text, repo_tree="", **kwargs):
        seen["tree"] = repo_tree
        return CodeArtifact(
            files={
                "util.py": (
                    "def main():\n    return 2\n"
                )
            },
            summary="bumped main",
        )

    monkeypatch.setattr("graphs.vibe_coding_graph.run_coder", fake_coder)
    monkeypatch.setattr(
        "graphs.vibe_coding_graph._resolve_repo_root",
        lambda: repo_dir,
    )
    monkeypatch.setattr("graphs.vibe_coding_graph.get_git_repo", lambda: None)

    state = {
        "idea": "make main return 2",
        "spec": None,
        "artifact": None,
        "test_logs": None,
        "debug_report": None,
        "fix_attempts": 0,
        "git_checkpoint_sha": None,
        "user_wip_stashed": False,
        "error": None,
        "handoff_history": [],
        "difficulty_by_role": None,
        "last_model_selection": None,
    }
    out = coder_node(state)
    assert out.get("error") is None
    assert "util.py" in seen["tree"], "repo tree must reach run_coder"
    # WAVE-18 preservation warning fires on the post-call read: useful_helper
    # was dropped and must be called out in the summary.
    summary = out["artifact"].summary
    assert "useful_helper" in summary
    # The artifact content dropped the helper (the warning only annotates the
    # summary) — the file on disk reflects the model's content.
    assert "main" in (repo_dir / "util.py").read_text(encoding="utf-8")
