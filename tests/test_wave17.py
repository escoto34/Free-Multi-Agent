"""WAVE-17 tests: structured CLI output + cross-AI context.

Covers the WAVE-17 deliverables in mejoras.md:
  1. output.py envelope: JSON validity, block renderer, error codes, exit codes.
  2. Global --json on outer CLI (history, config, pipeline run ok/error).
  3. Planner receives chat context (/do and run_pipeline).
  4. Chat: run_pipeline tool (approval + catalog), RECENT PIPELINE RUNS seed,
     graph mtime gating.
"""

from __future__ import annotations

import json

import pytest


# --- 1. Envelope / renderers / error codes ----------------------------------


def test_envelope_json_roundtrip():
    from cli_app.output import make_envelope, render_json

    env = make_envelope(
        ok=False, message="boom", error_code="MAE-1000", detail={"prov": "groq"}
    )
    parsed = json.loads(render_json(env))
    assert parsed["status"] == "ERROR"
    assert parsed["message"] == "boom"
    assert parsed["errorCode"] == "MAE-1000"
    assert parsed["detail"] == {"prov": "groq"}
    assert parsed["timestamp"].endswith("Z")


def test_envelope_error_gets_default_code():
    from cli_app.output import make_envelope

    env = make_envelope(ok=False, message="x")
    assert env["errorCode"] == "MAE-0000"
    env_ok = make_envelope(ok=True, message="y")
    assert "errorCode" not in env_ok


def test_block_renderer_contains_fields():
    from cli_app.output import make_envelope, render_block

    block = render_block(
        make_envelope(ok=False, message="bad", error_code="MAE-1000")
    )
    assert "Status    : ERROR" in block
    assert "Message   : bad" in block
    assert "Error Code: MAE-1000" in block
    assert "Explanation" in block and "Action" in block


def test_exit_codes():
    from cli_app.output import exit_code_for_status

    assert exit_code_for_status("OK") == 0
    assert exit_code_for_status("ERROR") == 1
    assert exit_code_for_status("WARNING") == 1


# --- 2. Global --json on the outer CLI -------------------------------------


def _runner():
    from click.testing import CliRunner

    return CliRunner()


