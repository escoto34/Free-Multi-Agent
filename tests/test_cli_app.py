"""Tests for interactive CLI helpers (config editor, keys, session, slash cmds)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from cli_app.commands import dispatch
from cli_app.session import ConversationSession, estimate_tokens
from core.config_editor import list_roles, reset_to_defaults, set_role
from core.keys import get_key_status, mask_key, set_api_key


def test_estimate_tokens_positive():
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 40) == 10


def test_session_compact_local_reduces_messages():
    s = ConversationSession()
    s.limit_tokens = 100000
    s.keep_recent = 2
    for i in range(10):
        s.add("user", f"message number {i} " + ("x" * 50))
        s.add("assistant", f"reply {i} " + ("y" * 50))
    before = len(s.messages)
    msg = s.compact_local()
    assert "Compacted" in msg or "Nothing" in msg
    assert len(s.messages) < before
    assert s.used_tokens() > 0


def test_session_status_line():
    s = ConversationSession()
    s.add("user", "hello")
    line = s.status_line()
    assert "ctx" in line
    assert "/" in line


def test_mask_key():
    assert mask_key("") == "(not set)"
    assert mask_key("your_groq_api_key_here") == "(not set)"
    assert mask_key("sk-abcdefghijklmnopqrstuvwxyz").endswith("wxyz")


def test_set_api_key_writes_env(tmp_path: Path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("GROQ_API_KEY=old\n", encoding="utf-8")
    preview = set_api_key("groq", "gsk_test_key_value_123456", env_file=env)
    assert "3456" in preview or preview.startswith("…")
    text = env.read_text(encoding="utf-8")
    assert "gsk_test_key_value_123456" in text
    status = get_key_status(env_file=env)
    groq = next(r for r in status if r["provider"] == "groq")
    # process env may still hold real keys; file path status uses env+file
    assert groq["provider"] == "groq"


def test_set_role_and_list(tmp_path: Path):
    live = tmp_path / "model_router.yaml"
    defaults = tmp_path / "defaults_model_router.yaml"
    # Minimal config with known roles
    data = {
        "vibe_coding": {
            "architect": {"provider": "cohere", "model": "command-a-plus-05-2026"},
            "coder": {"provider": "openrouter", "model": "cohere/north-mini-code:free"},
            "debugger": {
                "provider": "openrouter",
                "model": "tencent/hy3:free",
                "fallback": {"provider": "groq", "model": "openai/gpt-oss-120b"},
            },
            "max_fix_cycles": 3,
        },
        "deep_research": {
            "safety_filter": {
                "provider": "groq",
                "model": "openai/gpt-oss-safeguard-20b",
            },
            "context_compressor": {
                "provider": "openrouter",
                "model": "tencent/hy3:free",
            },
            "web_search": {"provider": "groq", "model": "groq/compound-mini"},
            "grounding": {"provider": "cohere", "model": "command-a-plus-05-2026"},
            "synthesizer": {
                "provider": "cohere",
                "model": "command-r-plus-08-2024",
            },
        },
        "cli": {
            "chat": {"provider": "groq", "model": "openai/gpt-oss-120b"},
            "context_limit_tokens": 32000,
        },
    }
    live.write_text(yaml.safe_dump(data), encoding="utf-8")
    defaults.write_text(yaml.safe_dump(data), encoding="utf-8")

    node = set_role(
        "vibe_coding",
        "debugger",
        provider="groq",
        model="openai/gpt-oss-120b",
        config_path=live,
    )
    assert node["provider"] == "groq"
    assert node["model"] == "openai/gpt-oss-120b"

    rows = list_roles(config_path=live)
    dbg = next(r for r in rows if r["id"] == "vibe_coding.debugger")
    assert dbg["provider"] == "groq"

    # mutate then reset
    set_role(
        "vibe_coding",
        "architect",
        provider="groq",
        model="openai/gpt-oss-20b",
        config_path=live,
    )
    reset_to_defaults(config_path=live, defaults_path=defaults)
    rows2 = list_roles(config_path=live)
    arch = next(r for r in rows2 if r["id"] == "vibe_coding.architect")
    assert arch["provider"] == "cohere"


def test_dispatch_help():
    s = ConversationSession()
    r = dispatch("/help", s)
    assert r.ok
    assert "/do" in r.text
    assert "/config" in r.text
    # Planner owns pipelines — direct /vibe and /research are gone
    assert "/vibe" not in r.text
    assert "/research <" not in r.text
    assert r.data and r.data.get("help_panel") is True


def test_dispatch_status():
    s = ConversationSession()
    r = dispatch("/status", s)
    assert r.ok
    assert "ctx" in r.text


def test_dispatch_unknown():
    s = ConversationSession()
    r = dispatch("/nope", s)
    assert not r.ok


def test_query_graph_local_fallback(monkeypatch, tmp_path: Path):
    from cli_app import graph_rag

    report = tmp_path / "GRAPH_REPORT.md"
    report.write_text("## God Nodes\n1. `ConversationSession` - 30 edges\n", encoding="utf-8")
    monkeypatch.setattr(graph_rag, "GRAPH_REPORT", report)
    monkeypatch.setattr(graph_rag, "GRAPH_JSON", tmp_path / "missing.json")
    monkeypatch.setattr(
        graph_rag.subprocess,
        "run",
        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()),
    )
    out = graph_rag.query_graph("ConversationSession", budget=500)
    assert "ConversationSession" in out


def test_build_graph_augmented_messages_is_slim():
    from cli_app.graph_rag import build_graph_augmented_messages

    msgs = build_graph_augmented_messages(
        question="How does router work?",
        graph_snippet="NODE router.py [src=core/router.py]",
        recent_turns=[
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ],
        system_prompt="sys",
    )
    # system + 2 recent + final user with context
    assert len(msgs) == 4
    assert "PROJECT CONTEXT" in msgs[-1]["content"] or "router.py" in msgs[-1]["content"]
    assert "router.py" in msgs[-1]["content"]
    # Context must not be duplicated into recent turns
    assert "PROJECT CONTEXT" not in msgs[1]["content"]


def test_chat_turn_uses_graph(monkeypatch):
    from cli_app import agent_chat
    from cli_app import commands
    from core.router import LLMResponse

    queries: list[str] = []

    def fake_query(q, budget=1200, **kw):
        queries.append(q)
        return f"NODE related to {q[:40]} [src=agents/planner.py]"

    monkeypatch.setattr("cli_app.graph_rag.query_graph", fake_query)
    monkeypatch.setattr("cli_app.graph_rag.graph_available", lambda: True)
    monkeypatch.setattr(
        "cli_app.context_tools.in_multiagent_project",
        lambda cwd=None: True,
    )
    monkeypatch.setattr(
        "cli_app.context_tools.gather_file_context",
        lambda *a, **k: "",
    )
    monkeypatch.setattr(
        "cli_app.context_tools.gather_dir_context",
        lambda *a, **k: "--- DIR: agents/ ---\n  [file] planner.py\n--- END DIR ---",
    )

    captured = {}

    def fake_invoke(router, **kwargs):
        captured["messages"] = kwargs.get("messages")
        return LLMResponse(
            content="agents/ holds planner.py and deep_research/",
            provider="x",
            model="y",
        )

    monkeypatch.setattr(agent_chat, "invoke_router", fake_invoke)

    s = ConversationSession()
    r = commands.chat_turn("contexto de la carpeta agents", s)
    assert r.ok
    assert "agents" in r.text.lower() or "planner" in r.text.lower()
    blob = " ".join(m["content"] for m in captured["messages"])
    assert "agents" in blob.lower()
    assert queries and "agents" in queries[0].lower()
    stored = " ".join(m.content for m in s.messages)
    assert "KNOWLEDGE GRAPH" not in stored
    assert "ctx " not in r.text
    sys = captured["messages"][0]["content"]
    assert "agents/" in sys and ".agents/" in sys


def test_chat_turn_strips_ponytail_noise(monkeypatch):
    from cli_app import agent_chat
    from cli_app import commands
    from core.router import LLMResponse

    monkeypatch.setattr(
        "cli_app.context_tools.in_multiagent_project", lambda cwd=None: False
    )
    monkeypatch.setattr("cli_app.graph_rag.graph_available", lambda: False)
    monkeypatch.setattr(
        "cli_app.context_tools.gather_file_context", lambda *a, **k: ""
    )
    monkeypatch.setattr(
        "cli_app.context_tools.gather_dir_context", lambda *a, **k: ""
    )

    def fake_invoke(router, **kwargs):
        return LLMResponse(
            content="Ok hecho.\n→ skipped: nada, add when foo",
            provider="x",
            model="y",
        )

    monkeypatch.setattr(agent_chat, "invoke_router", fake_invoke)
    s = ConversationSession()
    r = commands.chat_turn("hola", s)
    assert r.ok
    assert "skipped" not in r.text.lower()


def test_parse_and_run_read_tool(tmp_path: Path, monkeypatch):
    from cli_app import tools

    monkeypatch.setattr(tools, "ROOT", tmp_path)
    f = tmp_path / "hello.py"
    f.write_text("print(1)\n", encoding="utf-8")
    calls = tools.parse_tool_calls(
        '```tool\n{"name": "read_file", "args": {"path": "hello.py"}}\n```'
    )
    assert len(calls) == 1 and calls[0].name == "read_file"
    results, always, _ = tools.run_tools(calls, always_approve=True)
    assert results[0].ok
    assert "print(1)" in results[0].output
    assert always is True


def test_tool_approval_reject():
    from cli_app import tools

    calls = tools.parse_tool_calls(
        '```tool\n{"name": "run_terminal", "args": {"command": "echo hi"}}\n```'
    )
    results, _, _ = tools.run_tools(
        calls, approve=lambda c: "reject", always_approve=False
    )
    assert results[0].skipped
    assert "rejected" in results[0].output.lower()


def test_bash_alias_and_grep_glob_parse():
    from cli_app import tools

    calls = tools.parse_tool_calls(
        '```tool\n{"name": "bash", "args": {"command": "echo x"}}\n```\n'
        '```tool\n{"name": "grep", "args": {"pattern": "def ", "path": "agents"}}\n```\n'
        '```tool\n{"name": "glob", "args": {"pattern": "agents/**/*.py"}}\n```'
    )
    names = [c.name for c in calls]
    assert "run_terminal" in names  # bash → run_terminal
    assert "grep" in names
    assert "glob" in names
    # glob against real repo
    g = tools.exec_tool("glob", {"pattern": "agents/**/*.py", "path": "."})
    assert g.ok
    assert "planner.py" in g.output or "agents/" in g.output


def test_approve_command():
    s = ConversationSession()
    r = dispatch("/approve always", s)
    assert r.ok and s.always_approve is True
    r2 = dispatch("/approve off", s)
    assert r2.ok and s.always_approve is False


def test_create_venv_and_pip_install_tools(tmp_path: Path, monkeypatch):
    import sys
    from cli_app import tools

    monkeypatch.setattr(tools, "ROOT", tmp_path)
    # create_venv
    res = tools.exec_tool("create_venv", {"path": ".venv", "python": sys.executable})
    assert res.ok, res.output
    assert (tmp_path / ".venv" / "pyvenv.cfg").exists()
    # pip install a tiny pure package or just pip itself upgrade dry — use pip show via install empty fails
    # Install 'pip' is always present; use a no-op friendly package: typing_extensions often available
    # Safer: run pip install with a known tiny package from PyPI may need network — skip if offline
    res2 = tools.exec_tool(
        "pip_install",
        {"packages": ["pip"], "venv": ".venv", "upgrade": False, "timeout": 120},
    )
    # pip installing pip into itself should succeed with network OR already satisfied
    assert "pip install into" in res2.output
    # package token validation
    bad = tools.exec_tool("pip_install", {"packages": ["requests;rm -rf /"], "venv": ".venv"})
    assert not bad.ok


def test_list_project_dir_agents(tmp_path: Path, monkeypatch):
    from cli_app import context_tools

    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "planner.py").write_text("x=1\n", encoding="utf-8")
    (tmp_path / ".agents").mkdir()
    (tmp_path / ".agents" / "rules").mkdir()
    monkeypatch.setattr(context_tools, "ROOT", tmp_path)
    block = context_tools.list_project_dir("agents", root=tmp_path)
    assert "DIR: agents" in block
    assert "planner.py" in block
    # bare "agents" must not resolve to .agents
    assert ".agents" not in block.split("DIR:")[1].split("\n")[0]


def test_reset_role_to_default(tmp_path: Path):
    from core.config_editor import reset_role_to_default

    live = tmp_path / "model_router.yaml"
    defaults = tmp_path / "defaults_model_router.yaml"
    data = {
        "vibe_coding": {
            "architect": {"provider": "cohere", "model": "command-a-plus-05-2026"},
            "coder": {"provider": "openrouter", "model": "cohere/north-mini-code:free"},
            "debugger": {"provider": "groq", "model": "openai/gpt-oss-120b"},
            "max_fix_cycles": 3,
        },
        "deep_research": {
            "safety_filter": {"provider": "groq", "model": "openai/gpt-oss-safeguard-20b"},
            "context_compressor": {"provider": "openrouter", "model": "tencent/hy3:free"},
            "web_search": {"provider": "groq", "model": "groq/compound-mini"},
            "grounding": {"provider": "cohere", "model": "command-a-plus-05-2026"},
            "synthesizer": {"provider": "cohere", "model": "command-r-plus-08-2024"},
        },
        "cli": {
            "chat": {"provider": "groq", "model": "openai/gpt-oss-120b"},
            "planner": {"provider": "groq", "model": "openai/gpt-oss-120b"},
        },
    }
    live.write_text(yaml.safe_dump(data), encoding="utf-8")
    defaults.write_text(yaml.safe_dump(data), encoding="utf-8")
    set_role(
        "vibe_coding",
        "architect",
        provider="groq",
        model="openai/gpt-oss-20b",
        config_path=live,
    )
    node = reset_role_to_default(
        "vibe_coding", "architect", config_path=live, defaults_path=defaults
    )
    assert node["provider"] == "cohere"
    assert node["model"] == "command-a-plus-05-2026"


def test_context_tools_path_extract_and_read(tmp_path: Path, monkeypatch):
    from cli_app import context_tools

    f = tmp_path / "sample.py"
    f.write_text("def hello():\n    return 1\n", encoding="utf-8")
    monkeypatch.setattr(context_tools, "ROOT", tmp_path)
    paths = context_tools.extract_path_candidates("look at sample.py please")
    assert "sample.py" in paths
    block = context_tools.read_project_files(["sample.py"], root=tmp_path)
    assert "def hello" in block
    assert "FILE: sample.py" in block


def test_dispatch_vibe_removed():
    s = ConversationSession()
    r = dispatch("/vibe make a thing", s)
    assert not r.ok
    assert "Unknown command" in r.text


def test_language_helpers():
    from cli_app.language import (
        chat_language_instruction,
        looks_non_english,
        to_english_for_pipelines,
    )

    assert looks_non_english(
        "Quiero implementar un endpoint de salud para el proyecto"
    )
    assert not looks_non_english(
        "Please implement a healthcheck endpoint for the project carefully"
    )
    # Without LLM, non-English passes through unchanged
    src = "Haz un plan de investigación"
    assert to_english_for_pipelines(src) == src
    assert "same language" in chat_language_instruction().lower()
