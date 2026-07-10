"""Tests for pipeline planner schema and orchestration chaining."""

from __future__ import annotations

from schemas.requests import PipelinePlan, PipelineStep
from agents.planner import format_plan
from cli_app.orchestrate import execute_plan, _summarize_step_output


def test_pipeline_plan_schema():
    plan = PipelinePlan(
        summary="Research then implement",
        steps=[
            PipelineStep(
                action="research",
                prompt="Latest free LLM APIs",
                rationale="need facts",
                uses_prior=False,
            ),
            PipelineStep(
                action="vibe",
                prompt="Add README section from research",
                rationale="code uses research",
                uses_prior=True,
            ),
        ],
    )
    assert len(plan.steps) == 2
    text = format_plan(plan)
    assert "research" in text
    assert "vibe" in text
    assert "+prior" in text


def test_execute_plan_chains_prior(monkeypatch):
    calls: list[tuple[str, str]] = []

    def fake_research(prompt: str):
        calls.append(("research", prompt))
        return {
            "content": "API X is free",
            "sources": ["http://x.test"],
            "is_safe": True,
            "error": None,
        }

    def fake_vibe(prompt: str):
        calls.append(("vibe", prompt))
        assert "API X is free" in prompt  # prior context injected
        return {
            "passed": True,
            "fix_attempts": 1,
            "files_written": [{"path": "README.md", "lines": 10}],
            "summary": "updated readme",
            "error": None,
        }

    monkeypatch.setattr("cli_app.orchestrate._run_research", fake_research)
    monkeypatch.setattr("cli_app.orchestrate._run_vibe", fake_vibe)

    plan = PipelinePlan(
        summary="both",
        steps=[
            PipelineStep(action="research", prompt="find free APIs", uses_prior=False),
            PipelineStep(
                action="vibe",
                prompt="document them",
                uses_prior=True,
            ),
        ],
    )
    result = execute_plan(plan)
    assert result["ok"] is True
    assert len(calls) == 2
    assert calls[0][0] == "research"
    assert calls[1][0] == "vibe"


def test_summarize_research():
    s = _summarize_step_output(
        "research",
        {"content": "hello", "sources": ["http://a"], "is_safe": True},
    )
    assert "hello" in s
    assert "http://a" in s