def test_history_json_envelope():
    from cli import main

    result = _runner().invoke(main, ["--json", "history", "--limit", "3"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["status"] == "OK"
    assert "detail" in parsed


def test_config_show_json_envelope():
    from cli import main

    result = _runner().invoke(main, ["--json", "config", "show"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["status"] == "OK"
    assert isinstance(parsed["detail"], dict)
    assert "roles" in parsed["detail"]


def test_config_set_usage_error_json(monkeypatch):
    from cli import main

    result = _runner().invoke(main, ["--json", "config", "set", "noperiod", "groq", "m"])
    assert result.exit_code == 2
    parsed = json.loads(result.output)
    assert parsed["status"] == "ERROR"
    assert parsed["errorCode"] == "MAE-4000"


def test_pipeline_run_json_ok(monkeypatch):
    from cli import main

    def fake_run(*a, **k):
        return {
            "ok": True,
            "status": "OK",
            "error_code": None,
            "text": "done",
            "plan": {"summary": "s", "steps": []},
            "steps": [],
        }

    monkeypatch.setattr("cli_app.pipeline_cli.run_pipeline", fake_run)
    result = _runner().invoke(
        main, ["--json", "pipeline", "run", "add a feature", "--provider", "x", "--model", "y"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["status"] == "OK"
    assert parsed["detail"]["plan"]["summary"] == "s"


def test_pipeline_run_json_error(monkeypatch):
    from cli import main

    def fake_run(*a, **k):
        return {
            "ok": False,
            "status": "ERROR",
            "error_code": "MAE-2000",
            "text": "steps failed",
            "plan": None,
            "steps": [],
        }

    monkeypatch.setattr("cli_app.pipeline_cli.run_pipeline", fake_run)
    result = _runner().invoke(
        main, ["--json", "pipeline", "run", "add a feature", "--provider", "x", "--model", "y"]
    )
    assert result.exit_code == 1
    parsed = json.loads(result.output)
    assert parsed["status"] == "ERROR"
    assert parsed["errorCode"] == "MAE-2000"


def test_pipeline_run_progress_goes_to_stderr(monkeypatch):
    from cli import main

    def fake_run(*a, **k):
        prog = k.get("progress")
        if prog:
            prog("planning…")
        return {"ok": True, "status": "OK", "text": "done", "plan": None, "steps": []}

    monkeypatch.setattr("cli_app.pipeline_cli.run_pipeline", fake_run)
    result = _runner().invoke(main, ["pipeline", "run", "x", "--provider", "p", "--model", "m"])
    assert result.exit_code == 0
    assert "planning" in result.stderr  # progress never on stdout
    assert "planning" not in result.stdout


# --- 3. Planner receives chat context ---------------------------------------


@pytest.fixture
def session():
    from cli_app.session import ConversationSession

    return ConversationSession()


def test_chat_context_block_built(session):
    from cli_app.commands import _chat_context_for_planner

    session.add("user", "estamos investigando marcas de zapatos")
    session.add("assistant", "claro, puedo ayudar")
    block = _chat_context_for_planner(session)
    assert "CHAT HISTORY" in block
    assert "estamos investigando marcas" in block


def test_run_pipeline_forwards_chat_context(monkeypatch):
    from cli_app.pipeline_cli import run_pipeline

    seen = {}

    def fake_plan(*a, **k):
        seen["context"] = k.get("context")
        from schemas.requests import PipelinePlan, PipelineStep

        return PipelinePlan(
            summary="s",
            steps=[PipelineStep(action="vibe", prompt="write a simple landing page")],
        )

    def fake_execute(*a, **k):
        return {"ok": True, "text": "ok", "plan": None, "steps": []}

    monkeypatch.setattr("agents.planner.plan_pipelines", fake_plan)
    monkeypatch.setattr("cli_app.orchestrate.execute_plan", fake_execute)
    res = run_pipeline(
        "make a landing page",
        progress=lambda m: None,
        chat_context="=== CHAT HISTORY ===\nblah",
    )
    assert res["ok"] is True
    assert "CHAT HISTORY" in (seen["context"] or "")


def test_do_merges_chat_context_into_planner(monkeypatch, session):
    from cli_app import commands

    seen = {}

    def fake_plan(*a, **k):
        seen["context"] = k.get("context") or ""
        from schemas.requests import PipelinePlan, PipelineStep

        return PipelinePlan(
            summary="s",
            steps=[PipelineStep(action="vibe", prompt="write a simple landing page")],
        )

    def fake_execute(*a, **k):
        return {"ok": True, "text": "ok", "plan": None, "steps": []}

    monkeypatch.setattr("agents.planner.plan_pipelines", fake_plan)
    monkeypatch.setattr("cli_app.orchestrate.execute_plan", fake_execute)
    session.add("assistant", "he visto la web de la competencia")
    res = commands._do(["landing", "page"], session)
    assert res.ok
    assert "CHAT HISTORY" in seen["context"]
    assert "competencia" in seen["context"]


# --- 4. Chat: run_pipeline tool + seed context ------------------------------


def test_run_pipeline_tool_in_write_tools():
    from cli_app.tools import WRITE_TOOLS, needs_approval

    assert "run_pipeline" in WRITE_TOOLS
    assert needs_approval("run_pipeline")


def test_run_pipeline_tool_requires_task():
    from cli_app.tools import exec_tool

    r = exec_tool("run_pipeline", {})
    assert not r.ok
    assert r.error_code == "MAE-3100"


def test_run_pipeline_tool_executes_with_approval(monkeypatch, session):
    from cli_app.tools import exec_tool

    captured = {}

    def fake_run(*a, **k):
        captured["chat_context"] = k.get("chat_context") or ""
        captured["task"] = k.get("task") if False else a[0]
        return {
            "ok": True,
            "status": "OK",
            "text": "plan + results",
            "plan": {"summary": "s", "steps": []},
            "steps": [],
        }

    monkeypatch.setattr("cli_app.pipeline_cli.run_pipeline", fake_run)
    session.add("user", "hablemos del negocio")
    r = exec_tool(
        "run_pipeline",
        {"task": "research the brand"},
        ctx={"session": session, "progress": lambda m: None},
    )
    assert r.ok
    assert "[run_pipeline OK]" in r.output
    assert "CHAT HISTORY" in captured["chat_context"]
    assert captured["task"] == "research the brand"


def test_chat_seed_includes_recent_runs(monkeypatch, session):
    from cli_app import agent_chat

    class FakeHistory:
        def list_recent(self, limit=4):
            return [
                {
                    "id": 1,
                    "system": "deep_research",
                    "status": "success",
                    "created_at": "2026-08-01T10:00:00Z",
                    "result_summary": "informe sobre la marca",
                    "input_summary": "brand",
                }
            ]

    monkeypatch.setattr("cli_app.context_tools.in_multiagent_project", lambda cwd=None: False)
    monkeypatch.setattr("cli_app.graph_rag.graph_available", lambda: False)
    monkeypatch.setattr("cli_app.context_tools.gather_file_context", lambda *a, **k: "")
    monkeypatch.setattr("cli_app.context_tools.gather_dir_context", lambda *a, **k: "")
    monkeypatch.setattr("core.runs.get_run_history", lambda: FakeHistory())

    seed = agent_chat._seed_context("que hizo la investigacion?", session)
    assert "RECENT PIPELINE RUNS" in seed
    assert "deep_research" in seed


def test_chat_graph_requery_gated_by_mtime(monkeypatch, session):
    from cli_app import agent_chat

    calls = {"n": 0}
    mtime = {"v": 12345.0}

    monkeypatch.setattr("cli_app.context_tools.in_multiagent_project", lambda cwd=None: True)
    monkeypatch.setattr("cli_app.graph_rag.graph_available", lambda: True)
    monkeypatch.setattr("cli_app.context_tools.gather_file_context", lambda *a, **k: "")
    monkeypatch.setattr("cli_app.context_tools.gather_dir_context", lambda *a, **k: "")

    def fake_query(q, budget=1200):
        calls["n"] += 1
        return "node: agents/planner.py"

    monkeypatch.setattr("cli_app.graph_rag.query_graph", fake_query)
    monkeypatch.setattr("cli_app.context_tools.graph_mtime", lambda: mtime["v"])
    monkeypatch.setattr("core.runs.get_run_history", lambda: FakeHistoryEmpty())

    seed1 = agent_chat._seed_context("que hay en agents?", session)
    assert calls["n"] == 1
    assert "KNOWLEDGE GRAPH" in seed1

    # Same mtime: no re-query, cached snippet reused.
    seed2 = agent_chat._seed_context("sigue contando de agents", session)
    assert calls["n"] == 1
    assert seed2 == seed1

    # Graph changed: re-query once more.
    mtime["v"] = 99999.0
    session.graph_mtime_at_inject = None
    session.graph_used = False
    agent_chat._seed_context("una vez mas", session)
    assert calls["n"] == 2


class FakeHistoryEmpty:
    def list_recent(self, limit=4):
        return []


def test_approval_rejection_has_error_code(session):
    from cli_app.tools import ToolCall, run_tools

    results, _, rejected = run_tools(
        [ToolCall(name="run_pipeline", args={"task": "x"})],
        approve=lambda call: "reject",
    )
    assert rejected
    assert results[0].skipped
    assert results[0].error_code == "MAE-3000"
