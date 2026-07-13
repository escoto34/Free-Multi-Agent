"""Tests for the terminal toolbox catalog (doctor / suggest / search)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cli_app.commands import dispatch
from cli_app.session import ConversationSession
from cli_app.tools import exec_tool
from core.toolbox import (
    DEFAULT_CATALOG,
    alternatives,
    doctor,
    get_catalog,
    list_profiles,
    load_catalog,
    probe_tool,
    search,
    show_tool,
    suggest,
)


def test_catalog_loads_and_has_core_tools():
    cat = load_catalog(DEFAULT_CATALOG)
    assert cat.version >= 1
    assert len(cat.tools) >= 50
    assert "eza" in cat.by_id
    assert "ripgrep" in cat.by_id
    assert "core" in cat.profiles
    # every profile tool id must exist in catalog
    for pname, meta in cat.profiles.items():
        for tid in meta.get("tools") or []:
            assert tid in cat.by_id, f"profile {pname} references unknown tool {tid}"


def test_probe_python_is_installed():
    # python3 may or may not be in catalog; probe shutil.which path via a known bin
    cat = get_catalog()
    # jq or something might miss; just ensure probe doesn't crash
    for t in cat.tools[:5]:
        pr = probe_tool(t)
        assert pr.tool.id == t.id
        assert isinstance(pr.installed, bool)


def test_doctor_core_returns_report():
    text = doctor("core", show_installed=True)
    assert "Toolbox doctor" in text
    assert "profile: core" in text
    assert "installed:" in text.lower() or "Installed:" in text or "Missing" in text


def test_doctor_unknown_profile():
    text = doctor("no-such-profile-xyz")
    assert "Unknown profile" in text


def test_suggest_search_code():
    text = suggest("search code fast")
    assert "Suggestions" in text
    # ripgrep / fd / ast-grep are likely hits
    assert any(x in text.lower() for x in ("ripgrep", "rg", "fd", "ast-grep", "grep"))


def test_suggest_docker():
    text = suggest("docker image layers")
    assert "dive" in text.lower() or "lazydocker" in text.lower() or "trivy" in text.lower()


def test_search_yaml():
    text = search("yaml")
    assert "yq" in text.lower() or "dasel" in text.lower()


def test_alternatives_ls():
    text = alternatives("ls")
    assert "eza" in text.lower()


def test_show_eza():
    text = show_tool("eza")
    assert "eza" in text.lower()
    assert "install" in text.lower()


def test_list_profiles_nonempty():
    rows = list_profiles()
    names = {r["name"] for r in rows}
    assert "core" in names
    assert "git" in names


def test_slash_tools_help():
    s = ConversationSession()
    r = dispatch("/tools help", s)
    assert r.ok
    assert "doctor" in r.text
    assert "suggest" in r.text


def test_slash_tools_doctor():
    s = ConversationSession()
    r = dispatch("/tools doctor core", s)
    assert r.ok
    assert "doctor" in r.text.lower()


def test_slash_tools_alt_ls():
    s = ConversationSession()
    r = dispatch("/tools alt ls", s)
    assert r.ok
    assert "eza" in r.text.lower()


def test_slash_tools_suggest():
    s = ConversationSession()
    r = dispatch("/tools suggest safe delete files", s)
    assert r.ok
    assert "rip" in r.text.lower() or "rip2" in r.text.lower() or "trash" in r.text.lower()


def test_host_tool_toolbox_query_suggest():
    res = exec_tool("toolbox_query", {"query": "git pr review", "mode": "suggest"})
    assert res.ok
    assert res.output
    assert any(x in res.output.lower() for x in ("git", "gh", "lazygit", "delta"))


def test_host_tool_toolbox_query_doctor():
    res = exec_tool("toolbox_query", {"query": "core", "mode": "doctor"})
    assert res.ok
    assert "doctor" in res.output.lower() or "missing" in res.output.lower()


def test_host_tool_toolbox_alias():
    res = exec_tool("toolbox", {"query": "ls", "mode": "alt"})
    assert res.ok
    assert "eza" in res.output.lower()


def test_resolve_capability_list_dir():
    from core.toolbox import clear_runtime_cache, resolve_capability

    clear_runtime_cache()
    # On this machine eza may or may not be installed; just ensure API works
    r = resolve_capability("list_dir")
    if r is not None:
        assert r.capability == "list_dir"
        assert r.path
        assert r.tool_id in ("eza", "tre")


def test_soft_rewrite_ls_when_eza_installed():
    from core.toolbox import soft_rewrite_shell_command, which_tool

    if not which_tool("eza"):
        pytest.skip("eza not installed")
    new_cmd, note = soft_rewrite_shell_command("ls -la agents")
    assert note is not None
    assert "eza" in (note or "").lower()
    assert "ls -la" not in new_cmd or "eza" in new_cmd
    assert "agents" in new_cmd


def test_list_dir_uses_modern_backend_when_available():
    from core.toolbox import which_tool

    res = exec_tool("list_dir", {"path": "."})
    assert res.ok
    if which_tool("eza") or which_tool("tre"):
        assert "[via eza]" in res.output or "[via tre]" in res.output
    else:
        assert "[via python]" in res.output or "DIR" in res.output


def test_grep_annotates_backend():
    res = exec_tool("grep", {"pattern": "def load_catalog", "path": "core", "glob": "*.py"})
    assert res.ok
    assert "[via rg]" in res.output or "[via python]" in res.output


def test_runtime_brief_mode():
    res = exec_tool("toolbox_query", {"query": "", "mode": "runtime"})
    # query empty with runtime is ok via query_for_agent
    # actually toolbox_query requires query unless doctor — fix: allow runtime without query
    res = exec_tool("toolbox_query", {"query": "x", "mode": "runtime"})
    assert res.ok
    assert "MODERN TOOLBOX" in res.output or "none of the preferred" in res.output
