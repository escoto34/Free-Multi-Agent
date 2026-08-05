"""WAVE-20: score-driven model scoring (core/model_scoring.py) + the
difficulty_scorer aggregate wiring. All offline — synthetic bench fixtures.

Covered:
  split_model_key         provider-aware split (ambiguous keys)
  quality_for_role        mean over role relevant_areas
  efficiency_score        weighted speed/context/capacity
  fitness                 quality_weight*quality + efficiency_weight*efficiency
  rank_candidates         desc fitness, quality tiebreak, fit<=0 skipped
  difficulty aggregate    selection_defaults.quality_aggregate drives `overall`
                          (byte-identical vs the historical hardcoded formula)
"""

from __future__ import annotations

from typing import Any
from unittest import mock

from core import difficulty_scorer as ds
from core.difficulty_scorer import DifficultyAssessment, score_task_difficulty
from core import model_scoring as ms

# ---------------------------------------------------------------------------
# Synthetic schema-v2 bench used by the pure functions
# ---------------------------------------------------------------------------

_BENCH: dict[str, Any] = {
    "version": 2,
    "selection_defaults": {
        "quality_weight": 0.75,
        "efficiency_weight": 0.25,
        "quality_aggregate": {},
    },
    "roles": {
        "vibe_coding.coder": {"relevant_areas": ["code", "reason"]},
        "vibe_coding.note": {"relevant_areas": []},
    },
    "models": {
        "alpha/a-1": {
            "scores": {"code": 80, "reason": 60, "ground": 70},
            "efficiency": {
                "speed_score": 80,
                "context_score": 60,
                "capacity_score": 40,
            },
        },
        "alpha/a-2": {
            "scores": {"code": 70, "reason": 90},
        },
        "alpha/a-3": {},  # no scores at all -> fit 0, skipped
    },
}

# Two models with equal fitness but different quality -> quality is the tiebreak
# (fit = 0.5*q + 0.5*eff: tie-x 55, tie-y 55; quality 60 vs 80).
_TIE_BENCH: dict[str, Any] = {
    "selection_defaults": {"quality_weight": 0.5, "efficiency_weight": 0.5},
    "roles": {"vibe_coding.coder": {"relevant_areas": ["code", "reason"]}},
    "models": {
        "alpha/tie-x": {
            "scores": {"code": 80, "reason": 40},
            "efficiency": {"speed_score": 50, "context_score": 50, "capacity_score": 50},
        },
        "alpha/tie-y": {
            "scores": {"code": 90, "reason": 70},
            "efficiency": {"speed_score": 60, "context_score": 0, "capacity_score": 0},
        },
    },
}


# ---------------------------------------------------------------------------
# split_model_key
# ---------------------------------------------------------------------------


def test_split_model_key_ambiguous_known_providers():
    assert ms.split_model_key("groq/groq/compound-mini") == ("groq", "groq/compound-mini")
    assert ms.split_model_key("groq/openai/gpt-oss-120b") == ("groq", "openai/gpt-oss-120b")
    assert ms.split_model_key("openrouter/tencent/hy3:free") == ("openrouter", "tencent/hy3:free")
    assert ms.split_model_key("agnes/agnes-2.0-flash") == ("agnes", "agnes-2.0-flash")


def test_split_model_key_falls_back_to_naive_split():
    assert ms.split_model_key("fakeunknown/x/y") == ("fakeunknown", "x/y")


def test_split_model_key_requires_slash():
    with mock.patch.object(ms, "_providers", return_value=["known"]):
        try:
            ms.split_model_key("noprovider")  # type: ignore[arg-type]
        except ValueError as exc:
            assert "no provider slash" in str(exc)
        else:
            raise AssertionError("expected ValueError")


# ---------------------------------------------------------------------------
# quality_for_role / efficiency_score / fitness
# ---------------------------------------------------------------------------


def test_quality_for_role_mean_over_relevant_areas():
    q = ms.quality_for_role("alpha/a-1", "vibe_coding.coder", benchmarks=_BENCH)
    assert q == 70.0  # (80 + 60) / 2


def test_quality_for_role_defaults_to_reason_area():
    q = ms.quality_for_role("alpha/a-1", "vibe_coding.note", benchmarks=_BENCH)
    assert q == 60.0  # relevant_areas empty -> default ("reason",)


def test_quality_for_role_zero_when_no_scores():
    assert ms.quality_for_role("alpha/a-3", "vibe_coding.coder", benchmarks=_BENCH) == 0.0


def test_efficiency_score_weighted_components():
    eff = ms.efficiency_score("alpha/a-1", benchmarks=_BENCH)
    assert eff == 65.0  # 0.50*80 + 0.25*60 + 0.25*40


