"""WAVE-06 guard tests — provider catalog single source of truth.

Two currently-silent failure modes become loud CI failures here:

1. A provider/model with no row in ``config/model_benchmarks.yaml`` gets a
   silent flat 60 in ``core/model_selector.py`` (score-60 substitution),
   making difficulty-based selection a no-op for that model.
2. A registered provider with no entry in ``fallback_cascade:`` is a dead
   end: the router raises ``QuotaExhaustedError`` instead of trying another
   provider that may still have quota.

Backfill must land before these guards are meaningful — they read the live
``config/model_router.yaml`` catalog, so any model added to the catalog
without a benchmark row (or provider without a cascade entry) fails here.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from core.provider_registry import all_registered_models, get_registered_providers

_ROOT = Path(__file__).resolve().parent.parent
_ROUTER_PATH = _ROOT / "config" / "model_router.yaml"
_BENCHMARKS_PATH = _ROOT / "config" / "model_benchmarks.yaml"


def _load(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _benchmark_model_keys() -> set[str]:
    return set((_load(_BENCHMARKS_PATH).get("models") or {}).keys())


def _cascade_entries() -> dict:
    return _load(_ROUTER_PATH).get("fallback_cascade") or {}


def test_every_registered_model_has_benchmark_row():
    """Silent-flat-60 guard: every catalog model must be scored."""
    bench_keys = _benchmark_model_keys()
    missing = [
        f"{provider}/{model}"
        for provider, model in all_registered_models()
        if f"{provider}/{model}" not in bench_keys
    ]
    assert not missing, (
        "Models in config/model_router.yaml with no benchmark row in "
        f"config/model_benchmarks.yaml: {missing}"
    )


def test_every_benchmark_row_has_schema_v2_fields():
    """WAVE-20 guard: each scored row carries efficiency + evidence + verified.

    A row without these has no provenance and no measured stack position, so
    ``core/model_scoring.efficiency_score`` would silently read 0.
    """
    models = _load(_BENCHMARKS_PATH).get("models") or {}
    required = ("efficiency", "evidence", "verified", "available")
    bad = {
        key: [field for field in required if field not in row]
        for key, row in models.items()
        if not all(field in row for field in required)
    }
    assert not bad, f"benchmark rows missing schema-v2 fields: {bad}"


def test_measured_efficiency_rows_have_all_axis_scores():
    """WAVE-20 guard: rows claiming measured efficiency expose the full axis."""
    models = _load(_BENCHMARKS_PATH).get("models") or {}
    axes = ("speed_score", "context_score", "capacity_score")
    bad = {
        key: [a for a in axes if not isinstance(row["efficiency"].get(a), (int, float))]
        for key, row in models.items()
        if row.get("evidence") == "measured"
    }
    bad = {k: v for k, v in bad.items() if v}
    assert not bad, f"measured rows missing efficiency axes: {bad}"


def test_every_provider_has_cascade_entry():
    """Dead-end guard: every registered provider needs a fallback_cascade entry."""
    cascade = _cascade_entries()
    missing = [
        name for name in get_registered_providers() if f"{name}_fallback" not in cascade
    ]
    assert not missing, (
        "Providers in config/model_router.yaml: with no fallback_cascade "
        f"entry: {missing}"
    )


def test_cascade_targets_are_registered_providers():
    """Cascade must not point at providers absent from the catalog."""
    providers = set(get_registered_providers())
    bad: list[str] = []
    for key, target in _cascade_entries().items():
        if not isinstance(target, dict):
            bad.append(f"{key}: not a mapping")
            continue
        if target.get("provider") not in providers:
            bad.append(f"{key} -> {target!r}")
    assert not bad, f"fallback_cascade targets unknown providers: {bad}"


def test_cascade_targets_have_benchmark_rows():
    """Cascade targets are routable — they must be scored too."""
    bench_keys = _benchmark_model_keys()
    missing = [
        f"{t['provider']}/{t['model']}"
        for t in _cascade_entries().values()
        if isinstance(t, dict)
        and t.get("provider")
        and t.get("model")
        and f"{t['provider']}/{t['model']}" not in bench_keys
    ]
    assert not missing, f"Cascade targets with no benchmark row: {missing}"


def test_opencode_zen_client_resolves():
    """WAVE-08 smoke: get_client('opencode_zen') must resolve without error.

    opencode_zen is added through the YAML catalog alone — no Python change.
    The conftest fake-key loop derives OPENCODE_ZEN_API_KEY from the registry,
    so constructing the OpenAI client must not raise ValueError.
    """
    from openai import OpenAI

    from core.clients import get_client, clear_client_cache
    from core.provider_registry import get_provider_meta

    meta = get_provider_meta("opencode_zen")
    assert meta["kind"] == "openai_compatible"
    assert meta["base_url"] == "https://opencode.ai/zen/v1"
    assert meta["env_key"] == "OPENCODE_ZEN_API_KEY"
    assert len(meta["models"]) == 7

    client = get_client("opencode_zen")
    assert isinstance(client, OpenAI)
    clear_client_cache()
