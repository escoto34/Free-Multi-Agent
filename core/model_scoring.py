"""WAVE-20 — score-driven model scoring: quality + efficiency → fitness.

Pure, side-effect-free functions that read ``config/model_benchmarks.yaml``
(schema v2). Nothing in this module makes HTTP calls or mutates state; it is
the shared vocabulary WAVE-21's ``select_for_role`` will route on.

Contracts (mejoras.md WAVE-20)::

    split_model_key(key) -> (provider, model)     # provider-aware, no naive /
    quality_for_role(model_key, role_path) -> float   # mean over relevant_areas
    efficiency_score(model_key) -> float              # weighted speed/context/capacity
    fitness(model_key, role_path) -> float            # weighted quality+efficiency
    rank_candidates(role_path, candidates) -> list[tuple[str, float]]
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional

import yaml

from core.provider_registry import get_registered_providers

_BENCHMARKS_PATH = Path(__file__).parent.parent / "config" / "model_benchmarks.yaml"
_DEFAULT_AREAS = ("reason",)

# Efficiency component weights (stack-relative rubric, systems.md §4.1).
_EFFICIENCY_WEIGHTS: dict[str, float] = {
    "speed": 0.50,
    "context": 0.25,
    "capacity": 0.25,
}

_bench_cache: Optional[dict[str, Any]] = None
_providers_cache: Optional[list[str]] = None


def _load_benchmarks() -> dict[str, Any]:
    global _bench_cache
    if _bench_cache is None:
        with open(_BENCHMARKS_PATH, encoding="utf-8") as fh:
            _bench_cache = yaml.safe_load(fh) or {}
    return _bench_cache


def reload_benchmarks() -> None:
    """Clear benchmarks + provider-prefix caches (tests / live YAML edit)."""
    global _bench_cache, _providers_cache
    _bench_cache = None
    _providers_cache = None


def _providers() -> list[str]:
    global _providers_cache
    if _providers_cache is None:
        _providers_cache = sorted(get_registered_providers(), key=len, reverse=True)
    return _providers_cache


def split_model_key(key: str) -> tuple[str, str]:
    """Split a catalog key into ``(provider, model)`` against registered providers.

    Falls back to a naive first-``/`` split only when no registered provider
    prefix matches, so ambiguous keys like ``groq/groq/compound-mini`` and
    ``groq/openai/gpt-oss-120b`` resolve correctly.
    """
    for provider in _providers():
        prefix = provider + "/"
        if key.startswith(prefix):
            return provider, key[len(prefix) :]
    parts = key.split("/", 1)
    if len(parts) < 2:
        raise ValueError(f"model key {key!r} has no provider slash")
    return parts[0], parts[1]


def _role_areas(role_path: str, bench: Mapping[str, Any]) -> list[str]:
    roles = bench.get("roles") or {}
    specific = roles.get(role_path) or {}
    return list(specific.get("relevant_areas") or _DEFAULT_AREAS)


def quality_for_role(
    model_key: str,
    role_path: str,
    *,
    benchmarks: Optional[Mapping[str, Any]] = None,
) -> float:
    """Mean of the model's area scores over the role's ``relevant_areas``."""
    bench = benchmarks if benchmarks is not None else _load_benchmarks()
    provider, model = split_model_key(model_key)
    row = (bench.get("models") or {}).get(model_key) or {}
    scores = row.get("scores") or {}
    if not scores:
        return 0.0
    areas = _role_areas(role_path, bench)
    values = [float(scores.get(a, 60)) for a in areas]
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def efficiency_score(
    model_key: str,
    *,
    benchmarks: Optional[Mapping[str, Any]] = None,
) -> float:
    """Weighted speed/context/capacity score (0-100) from the model row."""
    bench = benchmarks if benchmarks is not None else _load_benchmarks()
    eff = ((bench.get("models") or {}).get(model_key) or {}).get("efficiency") or {}
    speed = float(eff.get("speed_score") or 0.0)
    context = float(eff.get("context_score") or 0.0)
    capacity = float(eff.get("capacity_score") or 0.0)
    raw = (
        _EFFICIENCY_WEIGHTS["speed"] * speed
        + _EFFICIENCY_WEIGHTS["context"] * context
        + _EFFICIENCY_WEIGHTS["capacity"] * capacity
    )
    return round(raw, 2)


def fitness(
    model_key: str,
    role_path: str,
    *,
    benchmarks: Optional[Mapping[str, Any]] = None,
) -> float:
    """quality_weight * quality_for_role + efficiency_weight * efficiency_score."""
    bench = benchmarks if benchmarks is not None else _load_benchmarks()
    defaults = bench.get("selection_defaults") or {}
    qw = float(defaults.get("quality_weight", 0.75))
    ew = float(defaults.get("efficiency_weight", 0.25))
    raw = qw * quality_for_role(model_key, role_path, benchmarks=bench) + ew * efficiency_score(
        model_key, benchmarks=bench
    )
    return round(raw, 2)


def rank_candidates(
    role_path: str,
    candidates: list[str],
    *,
    benchmarks: Optional[Mapping[str, Any]] = None,
) -> list[tuple[str, float]]:
    """Rank candidate model keys by descending ``fitness``, quality as tiebreak."""
    bench = benchmarks if benchmarks is not None else _load_benchmarks()
    scored: list[tuple[str, float, float]] = []
    for key in candidates:
        quality = quality_for_role(key, role_path, benchmarks=bench)
        fit = fitness(key, role_path, benchmarks=bench)
        if fit <= 0:
            continue
        scored.append((key, fit, quality))
    scored.sort(key=lambda item: (item[1], item[2]), reverse=True)
    return [(key, fit) for key, fit, _quality in scored]