"""
Difficulty scoring + model selection (primary vs fallback) + hy3 expiry.

Covers systems.md §4.3 policy and task checklist:
  (a) easy task → stay on primary
  (b) hard + primary degraded → fallback via handoff (audited)
  (c) healthy primary + easy → NO switch even if fallback edges higher
  (d) free_until expired (hy3) → automatic fallback

All tests are offline: no real HTTP / quota consumption.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

from core.difficulty_scorer import (
    DifficultyAssessment,
    plan_pipeline_difficulties,
    score_task_difficulty,
)
from core.handoff import HandoffError
from core.model_selector import (
    get_model_scores,
    hy3_status,
    is_model_available,
    record_model_selection_handoff,
    reload_benchmarks,
    select_for_role,
)
from core.agent_config import reload_config


@pytest.fixture(autouse=True)
def _reload_yaml_caches():
    reload_config()
    reload_benchmarks()
    yield
    reload_config()
    reload_benchmarks()


# ---------------------------------------------------------------------------
# (a) Easy task → stay on primary
# ---------------------------------------------------------------------------


def test_easy_task_stays_on_coder_primary():
    """Simple coding task → Codestral primary (not Agnes fallback)."""
    easy = (
        "Write a simple function that returns hello world. "
        "Just print a greeting. Minimal todo list helper."
    )
    assess = score_task_difficulty(easy, role_path="vibe_coding.coder", subtask="coder")
    assert assess.overall < 70
    assert assess.code < 70

    sel = select_for_role("vibe_coding", "coder", assessment=assess)
    assert sel.used_fallback is False
    assert sel.forced_expiry is False
    assert sel.provider == "mistral"
    assert sel.model == "codestral-latest"


def test_easy_architect_stays_on_primary():
    assess = score_task_difficulty(
        "Design a small hello world script.",
        role_path="vibe_coding.architect",
    )
    sel = select_for_role("vibe_coding", "architect", assessment=assess)
    assert sel.used_fallback is False
    assert sel.provider == "agnes"
    assert sel.model == "agnes-2.0-flash"


# ---------------------------------------------------------------------------
# (b) Hard task + primary degraded → fallback + handoff audited
# ---------------------------------------------------------------------------


def test_hard_task_degraded_primary_switches_and_handoff():
    """High difficulty alone is not enough; with quota_exhausted → Gemini + handoff."""
    assess = DifficultyAssessment(
        code=40,
        reason=92,
        ground=20,
        synth=55,
        safety=20,
        logic_complexity=90,
        error_handling_complexity=40,
        estimated_context_tokens=8000,
        overall=88,
        rationale="multi-step architecture tradeoffs",
        subtask="architect",
        role_path="vibe_coding.architect",
    )
    # Healthy: stay Agnes even if Gemini edges reason 78 vs 76 (Δ=2 < 8)
    sel_ok = select_for_role(
        "vibe_coding", "architect", assessment=assess, primary_status="ok"
    )
    assert sel_ok.used_fallback is False
    assert sel_ok.provider == "agnes"

    # Degraded: operational switch to role fallback (systems.md §4.3)
    sel = select_for_role(
        "vibe_coding",
        "architect",
        assessment=assess,
        primary_status="quota_exhausted",
    )
    assert sel.used_fallback is True
    assert sel.provider == "gemini"
    assert sel.model == "gemini-2.0-flash"
    assert "degraded" in sel.reason.lower() or "quota" in sel.reason.lower()

    state = {
        "idea": "Design a complex distributed system",
        "handoff_history": [],
        "spec": None,
        "error": None,
    }
    patch = record_model_selection_handoff(
        state,
        sel,
        role="architect",
        user_input_key="idea",
        pipeline="vibe_coding",
    )
    assert "handoff_history" in patch
    assert len(patch["handoff_history"]) == 1
    rec = patch["handoff_history"][0]
    assert rec["user_input"] == "Design a complex distributed system"
    assert "architect@" in rec["to_agent"]
    assert "gemini" in rec["to_agent"]
    assert patch["last_model_selection"]["used_fallback"] is True
    assert patch["last_model_selection"]["primary_status"] == "quota_exhausted"


def test_empty_completion_degraded_switches_coder():
    assess = DifficultyAssessment(
        code=80,
        reason=60,
        overall=75,
        subtask="coder",
        role_path="vibe_coding.coder",
    )
    sel = select_for_role(
        "vibe_coding",
        "coder",
        assessment=assess,
        primary_status="empty_completion",
    )
    assert sel.used_fallback is True
    assert sel.provider == "agnes"
    assert sel.model == "agnes-2.0-flash"


def test_hard_keyword_heuristic_raises_code_difficulty():
    text = (
        "Refactor the entire distributed concurrency pipeline with "
        "race-condition-free lock-free async workers and cryptography."
    )
    assess = score_task_difficulty(text, role_path="vibe_coding.coder")
    assert assess.code >= 70
    assert assess.logic_complexity >= 70


def test_mis_specialized_weak_primary_switches(tmp_path: Path):
    """Safeguard-as-coder (code 35) vs Agnes (code 78): Δ≥8 and weak primary → fallback."""
    router_yaml = {
        "providers": {},
        "vibe_coding": {
            "coder": {
                "provider": "groq",
                "model": "openai/gpt-oss-safeguard-20b",
                "fallback": {
                    "provider": "agnes",
                    "model": "agnes-2.0-flash",
                },
            }
        },
    }
    cfg_path = tmp_path / "model_router.yaml"
    cfg_path.write_text(yaml.safe_dump(router_yaml), encoding="utf-8")

    assess = DifficultyAssessment(
        code=75,
        reason=40,
        overall=70,
        subtask="coder",
        role_path="vibe_coding.coder",
    )
    sel = select_for_role(
        "vibe_coding",
        "coder",
        assessment=assess,
        config_path=cfg_path,
        primary_status="ok",
    )
    assert sel.used_fallback is True
    assert sel.provider == "agnes"
    assert "mis-specialized" in sel.reason.lower() or "Mis-specialized" in sel.reason


# ---------------------------------------------------------------------------
# (c) Healthy primary → NO switch even if fallback scores slightly higher
# ---------------------------------------------------------------------------


def test_healthy_primary_no_switch_when_fallback_edges_higher():
    """Gemini reason 78 > Agnes 76 (Δ=2 < 8). Healthy + mid difficulty → keep Agnes."""
    assess = DifficultyAssessment(
        code=45,
        reason=55,
        ground=20,
        synth=50,
        safety=20,
        overall=52,
        rationale="mid plan",
        subtask="architect",
        role_path="vibe_coding.architect",
    )
    sel = select_for_role(
        "vibe_coding", "architect", assessment=assess, primary_status="ok"
    )
    assert sel.used_fallback is False
    assert sel.provider == "agnes"
    assert sel.model == "agnes-2.0-flash"


def test_healthy_coder_no_switch_even_on_hard_task():
    """Codestral code 88 is best-in-stack; hard task alone must not leave primary."""
    assess = DifficultyAssessment(
        code=95,
        reason=80,
        overall=90,
        subtask="coder",
        role_path="vibe_coding.coder",
    )
    sel = select_for_role(
        "vibe_coding", "coder", assessment=assess, primary_status="ok"
    )
    assert sel.used_fallback is False
    assert sel.provider == "mistral"
    assert sel.model == "codestral-latest"


# ---------------------------------------------------------------------------
# (d) hy3 expired → automatic fallback (no YAML edit / no HTTP)
# ---------------------------------------------------------------------------


def test_hy3_available_before_expiry():
    assert is_model_available(
        "openrouter",
        "tencent/hy3:free",
        today=date(2026, 7, 17),
    )
    st = hy3_status(today=date(2026, 7, 17))
    assert st["expired"] is False
    assert st["days_remaining"] == 4


def test_hy3_expired_status():
    st = hy3_status(today=date(2026, 7, 22))
    assert st["expired"] is True
    assert st["days_remaining"] < 0
    assert st["expired_fallback"]["model"] == "openai/gpt-oss-120b"
    assert not is_model_available(
        "openrouter",
        "tencent/hy3:free",
        today=date(2026, 7, 22),
    )


def test_hy3_expired_scores_capped_at_49():
    """Auto-scorer cap after free_until (systems.md: cap ≤49 when expired)."""
    live = get_model_scores(
        "openrouter", "tencent/hy3:free", today=date(2026, 7, 17)
    )
    assert live.get("reason", 0) == 60  # uncapped table value
    dead = get_model_scores(
        "openrouter", "tencent/hy3:free", today=date(2026, 7, 22)
    )
    assert all(v <= 49 for v in dead.values())


def test_hy3_expired_role_auto_fallback(tmp_path: Path):
    """Role primary hy3 past free_until → selection uses fallback without user action."""
    router_yaml = {
        "providers": {},
        "vibe_coding": {
            "debugger": {
                "provider": "openrouter",
                "model": "tencent/hy3:free",
                "free_until": "2026-07-21",
                "fallback": {
                    "provider": "groq",
                    "model": "openai/gpt-oss-120b",
                },
            }
        },
    }
    cfg_path = tmp_path / "model_router.yaml"
    cfg_path.write_text(yaml.safe_dump(router_yaml), encoding="utf-8")

    assess = DifficultyAssessment(
        code=50,
        reason=50,
        ground=20,
        synth=40,
        safety=20,
        overall=50,
        rationale="mid",
        subtask="debugger",
        role_path="vibe_coding.debugger",
    )
    # Before expiry: hy3 still selectable as primary
    sel_ok = select_for_role(
        "vibe_coding",
        "debugger",
        assessment=assess,
        today=date(2026, 7, 17),
        config_path=cfg_path,
    )
    assert sel_ok.provider == "openrouter"
    assert sel_ok.model == "tencent/hy3:free"
    assert sel_ok.forced_expiry is False

    # After expiry: auto fallback to gpt-oss-120b
    sel_exp = select_for_role(
        "vibe_coding",
        "debugger",
        assessment=assess,
        today=date(2026, 7, 22),
        config_path=cfg_path,
    )
    assert sel_exp.used_fallback is True
    assert sel_exp.forced_expiry is True
    assert sel_exp.provider == "groq"
    assert sel_exp.model == "openai/gpt-oss-120b"

    # Handoff must preserve user context
    state = {"idea": "fix the race condition", "handoff_history": []}
    patch = record_model_selection_handoff(
        state,
        sel_exp,
        role="debugger",
        user_input_key="idea",
        pipeline="vibe_coding",
    )
    assert patch["handoff_history"][-1]["user_input"] == "fix the race condition"
    assert "gpt-oss-120b" in patch["handoff_history"][-1]["to_agent"]


def test_handoff_refuses_empty_user_on_model_switch():
    assess = DifficultyAssessment(overall=90, reason=90, code=40)
    sel = select_for_role(
        "vibe_coding",
        "architect",
        assessment=assess,
        primary_status="rate_limited_429",
    )
    with pytest.raises(HandoffError):
        record_model_selection_handoff(
            {"idea": "", "handoff_history": []},
            sel,
            role="architect",
            user_input_key="idea",
            pipeline="vibe_coding",
        )


def test_plan_pipeline_difficulties_vibe_has_coder_and_debugger():
    plans = plan_pipeline_difficulties("Build a REST API", pipeline="vibe_coding")
    assert "coder" in plans
    assert "debugger" in plans
    assert "architect" in plans
    assert isinstance(plans["coder"], DifficultyAssessment)


def test_resolve_role_selection_easy_no_http():
    """agent_runtime.resolve_role_selection stays offline for easy tasks."""
    from core.agent_runtime import resolve_role_selection

    provider, model, fb, sel, assess = resolve_role_selection(
        "vibe_coding",
        "coder",
        messages=[{"role": "user", "content": "simple hello world function"}],
    )
    assert provider == "mistral"
    assert model == "codestral-latest"
    assert sel is not None
    assert sel.used_fallback is False
    assert assess is not None
