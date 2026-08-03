"""WAVE-13 tests: headless pipeline entry + agent-loop hygiene.

Covers the four WAVE-13 deliverables in mejoras.md lines ~1029-1075:
  1. Outer CLI `pipeline run` exists and mirrors the /do flow.
  2. The chat agent's hola-mundo write shortcut is removed (no file shortcut).
  3. `webfetch` returns readable text (not raw truncated HTML) via fetch_url.
  4. Read-only tools are batched in one run_tools call per agent loop turn.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def session():
    from cli_app.session import ConversationSession

    return ConversationSession()


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """Force cheap/no-network environment so tests are hermetic."""
    monkeypatch.setattr("cli_app.context_tools.in_multiagent_project", lambda cwd=None: False)
    monkeypatch.setattr("cli_app.graph_rag.graph_available", lambda: False)
    monkeypatch.setattr("cli_app.context_tools.gather_file_context", lambda *a, **k: "")
    monkeypatch.setattr("cli_app.context_tools.gather_dir_context", lambda *a, **k: "")


def _llm(content: str):
    from core.router import LLMResponse

    return LLMResponse(content=content, provider="x", model="y")


# --- 1. Headless CLI pipeline command ------------------------------------


def test_cli_pipeline_group_registered():
    from cli import main

    cmd = main.get_command(None, "pipeline")
    assert cmd is not None
    run = cmd.get_command(None, "run")
    assert run is not None
    opts = {p.name: p for p in run.params if hasattr(p, "name")}
    assert "gpt_researcher" in opts
    assert "provider" in opts and "model" in opts


def test_run_pipeline_planner_failure_returns_dict(monkeypatch):
    from cli_app.pipeline_cli import run_pipeline

    def boom(*a, **k):
        raise RuntimeError("planner down")

    monkeypatch.setattr("agents.planner.plan_pipelines", boom)
    res = run_pipeline("add a csv export feature", progress=lambda m: None)
    assert res["ok"] is False
    assert "planner down" in res["text"]


def test_run_pipeline_executes_plan(monkeypatch, tmp_path):
    from cli_app.pipeline_cli import run_pipeline
    from schemas.requests import PipelinePlan, PipelineStep

    step = PipelineStep(action="vibe", prompt="write code", rationale="small task")
    plan = PipelinePlan(summary="test", steps=[step])

    def fake_plan(*a, **k):
        return plan

    def fake_execute(*a, **k):
        return {
            "ok": True,
            "text": "All steps done.",
            "plan": plan.model_dump(),
            "steps": [{"action": "vibe", "status": "done"}],
        }

    monkeypatch.setattr("agents.planner.plan_pipelines", fake_plan)
    monkeypatch.setattr("cli_app.orchestrate.execute_plan", fake_execute)
    res = run_pipeline("add two numbers", progress=lambda m: None)
    assert res["ok"] is True
    assert res["steps"][0]["status"] == "done"


# --- 2. Host-side hola-mundo write hook removed ---------------------------


def test_hola_mundo_create_is_not_shortcircuited(monkeypatch, session, tmp_path):
    """A 'hola mundo crea file' prompt must NOT auto-write a file host-side."""
    from cli_app import agent_chat
    from cli_app import commands

    monkeypatch.setattr(
        agent_chat,
        "invoke_router",
        lambda *a, **k: _llm("Ok, puedo ayudarte."),
    )
    r = commands.chat_turn("hola mundo crea un archivo", session)
    assert r.ok
    # No write_file tool ran, no file created by the shortcut.
    assert r.data["tools"] == []
    created = [p for p in tmp_path.rglob("hola_mundo.py")] if tmp_path.exists() else []
    assert created == []


# --- 3. webfetch returns readable text ----------------------------------


def _fetch_result(url, text, status=None, error=""):
    from agents.deep_research.contracts import SourceResultStatus
    from agents.deep_research.source_fetch import FetchedSource

    return FetchedSource(
        url=url,
        status=status or SourceResultStatus.SUCCESS,
        http_status=200,
        text=text,
        error=error,
    )


def test_webfetch_uses_source_pipeline(monkeypatch, tmp_path):
    from cli_app import tools

    monkeypatch.setattr(tools, "ROOT", tmp_path)
    fetched = {"called": False}

    def fake_fetch(url, **k):
        fetched["called"] = True
        assert url == "https://example.com/page"
        return _fetch_result(url, "Readable page text about ships.")

    monkeypatch.setattr(
        "agents.deep_research.source_fetch.fetch_url", fake_fetch
    )
    res = tools.exec_tool(
        "webfetch", {"url": "https://example.com/page", "max_chars": 2000}
    )
    assert res.ok
    assert fetched["called"]
    assert "Readable page text" in res.output


def test_webfetch_failure_propagates(monkeypatch, tmp_path):
    from agents.deep_research.contracts import SourceResultStatus
    from cli_app import tools

    monkeypatch.setattr(tools, "ROOT", tmp_path)

    def fake_fetch(url, **k):
        return _fetch_result(
            url, "", status=SourceResultStatus.EMPTY, error="no content"
        )

    monkeypatch.setattr("agents.deep_research.source_fetch.fetch_url", fake_fetch)
    res = tools.exec_tool("webfetch", {"url": "https://example.com/x"})
    assert not res.ok
    assert "webfetch failed" in res.output


# --- 4. Read tools batched per turn -----------------------------------------


def test_chat_batches_read_tools(monkeypatch, session, tmp_path):
    from cli_app import agent_chat
    from cli_app import commands

    (tmp_path / "a.txt").write_text("AAA", encoding="utf-8")
    (tmp_path / "b.txt").write_text("BBB", encoding="utf-8")

    parser_tool_call = (
        "```tool\n{\"name\": \"read_file\", \"args\": {\"path\": \"a.txt\"}}\n```\n"
        "```tool\n{\"name\": \"read_file\", \"args\": {\"path\": \"b.txt\"}}\n```"
    )
    responses = iter(
        [
            _llm(parser_tool_call),
            _llm("Listo, leí ambos archivos."),
        ]
    )
    monkeypatch.setattr(
        agent_chat, "invoke_router", lambda *a, **k: next(responses)
    )

    captured: list[int] = []
    orig_run_tools = agent_chat.run_tools

    def wrap(calls, **k):
        captured.append(len(calls))
        return orig_run_tools(calls, **k)

    monkeypatch.setattr(agent_chat, "run_tools", wrap)
    res = commands.chat_turn("lee dos archivos", session)
    assert res.ok
    # Both read tools were passed in a single batched run_tools call.
    assert captured == [2]
    assert res.data["tools"] == ["read_file", "read_file"]