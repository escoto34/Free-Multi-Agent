"""Tests for pipeline planner schema and orchestration chaining."""

from __future__ import annotations

from schemas.requests import PipelinePlan, PipelineStep
from agents.planner import format_plan
from cli_app.orchestrate import (
    execute_plan,
    ensure_origin_urls_in_research_prompt,
    _summarize_step_output,
)


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
        assert "GROUNDED FACTS" in prompt  # research→vibe hard constraints
        assert "PRIOR RESEARCH CONTEXT" in prompt
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


def test_execute_plan_shows_full_research_report(monkeypatch):
    """User-facing /do text must include the whole research body, not a 400-char stub."""
    long_body = (
        "Verified Report: AcmeBrand Clinic, Example City, Exampleland\n"
        "This report summarizes AcmeBrand based on public sources.\n"
        "Company Background\n"
        "AcmeBrand's founding date is not readily available. "
        "The clinic's website, acmebrand.test.com, positions the brand as a "
        "modern dental practice in Example City with implants and aesthetics.\n"
    ) + ("Detail paragraph about services and locations. " * 40)

    def fake_research(prompt: str):
        return {
            "content": long_body,
            "sources": ["https://acmebrand.test.com", "https://example.com/reviews"],
            "is_safe": True,
            "error": None,
        }

    monkeypatch.setattr("cli_app.orchestrate._run_research", fake_research)

    plan = PipelinePlan(
        summary="Research AcmeBrand",
        steps=[
            PipelineStep(
                action="research",
                prompt="AcmeBrand Example City",
                uses_prior=False,
            ),
        ],
    )
    result = execute_plan(plan)
    assert result["ok"] is True
    text = result["text"]
    assert "acmebrand.test.com" in text
    assert "implants and aesthetics" in text
    assert long_body in text or long_body.strip() in text
    assert "https://acmebrand.test.com" in text
    # Must not stop after the old ~400-char step summary cut.
    assert len(text) > 800


def test_execute_plan_research_then_vibe_with_long_prior(monkeypatch):
    """Prior research context must reach vibe without schema max_length failure."""
    long_body = "Research findings on AcmeBrand. " * 200  # >4k when wrapped
    vibe_prompts: list[str] = []

    def fake_research(prompt: str):
        return {
            "content": long_body,
            "sources": ["https://www.acmebrand.test.com"],
            "is_safe": True,
            "error": None,
        }

    def fake_vibe(prompt: str):
        vibe_prompts.append(prompt)
        return {
            "passed": True,
            "fix_attempts": 1,
            "files_written": [{"path": "reports/acmebrand.md", "lines": 40}],
            "summary": "wrote report",
            "error": None,
        }

    monkeypatch.setattr("cli_app.orchestrate._run_research", fake_research)
    monkeypatch.setattr("cli_app.orchestrate._run_vibe", fake_vibe)

    plan = PipelinePlan(
        summary="Research then report",
        steps=[
            PipelineStep(action="research", prompt="Research AcmeBrand", uses_prior=False),
            PipelineStep(
                action="vibe",
                prompt="Compile a Markdown research report file from the prior findings.",
                uses_prior=True,
            ),
        ],
    )
    result = execute_plan(plan)
    assert result["ok"] is True
    assert len(vibe_prompts) == 1
    assert "PRIOR RESEARCH CONTEXT" in vibe_prompts[0] or "GROUNDED FACTS" in vibe_prompts[0]
    assert "AcmeBrand" in vibe_prompts[0]
    assert "AcmeBrand" in vibe_prompts[0]
    assert len(vibe_prompts[0]) > 4000


def test_ensure_origin_urls_reinjects_dropped_domain():
    step = (
        "Deep-dive Credental in Colonia Trejo, San Pedro Sula. "
        "Find address, social, and competitors."
    )
    origin = (
        "investiga Credental clinica dental Honduras Colonia Trejo "
        "pagina web actual: credentalhn.com imagen de marca"
    )
    out = ensure_origin_urls_in_research_prompt(step, origin)
    assert "credentalhn.com" in out
    assert "USER-NAMED OFFICIAL" in out
    # Already present → no duplicate enrichment block
    same = ensure_origin_urls_in_research_prompt(
        step + " official site credentalhn.com", origin
    )
    assert "USER-NAMED OFFICIAL" not in same


def test_execute_plan_injects_origin_url_into_research(monkeypatch):
    """Planner dropping the official domain must not starve PRIMARY fetch."""
    research_prompts: list[str] = []

    def fake_research(prompt: str):
        research_prompts.append(prompt)
        return {
            "content": "Clinic found at official site.",
            "sources": ["https://credentalhn.com"],
            "is_safe": True,
            "error": None,
        }

    monkeypatch.setattr("cli_app.orchestrate._run_research", fake_research)

    plan = PipelinePlan(
        summary="Research only",
        steps=[
            PipelineStep(
                action="research",
                # Planner rewrote without the domain
                prompt="Investigate Credental dental clinic Colonia Trejo SPS",
                uses_prior=False,
            ),
        ],
    )
    origin = "Credental Colonia Trejo website credentalhn.com brand image"
    result = execute_plan(plan, origin_prompt=origin)
    assert result["ok"] is True
    assert len(research_prompts) == 1
    assert "credentalhn.com" in research_prompts[0]
    assert "USER-NAMED OFFICIAL" in research_prompts[0]