def test_efficiency_score_zero_when_missing():
    assert ms.efficiency_score("alpha/a-2", benchmarks=_BENCH) == 0.0


def test_fitness_blends_quality_and_efficiency():
    fit = ms.fitness("alpha/a-1", "vibe_coding.coder", benchmarks=_BENCH)
    assert fit == 68.75  # 0.75*70 + 0.25*65


def test_fitness_uses_default_weights_when_defaults_missing():
    bare = {"roles": {"vibe_coding.coder": {"relevant_areas": ["code"]}}, "models": {}}
    # No selection_defaults -> 0.75/0.25 fallbacks, no crash.
    assert ms.fitness("alpha/a-1", "vibe_coding.coder", benchmarks=bare) == 0.0


# ---------------------------------------------------------------------------
# rank_candidates
# ---------------------------------------------------------------------------


def test_rank_candidates_orders_by_fitness_desc_and_skips_zero():
    ranked = ms.rank_candidates(
        "vibe_coding.coder",
        ["alpha/a-3", "alpha/a-2", "alpha/a-1"],
        benchmarks=_BENCH,
    )
    # a-1 fit 68.75 > a-2 fit 60.0 (0.75*80 + 0) ; a-3 fit 0 -> skipped
    assert ranked == [("alpha/a-1", 68.75), ("alpha/a-2", 60.0)]


def test_rank_candidates_uses_quality_as_tiebreak():
    ranked = ms.rank_candidates(
        "vibe_coding.coder",
        ["alpha/tie-x", "alpha/tie-y"],
        benchmarks=_TIE_BENCH,
    )
    # tie-x: quality 60, eff 50 -> fit 55 ; tie-y: quality 80, eff 30 -> fit 55.
    # Equal fitness -> higher quality (tie-y) ranks first.
    assert [key for key, _fit in ranked] == ["alpha/tie-y", "alpha/tie-x"]
    assert ranked[0][1] == ranked[1][1] == 55.0


# ---------------------------------------------------------------------------
# Real-YAML contract guards (schema v2)
# ---------------------------------------------------------------------------


def test_real_benchmarks_is_schema_v2():
    real = ms._load_benchmarks()
    assert real.get("version") == 2
    sd = real.get("selection_defaults") or {}
    assert sd.get("quality_weight") == 0.75
    assert sd.get("efficiency_weight") == 0.25
    assert sd.get("quality_aggregate")  # explicit block present


def test_reload_benchmarks_clears_cache():
    ms._load_benchmarks()
    assert ms._bench_cache is not None
    ms.reload_benchmarks()
    assert ms._bench_cache is None


# ---------------------------------------------------------------------------
# difficulty_scorer aggregate wiring (byte-identical defaults, overridable)
# ---------------------------------------------------------------------------


def test_difficulty_overall_uses_default_aggregate_byte_identical():
    ds.reload_benchmarks()
    task = "Return a string reversed with extra blank lines."
    baseline = score_task_difficulty(task, role_path="vibe_coding.note")
    # The YAML quality_aggregate block holds the historical coefficients; the
    # `overall` from the YAML-driven path must match the legacy hardcoded formula.
    legacy = round(
        baseline.code * 0.30
        + baseline.reason * 0.25
        + baseline.ground * 0.15
        + baseline.synth * 0.15
        + baseline.safety * 0.05
        + max(baseline.logic_complexity, baseline.error_handling_complexity) * 0.10
    )
    assert baseline.overall == max(0, min(100, legacy))


def test_difficulty_overall_honors_yaml_aggregate_override(monkeypatch):
    monkeypatch.setattr(
        "core.difficulty_scorer._load_benchmarks",
        lambda: {
            "selection_defaults": {
                "quality_aggregate": {
                    "code_weight": 1.0,
                    "reason_weight": 0.0,
                    "ground_weight": 0.0,
                    "synth_weight": 0.0,
                    "safety_weight": 0.0,
                    "logic_error_weight": 0.0,
                }
            }
        },
    )
    ds.reload_benchmarks()
    task = _CODE_HEAVY_TASK
    assess = ds.score_task_difficulty(task, role_path="vibe_coding.coder")
    assert isinstance(assess, DifficultyAssessment)
    # code-only aggregate -> overall == code exactly
    assert assess.overall == assess.code


_CODE_HEAVY_TASK = (
    "Implement a red-black tree with iterative insertion. "
    "Handle rotations, rebalancing, and parent pointers. "
    "Add unit tests covering edge cases and memory guard rails."
)