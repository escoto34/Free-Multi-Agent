"""
Difficulty → reasoning_effort kwargs (offline, no HTTP).

Free-tier limits are per-call: effort must not invent extra calls.
"""

from __future__ import annotations

from core.difficulty_scorer import DifficultyAssessment
from core.reasoning_params import (
    difficulty_to_effort,
    reload_reasoning_config,
    resolve_reasoning_kwargs,
    sanitize_call_kwargs,
    strip_reasoning_kwargs,
)
from core.model_selector import reload_benchmarks
from core.agent_config import reload_config


def setup_function():
    reload_config()
    reload_benchmarks()
    reload_reasoning_config()


def test_easy_task_low_effort_on_gpt_oss():
    assess = DifficultyAssessment(
        code=30, reason=30, overall=35, role_path="vibe_coding.debugger"
    )
    # debugger min_effort=medium → clamp up from low
    effort = difficulty_to_effort(assess, role_path="vibe_coding.debugger")
    assert effort == "medium"

    # architect has min low → stays low for easy
    effort_a = difficulty_to_effort(assess, role_path="vibe_coding.architect")
    assert effort_a == "low"

    kw = resolve_reasoning_kwargs(
        "groq",
        "openai/gpt-oss-120b",
        assessment=assess,
        role_path="vibe_coding.architect",
    )
    assert kw["reasoning_effort"] == "low"
    assert kw["include_reasoning"] is False


def test_hard_task_high_effort_debugger():
    assess = DifficultyAssessment(
        code=90,
        reason=92,
        overall=90,
        role_path="vibe_coding.debugger",
    )
    effort = difficulty_to_effort(assess, role_path="vibe_coding.debugger")
    assert effort == "high"
    kw = resolve_reasoning_kwargs(
        "groq",
        "openai/gpt-oss-120b",
        assessment=assess,
        role_path="vibe_coding.debugger",
    )
    assert kw["reasoning_effort"] == "high"
    assert kw.get("include_reasoning") is False


def test_safety_filter_caps_at_low():
    assess = DifficultyAssessment(
        safety=95, overall=95, role_path="deep_research.safety_filter"
    )
    effort = difficulty_to_effort(assess, role_path="deep_research.safety_filter")
    assert effort == "low"
    kw = resolve_reasoning_kwargs(
        "groq",
        "openai/gpt-oss-safeguard-20b",
        assessment=assess,
        role_path="deep_research.safety_filter",
    )
    assert kw["reasoning_effort"] == "low"


def test_unsupported_model_gets_no_reasoning_kwargs():
    assess = DifficultyAssessment(code=90, overall=90)
    kw = resolve_reasoning_kwargs(
        "mistral",
        "codestral-latest",
        assessment=assess,
        role_path="vibe_coding.coder",
    )
    assert kw == {}
    kw2 = resolve_reasoning_kwargs(
        "agnes",
        "agnes-2.0-flash",
        assessment=assess,
        role_path="vibe_coding.architect",
    )
    assert kw2 == {}


def test_cascade_sanitize_strips_then_reapplies_for_next_model():
    assess = DifficultyAssessment(code=85, reason=85, overall=85)
    incoming = {
        "reasoning_effort": "high",
        "include_reasoning": False,
        "max_tokens": 4096,
    }
    # Agnes does not support reasoning → strip only
    clean = sanitize_call_kwargs(
        "agnes",
        "agnes-2.0-flash",
        incoming,
        assessment=assess,
        role_path="vibe_coding.debugger",
    )
    assert "reasoning_effort" not in clean
    assert clean["max_tokens"] == 4096

    # gpt-oss keeps/re-maps effort (debugger min medium, hard → high)
    clean2 = sanitize_call_kwargs(
        "groq",
        "openai/gpt-oss-120b",
        incoming,
        assessment=assess,
        role_path="vibe_coding.debugger",
    )
    assert clean2["reasoning_effort"] == "high"
    assert clean2["max_tokens"] == 4096


def test_strip_reasoning_kwargs_helper():
    raw = {
        "reasoning_effort": "high",
        "include_reasoning": True,
        "reasoning_format": "parsed",
        "temperature": 0.2,
    }
    assert strip_reasoning_kwargs(raw) == {"temperature": 0.2}


def test_invoke_router_merges_reasoning_for_mock():
    """agent_runtime.invoke_router injects kwargs without HTTP."""
    from core.agent_runtime import invoke_router
    from core.router import LLMResponse

    captured: dict = {}

    def mock_router(**kw):
        captured.update(kw)
        return LLMResponse(content='{"ok": true}', provider=kw["provider"], model=kw["model"])

    assess = DifficultyAssessment(
        code=88, reason=90, overall=88, role_path="vibe_coding.debugger"
    )
    invoke_router(
        mock_router,
        provider="groq",
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": "fix race condition"}],
        assessment=assess,
        role_path="vibe_coding.debugger",
    )
    assert captured["reasoning_effort"] == "high"
    assert captured["include_reasoning"] is False
    assert captured.get("_difficulty_assessment") is assess


def test_invoke_router_no_reasoning_on_codestral():
    from core.agent_runtime import invoke_router
    from core.router import LLMResponse

    captured: dict = {}

    def mock_router(**kw):
        captured.update(kw)
        return LLMResponse(content="{}", provider=kw["provider"], model=kw["model"])

    assess = DifficultyAssessment(code=90, overall=90)
    invoke_router(
        mock_router,
        provider="mistral",
        model="codestral-latest",
        messages=[{"role": "user", "content": "hard code"}],
        assessment=assess,
        role_path="vibe_coding.coder",
    )
    assert "reasoning_effort" not in captured
