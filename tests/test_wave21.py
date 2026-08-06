"""
WAVE-21 — score-driven routing + cli.chat wiring.

Covers the wave's mandatory tests:

* ``select_for_role`` ranks by ``fitness()`` with hysteresis (anti-churn).
* ``hard_threshold`` genuinely escalates on hard-task fixtures.
* ``primary_status`` is derived from a mocked ``quota_remaining`` ledger.
* ``pin: true`` (deep_research.web_search) blocks every possible swap.
* ``cli.chat`` bypass removed: a chat turn's selection record carries its
  ``role_path`` (previously it never did).
* ``difficulty_scorer``'s ``cli.chat`` role-bias branch fires.

All offline / synthetic: no real quota ledger, no HTTP.
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from core.difficulty_scorer import DifficultyAssessment, score_task_difficulty
from core.model_selector import reload_benchmarks, select_for_role

# ---------------------------------------------------------------------------
# Synthetic helpers
# ---------------------------------------------------------------------------


def _row(scores: dict[str, int], eff: float) -> dict[str, Any]:
    """Benchmark row with a single scalar efficiency (stack-relative rubric)."""
    return {
        "scores": scores,
        "efficiency": {
            "speed_score": eff,
            "context_score": eff,
            "capacity_score": eff,
        },
        "evidence": "provisional",
        "verified": "2026-08-05",
        "available": True,
    }


def _bench(
    models: dict[str, dict[str, Any]],
    coder_hard: int = 70,
) -> dict[str, Any]:
    return {
        "models": models,
        "roles": {
            "vibe_coding.coder": {
                "relevant_areas": ["code", "reason"],
                "hard_threshold": coder_hard,
            },
            "deep_research.web_search": {
                "relevant_areas": ["ground"],
                "hard_threshold": 90,
                "pin": True,
            },
        },
        "selection_defaults": {
            "score_advantage_threshold": 8,
            "quality_weight": 0.75,
            "efficiency_weight": 0.25,
        },
    }


def _write_yaml(tmp_path: Any, name: str, data: dict[str, Any]) -> Any:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def _assess(code: int, reason: int, overall: int) -> DifficultyAssessment:
    return DifficultyAssessment(
        code=code,
        reason=reason,
        ground=20,
        synth=50,
        safety=20,
        overall=overall,
        subtask="coder",
        role_path="vibe_coding.coder",
    )


@pytest.fixture(autouse=True)
def _reload():
    from core.agent_config import reload_config

    reload_config()
    reload_benchmarks()
    yield
    reload_config()
    reload_benchmarks()


# ---------------------------------------------------------------------------
# Hysteresis: no switch on a marginal fitness edge (< score_advantage_threshold)
# ---------------------------------------------------------------------------


def test_hysteresis_no_switch_when_best_candidate_edges_below_threshold(tmp_path):
    """Primary edges a slightly-better candidate by <8 fitness → stay on primary."""
    bench = _bench(
        {
            "primary/quality": _row(
                {"code": 70, "reason": 70, "ground": 40, "synth": 55, "safety": 35}, 90.0
            ),
            "fallback/edge": _row(
                {"code": 74, "reason": 74, "ground": 40, "synth": 55, "safety": 35}, 80.0
            ),
        }
    )
    bench_path = _write_yaml(tmp_path, "bench.yaml", bench)
    cfg_path = _write_yaml(
        tmp_path,
        "router.yaml",
        _assessor_router(("primary", "quality"), ("fallback", "edge")),
    )

    sel = select_for_role(
        "vibe_coding", "coder", assessment=_assess(40, 40, 40),
        config_path=cfg_path, benchmarks_path=bench_path,
    )
    assert sel.used_fallback is False
    assert sel.provider == "primary"
    assert sel.model == "quality"


def test_hysteresis_switches_when_candidate_clearly_better(tmp_path):
    """A candidate beating the primary by >= score_advantage_threshold wins."""
    bench = _bench(
        {
            "primary/weak": _row(
                {"code": 60, "reason": 60, "ground": 40, "synth": 55, "safety": 35}, 80.0
            ),
            "best/wins": _row(
                {"code": 88, "reason": 88, "ground": 40, "synth": 55, "safety": 35}, 90.0
            ),
        }
    )
    bench_path = _write_yaml(tmp_path, "bench.yaml", bench)
    cfg_path = _write_yaml(
        tmp_path, "router.yaml", _assessor_router(("primary", "weak"), ("best", "wins"))
    )

    sel = select_for_role(
        "vibe_coding", "coder", assessment=_assess(50, 50, 50),
        config_path=cfg_path, benchmarks_path=bench_path,
    )
    assert sel.used_fallback is True
    assert sel.provider == "best"
    assert sel.model == "wins"
    assert "score-driven" in sel.reason.lower()


def _assessor_router(primary: tuple[str, str], fallback: tuple[str, str]) -> dict[str, Any]:
    return {
        "providers": {},
        "vibe_coding": {
            "coder": {
                "provider": primary[0],
                "model": primary[1],
                "fallback": {"provider": fallback[0], "model": fallback[1]},
            }
        },
    }


# ---------------------------------------------------------------------------
# hard_threshold: escalate on hard tasks to a model that clears the quality gate
# ---------------------------------------------------------------------------


def test_hard_threshold_escalates_on_hard_task(tmp_path):
    """Easy task: efficient primary keeps its seat. Hard task
    (relevant_max >= 70): primary quality (57.5) < 70 → escalate to the
    higher-quality candidate despite its lower overall fitness."""
    bench = _bench(
        {
            "primary/med": _row(
                {"code": 55, "reason": 60, "ground": 40, "synth": 55, "safety": 35}, 100.0
            ),
            "strong/high": _row(
                {"code": 90, "reason": 90, "ground": 40, "synth": 55, "safety": 35}, 0.0
            ),
        }
    )
    bench_path = _write_yaml(tmp_path, "bench.yaml", bench)
    cfg_path = _write_yaml(
        tmp_path, "router.yaml", _assessor_router(("primary", "med"), ("strong", "high"))
    )

    easy = select_for_role(
        "vibe_coding", "coder", assessment=_assess(40, 40, 45),
        config_path=cfg_path, benchmarks_path=bench_path,
    )
    assert easy.used_fallback is False
    assert easy.provider == "primary"

    hard = select_for_role(
        "vibe_coding", "coder", assessment=_assess(85, 90, 88),
        config_path=cfg_path, benchmarks_path=bench_path,
    )
    assert hard.used_fallback is True
    assert hard.provider == "strong"
    assert hard.model == "high"


def test_hard_threshold_graceful_when_no_candidate_clears_gate(tmp_path):
    """No candidate clears the quality gate on a hard task → keep primary."""
    bench = _bench(
        {
            "primary/q": _row(
                {"code": 40, "reason": 45, "ground": 40, "synth": 55, "safety": 35}, 100.0
            ),
            "other/r": _row(
                {"code": 50, "reason": 50, "ground": 40, "synth": 55, "safety": 35}, 0.0
            ),
        },
        coder_hard=60,
    )
    bench_path = _write_yaml(tmp_path, "bench.yaml", bench)
    cfg_path = _write_yaml(
        tmp_path, "router.yaml", _assessor_router(("primary", "q"), ("other", "r"))
    )

    sel = select_for_role(
        "vibe_coding", "coder", assessment=_assess(80, 80, 80),
        config_path=cfg_path, benchmarks_path=bench_path,
    )
    assert sel.used_fallback is False
    assert sel.provider == "primary"
    assert sel.model == "q"


# ---------------------------------------------------------------------------
# pin: web_search never swapped, regardless of fitness deltas
# ---------------------------------------------------------------------------


def test_pinned_web_search_never_swapped(tmp_path):
    """A competitor that dwarfs compound-mini in fitness — pin still refuses."""
    bench = _bench(
        {
            "groq/groq/compound-mini": _row(
                {"ground": 85, "code": 30, "reason": 30, "synth": 30, "safety": 30}, 0.0
            ),
            "fake/strong": _row(
                {"ground": 99, "code": 99, "reason": 99, "synth": 99, "safety": 99}, 100.0
            ),
        }
    )
    bench_path = _write_yaml(tmp_path, "bench.yaml", bench)
    cfg_path = _write_yaml(
        tmp_path,
        "router.yaml",
        {
            "providers": {},
            "deep_research": {
                "web_search": {"provider": "groq", "model": "groq/compound-mini"}
            },
        },
    )

    assess = DifficultyAssessment(
        ground=90, overall=85, role_path="deep_research.web_search", subtask="web_search"
    )
    sel = select_for_role(
        "deep_research", "web_search", assessment=assess,
        config_path=cfg_path, benchmarks_path=bench_path,
    )
    assert sel.provider == "groq"
    assert sel.model == "groq/compound-mini"
    assert sel.used_fallback is False
    assert "pinned" in sel.reason.lower()


# ---------------------------------------------------------------------------
# quota-derived primary_status
# ---------------------------------------------------------------------------


def test_quota_derived_status_from_mocked_tracker(tmp_path):
    bench = _bench(
        {
            "primary/q": _row(
                {"code": 70, "reason": 70, "ground": 40, "synth": 55, "safety": 35}, 100.0
            ),
            "healthy/r": _row(
                {"code": 80, "reason": 80, "ground": 40, "synth": 55, "safety": 35}, 0.0
            ),
        }
    )
    bench_path = _write_yaml(tmp_path, "bench.yaml", bench)
    cfg_path = _write_yaml(
        tmp_path, "router.yaml", _assessor_router(("primary", "q"), ("healthy", "r"))
    )

    def quota(provider, model):
        return 0 if provider == "primary" else 10

    sel = select_for_role(
        "vibe_coding", "coder", assessment=_assess(50, 50, 50),
        config_path=cfg_path, benchmarks_path=bench_path,
        primary_status="ok", quota_remaining=quota,
    )
    assert sel.primary_status == "quota_exhausted"
    assert sel.used_fallback is True
    assert sel.provider == "healthy"
    assert sel.model == "r"
    assert "degraded" in sel.reason.lower() or "quota" in sel.reason.lower()


# ---------------------------------------------------------------------------
# cli.chat routing + difficulty bias
# ---------------------------------------------------------------------------


def test_chat_turn_selection_carries_role_path(monkeypatch):
    from cli_app import agent_chat
    from cli_app.session import ConversationSession
    from core.model_selector import ModelSelection

    from_cli = ModelSelection(
        provider="cerebras",
        model="gpt-oss-120b",
        used_fallback=False,
        reason="cli.chat now routed via role selection",
        role_path=("cli", "chat"),
        primary_provider="cerebras",
        primary_model="gpt-oss-120b",
    )

    def fake_resolve(*args, **kwargs):
        return "cerebras", "gpt-oss-120b", {"provider": "agnes", "model": "agnes-2.0-flash"}, from_cli, None

    class _FakeLLM:
        def __init__(self, content):
            self.content = content

    def fake_invoke(router, **kwargs):
        return _FakeLLM("hola")

    monkeypatch.setattr(agent_chat, "resolve_role_selection", fake_resolve)
    monkeypatch.setattr(agent_chat, "invoke_router", fake_invoke)
    monkeypatch.setattr("cli_app.context_tools.in_multiagent_project", lambda cwd=None: False)
    monkeypatch.setattr("cli_app.graph_rag.graph_available", lambda: False)
    monkeypatch.setattr("cli_app.context_tools.gather_file_context", lambda *a, **k: "")
    monkeypatch.setattr("cli_app.context_tools.gather_dir_context", lambda *a, **k: "")

    s = ConversationSession()
    r = agent_chat.agent_chat_turn("hola (wave21)", s)
    assert r["ok"] is True
    rec = r["data"]["model_selection"]
    assert rec is not None
    assert rec["role_path"] == ["cli", "chat"]
    assert rec["model"] == "gpt-oss-120b"


def test_difficulty_scorer_cli_chat_bias_fires():
    text = (
        "Explain the difference between two approaches in plain language "
        "for a beginner, keeping it concise and useful."
    )
    chat = score_task_difficulty(text, role_path="cli.chat")
    bare = score_task_difficulty(text, role_path="some/other")
    assert chat.reason == bare.reason + 5
    assert chat.role_path == "cli.chat"