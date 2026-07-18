"""Tests for live System A/B quota capacity estimates (no real HTTP)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.agent_config import reload_config
from core.model_selector import reload_benchmarks
from core.quota_estimate import (
    build_system_estimate,
    estimate_all,
    format_quota_report,
    pipeline_role_calls,
    resolve_role_endpoint,
)
from core.quotas import QuotaTracker


@pytest.fixture(autouse=True)
def _reload():
    reload_config()
    reload_benchmarks()
    yield
    reload_config()
    reload_benchmarks()


def _write_router(tmp_path: Path, doc: dict) -> Path:
    p = tmp_path / "model_router.yaml"
    p.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return p


def _minimal_router(
    *,
    architect_provider: str = "agnes",
    architect_model: str = "agnes-2.0-flash",
    coder_provider: str = "mistral",
    coder_model: str = "codestral-latest",
    coder_fb: dict | None = None,
) -> dict:
    return {
        "providers": {
            "agnes": {"daily_limit": 10},
            "mistral": {"daily_limit": 20},
            "gemini": {"daily_limit": 8},
            "groq": {"daily_limit_per_model": 6},
            "cohere": {"daily_limit": 5},
        },
        "vibe_coding": {
            "architect": {
                "provider": architect_provider,
                "model": architect_model,
                "fallback": {"provider": "gemini", "model": "gemini-2.0-flash"},
            },
            "coder": {
                "provider": coder_provider,
                "model": coder_model,
                "fallback": coder_fb
                or {"provider": "agnes", "model": "agnes-2.0-flash"},
            },
            "debugger": {
                "provider": "groq",
                "model": "openai/gpt-oss-120b",
                "fallback": {"provider": "agnes", "model": "agnes-2.0-flash"},
            },
            "max_fix_cycles": 3,
        },
        "deep_research": {
            "safety_filter": {
                "provider": "groq",
                "model": "openai/gpt-oss-safeguard-20b",
                "fallback": {"provider": "gemini", "model": "gemini-2.0-flash"},
            },
            "context_compressor": {
                "provider": "agnes",
                "model": "agnes-2.0-flash",
                "fallback": {"provider": "gemini", "model": "gemini-2.0-flash"},
            },
            "web_search": {
                "provider": "groq",
                "model": "groq/compound-mini",
            },
            "grounding": {
                "provider": "cohere",
                "model": "command-a-plus-05-2026",
                "fallback": {
                    "provider": "mistral",
                    "model": "mistral-small-latest",
                },
            },
            "synthesizer": {
                "provider": "groq",
                "model": "openai/gpt-oss-120b",
                "fallback": {"provider": "agnes", "model": "agnes-2.0-flash"},
            },
        },
    }


def test_pipeline_role_calls_typical_counts():
    a = pipeline_role_calls("vibe_coding", typical=True)
    assert sum(n for _, n in a) == 3
    b = pipeline_role_calls("deep_research", typical=True)
    assert sum(n for _, n in b) == 5


def test_resolve_primary_vs_fallback(tmp_path: Path):
    cfg = _write_router(tmp_path, _minimal_router())
    prim = resolve_role_endpoint(
        ("vibe_coding", "architect"), scenario="primary", config_path=cfg
    )
    fb = resolve_role_endpoint(
        ("vibe_coding", "architect"), scenario="fallback", config_path=cfg
    )
    assert prim["provider"] == "agnes"
    assert fb["provider"] == "gemini"
    assert fb["source"] == "fallback"


def test_exhausted_quota_zero_runs(tmp_path: Path, tmp_quota_db: Path):
    """(a) Exhausting a required provider bucket → 0 complete runs."""
    cfg = _write_router(tmp_path, _minimal_router())
    tracker = QuotaTracker(db_path=tmp_quota_db)

    # System A primary uses agnes(architect)+mistral(coder)+groq(debugger)
    # Drain agnes completely (limit 10)
    for _ in range(10):
        tracker.record_call("agnes", "agnes-2.0-flash")

    est = build_system_estimate(
        "vibe_coding",
        scenario="primary",
        tracker=tracker,
        config_path=cfg,
        reload=False,
    )
    assert est.runs_remaining == 0
    assert any(b.remaining == 0 for b in est.buckets if b.provider == "agnes")


def test_changing_primary_yaml_changes_demand(tmp_path: Path, tmp_quota_db: Path):
    """(b) Swapping primary model in YAML changes which bucket is charged."""
    tracker = QuotaTracker(db_path=tmp_quota_db)

    cfg_a = _write_router(
        tmp_path,
        _minimal_router(
            architect_provider="agnes",
            architect_model="agnes-2.0-flash",
        ),
    )
    est_a = build_system_estimate(
        "vibe_coding",
        scenario="primary",
        tracker=tracker,
        config_path=cfg_a,
        reload=False,
    )
    buckets_a = {b.bucket for b in est_a.buckets}
    assert "agnes/__shared__" in buckets_a

    # Point architect primary at gemini instead
    cfg_b = tmp_path / "model_router_b.yaml"
    doc = _minimal_router(
        architect_provider="gemini",
        architect_model="gemini-2.0-flash",
    )
    cfg_b.write_text(yaml.safe_dump(doc), encoding="utf-8")
    est_b = build_system_estimate(
        "vibe_coding",
        scenario="primary",
        tracker=tracker,
        config_path=cfg_b,
        reload=False,
    )
    buckets_b = {b.bucket for b in est_b.buckets}
    assert "gemini/__shared__" in buckets_b
    # Architect no longer bills agnes (coder fallback not used in primary scenario)
    # coder primary is mistral; debugger groq — agnes only if still used
    architect_roles = [r for r in est_b.roles if r.role.endswith("architect")]
    assert architect_roles[0].provider == "gemini"


def test_fallback_scenario_uses_fallback_models(tmp_path: Path, tmp_quota_db: Path):
    """(c) Planner fallback mode bills fallback endpoints for roles that have them."""
    cfg = _write_router(tmp_path, _minimal_router())
    tracker = QuotaTracker(db_path=tmp_quota_db)

    est_p = build_system_estimate(
        "vibe_coding",
        scenario="primary",
        tracker=tracker,
        config_path=cfg,
        reload=False,
    )
    est_f = build_system_estimate(
        "vibe_coding",
        scenario="fallback",
        tracker=tracker,
        config_path=cfg,
        reload=False,
    )

    by_role_p = {r.role: r for r in est_p.roles}
    by_role_f = {r.role: r for r in est_f.roles}

    assert by_role_p["vibe_coding.architect"].provider == "agnes"
    assert by_role_f["vibe_coding.architect"].provider == "gemini"
    assert by_role_f["vibe_coding.architect"].source == "fallback"

    assert by_role_p["vibe_coding.coder"].model == "codestral-latest"
    assert by_role_f["vibe_coding.coder"].model == "agnes-2.0-flash"

    # Different bottleneck possible once fallback piles onto gemini/agnes
    assert est_p.scenario == "primary"
    assert est_f.scenario == "fallback"


def test_fallback_scenario_tighter_when_shared_bucket_scarce(
    tmp_path: Path, tmp_quota_db: Path
):
    """Fallback scenario can reduce remaining runs vs primary when scarce bucket piles up."""
    # Tiny gemini limit; fallback scenario sends architect+… to gemini
    doc = _minimal_router()
    doc["providers"]["gemini"]["daily_limit"] = 2
    doc["providers"]["agnes"]["daily_limit"] = 100
    doc["providers"]["mistral"]["daily_limit"] = 100
    doc["providers"]["groq"]["daily_limit_per_model"] = 100
    cfg = _write_router(tmp_path, doc)
    tracker = QuotaTracker(db_path=tmp_quota_db)

    est_p = build_system_estimate(
        "vibe_coding",
        scenario="primary",
        tracker=tracker,
        config_path=cfg,
        reload=False,
    )
    est_f = build_system_estimate(
        "vibe_coding",
        scenario="fallback",
        tracker=tracker,
        config_path=cfg,
        reload=False,
    )
    # Primary does not need gemini for vibe (agnes/mistral/groq)
    assert est_p.runs_remaining >= 1
    # Fallback: architect→gemini (1) + maybe others stay off gemini;
    # at least architect burns 1 gemini/run → max 2 runs; if more roles hit gemini, fewer
    gemini_buckets = [b for b in est_f.buckets if b.provider == "gemini"]
    assert gemini_buckets
    assert est_f.runs_remaining <= est_p.runs_remaining


def test_format_report_contains_both_scenarios(tmp_quota_db: Path):
    tracker = QuotaTracker(db_path=tmp_quota_db)
    text = format_quota_report(tracker=tracker)
    assert "System A" in text
    assert "System B" in text
    assert "ALL PRIMARY" in text
    assert "PLANNER FALLBACK" in text
    assert "Complete runs remaining" in text


def test_estimate_all_structure(tmp_quota_db: Path):
    tracker = QuotaTracker(db_path=tmp_quota_db)
    rep = estimate_all(tracker=tracker)
    assert "vibe_coding" in rep["systems"]
    assert "primary" in rep["systems"]["vibe_coding"]
    assert "fallback" in rep["systems"]["deep_research"]
    assert rep["systems"]["deep_research"]["primary"].total_llm_calls == 5
