"""WAVE-14 tests: new agent tools (git_log, git_diff, run_tests, search_web).

Requires every new tool to be classified READ (no approval round-trip) and to
either be network-free (search_web is mocked) or route through the hardened
shell helper (git/test tools are mocked at _guarded_shell).
"""

from __future__ import annotations

import pytest

NEW_TOOLS = ["git_log", "git_diff", "run_tests", "search_web"]


@pytest.fixture
def tools_module():
    from cli_app import tools

    return tools


def test_new_tools_classified_read_only(tools_module):
    for t in NEW_TOOLS:
        assert t in tools_module.READ_TOOLS, f"{t} must be a READ tool"
        assert t not in tools_module.WRITE_TOOLS, f"{t} must NOT be a WRITE tool"
        assert tools_module.needs_approval(t) is False


def test_new_tools_skipped_approval_roundtrip(tools_module, tmp_path, monkeypatch):
    """Each READ tool runs with approve=None (no approval UI) and no rejection."""
    monkeypatch.setattr(tools_module, "ROOT", tmp_path)
    # All four shell/network tools are stubbed so the test never execs.
    monkeypatch.setattr(
        tools_module, "_guarded_shell", lambda *a, **k: (0, "mock ok")
    )

    def fake_search(*a, **k):
        return "--- DuckDuckGo results ---\nURL: https://example.com\nTitle: x"

    monkeypatch.setattr(
        "agents.deep_research.source_fetch.search_duckduckgo", fake_search
    )
    for t in NEW_TOOLS:
        calls = tools_module.parse_tool_calls(
            f'```tool\n{{"name": "{t}", "args": {{"query": "langgraph"}}}}\n```'
        )
        results, always, rejected = tools_module.run_tools(calls)
        assert len(results) == 1
        assert rejected is False
        assert results[0].name == t


def test_git_log_builds_guarded_command(tools_module, monkeypatch):
    seen: dict = {}

    def fake_shell(cmd, **k):
        seen["cmd"] = cmd
        return 0, "abc123 (HEAD -> main) wave-14 tip"

    monkeypatch.setattr(tools_module, "_guarded_shell", fake_shell)
    res = tools_module.exec_tool("git_log", {"count": 3, "path": "cli_app"})
    assert res.ok
    assert "git log --oneline" in seen["cmd"]
    assert "-n 3" in seen["cmd"]
    assert "cli_app" in seen["cmd"]


def test_git_diff_defaults_to_unstaged(tools_module, monkeypatch):
    """Without a ref, git diff inspects unstaged (worktree) changes."""
    seen: dict[str] = {}

    def fake_shell(cmd, **k):
        seen["cmd"] = cmd
        return 0, "diff --git"

    monkeypatch.setattr(tools_module, "_guarded_shell", fake_shell)
    res = tools_module.exec_tool("git_diff", {})
    assert res.ok
    assert seen["cmd"].strip() == "git diff"


def test_run_tests_uses_venv_or_python3(tools_module, monkeypatch):
    seen: dict[str] = {}

    def fake_shell(cmd, **k):
        seen["cmd"] = cmd
        return 0, "5 passed"

    monkeypatch.setattr(tools_module, "_guarded_shell", fake_shell)
    res = tools_module.exec_tool(
        "run_tests", {"path": "tests/test_wave13.py"}
    )
    assert res.ok and res.output.startswith("tests: PASSED")
    assert "pytest" in seen["cmd"]


def test_run_tests_failure_reported(tools_module, monkeypatch):
    def fake_shell(cmd, **k):
        return 1, "1 failed"

    monkeypatch.setattr(tools_module, "_guarded_shell", fake_shell)
    res = tools_module.exec_tool("run_tests", {})
    assert not res.ok
    assert "FAILED" in res.output


def test_search_web_uses_ddg_chain(tools_module, monkeypatch):
    captured: dict[str, str] = {}

    def fake_search(query, *, max_chars=8000, timeout=15.0):
        captured["q"] = query
        return "URL: https://example.com\nTitle: LangGraph release"

    monkeypatch.setattr(
        "agents.deep_research.source_fetch.search_duckduckgo", fake_search
    )
    res = tools_module.exec_tool("search_web", {"query": "LangGraph"})
    assert res.ok
    assert captured["q"] == "LangGraph"
    assert "LangGraph release" in res.output


def test_tools_help_text_mentions_new_tools(tools_module):
    help_text = tools_module.tools_help_text()
    for t in NEW_TOOLS:
        assert f'"{t}"' in help_text


def test_write_tool_still_demands_approval(tools_module, tmp_path, monkeypatch):
    """A WRITE tool (run_terminal) still needs approval even in a batch."""
    monkeypatch.setattr(tools_module, "ROOT", tmp_path)
    calls = tools_module.parse_tool_calls(
        '```tool\n{"name": "run_tests", "args": {"query": "x"}}\n```\n'
        '```tool\n{"name": "create_venv", "args": {"path": ".venv"}}\n```'
    )
    from cli_app.tools import ToolCall, ToolResult

    created = []

    def approve(call: ToolCall) -> str:
        return "reject"

    monkeypatch.setattr(
        tools_module,
        "exec_tool",
        lambda n, a: created.append((n, a)) or ToolResult(n, True, "ran"),
    )
    results, always, rejected = tools_module.run_tools(calls, approve=approve)
    # run_tests ran (READ), create_venv rejected (WRITE).
    assert created and created[0][0] == "run_tests"
    assert len(results) == 2
    assert results[1].skipped is True  # create_venv → rejected/skipped
    assert rejected is True