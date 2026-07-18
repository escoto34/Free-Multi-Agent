"""
Difficulty-aware reasoning / thinking kwargs for models that support them.

Free-tier provider limits in this stack are almost always **per call (RPD)**,
not per token. Raising ``reasoning_effort`` on a supported model therefore
improves quality **without** burning an extra daily call — only latency and
output tokens increase inside the same request.

Policy source: ``config/model_benchmarks.yaml`` → ``reasoning:`` (systems.md §4.5).

Supported styles (mid-2026):

* ``groq_gpt_oss`` — Groq GPT-OSS family:
  ``reasoning_effort`` ∈ {low, medium, high}, ``include_reasoning`` bool
* ``groq_qwen`` — Groq Qwen 3.6:
  ``reasoning_effort`` ∈ {none, default}, optional ``reasoning_format``

Models without a capability entry receive **no** reasoning kwargs (safe when
the router cascades to Agnes / Codestral / Gemini / Cohere).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import yaml

from core.difficulty_scorer import DifficultyAssessment
from core.model_selector import model_key, reload_benchmarks

logger = logging.getLogger(__name__)

_BENCHMARKS_PATH = Path(__file__).parent.parent / "config" / "model_benchmarks.yaml"

# Keys we may inject or must strip when cascading to unsupported models.
REASONING_KWARG_KEYS: frozenset[str] = frozenset(
    {
        "reasoning_effort",
        "include_reasoning",
        "reasoning_format",
        "reasoning",  # OpenRouter-style map — reserved / stripped if unsupported
    }
)

_EFFORT_RANK_DEFAULT = ("low", "medium", "high")

_bench_cache: Optional[dict[str, Any]] = None


def _load_benchmarks(path: Optional[Path] = None) -> dict[str, Any]:
    global _bench_cache
    if path is not None:
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    if _bench_cache is None:
        with open(_BENCHMARKS_PATH, encoding="utf-8") as fh:
            _bench_cache = yaml.safe_load(fh) or {}
    return _bench_cache


def reload_reasoning_config() -> None:
    """Clear local + model_selector benchmarks caches after YAML edits."""
    global _bench_cache
    _bench_cache = None
    reload_benchmarks()


def _reasoning_cfg(bench: Mapping[str, Any]) -> dict[str, Any]:
    return dict(bench.get("reasoning") or {})


def _effort_rank(cfg: Mapping[str, Any]) -> list[str]:
    raw = cfg.get("effort_rank") or list(_EFFORT_RANK_DEFAULT)
    return [str(x) for x in raw]


def _rank_index(effort: str, rank: Sequence[str]) -> int:
    try:
        return list(rank).index(effort)
    except ValueError:
        return 0


def _clamp_effort(
    effort: str,
    *,
    rank: Sequence[str],
    min_effort: Optional[str] = None,
    max_effort: Optional[str] = None,
) -> str:
    if effort not in rank:
        effort = rank[0] if rank else "low"
    lo = _rank_index(min_effort, rank) if min_effort in rank else 0
    hi = _rank_index(max_effort, rank) if max_effort in rank else len(rank) - 1
    idx = max(lo, min(hi, _rank_index(effort, rank)))
    return rank[idx]


def difficulty_to_effort(
    assessment: DifficultyAssessment,
    *,
    role_path: str = "",
    benchmarks: Optional[Mapping[str, Any]] = None,
) -> str:
    """Map assessment → abstract effort band (low|medium|high)."""
    bench = benchmarks if benchmarks is not None else _load_benchmarks()
    cfg = _reasoning_cfg(bench)
    rank = _effort_rank(cfg)

    # Prefer max over role-relevant areas when known
    roles = (bench.get("roles") or {}).get(role_path) or {}
    areas = list(roles.get("relevant_areas") or [])
    score = assessment.relevant_max(areas) if areas else int(assessment.overall or 0)
    if not score:
        score = int(assessment.overall or 0)

    bands = list(cfg.get("difficulty_bands") or [])
    effort = rank[0] if rank else "low"
    for band in bands:
        try:
            max_ex = int(band.get("max_exclusive", 101))
        except (TypeError, ValueError):
            max_ex = 101
        if score < max_ex:
            effort = str(band.get("effort") or effort)
            break

    role_rules = dict((cfg.get("role_effort") or {}).get(role_path) or {})
    effort = _clamp_effort(
        effort,
        rank=rank,
        min_effort=role_rules.get("min_effort"),
        max_effort=role_rules.get("max_effort"),
    )
    return effort


def get_model_reasoning_capability(
    provider: str,
    model: str,
    *,
    benchmarks: Optional[Mapping[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    bench = benchmarks if benchmarks is not None else _load_benchmarks()
    caps = (_reasoning_cfg(bench).get("model_capabilities") or {})
    entry = caps.get(model_key(provider, model))
    return dict(entry) if isinstance(entry, dict) else None


def _map_effort_for_style(style: str, effort: str) -> str:
    """Translate abstract low|medium|high into provider-native effort values."""
    if style == "groq_qwen":
        # Qwen only accepts none | default
        return "none" if effort == "low" else "default"
    # groq_gpt_oss and unknowns that use low/medium/high
    if effort in ("low", "medium", "high"):
        return effort
    return "medium"


@dataclass
class ReasoningPlan:
    """Resolved reasoning plan for one LLM call."""

    effort: str
    provider: str
    model: str
    style: Optional[str] = None
    kwargs: dict[str, Any] = field(default_factory=dict)
    applied: bool = False
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "effort": self.effort,
            "provider": self.provider,
            "model": self.model,
            "style": self.style,
            "kwargs": dict(self.kwargs),
            "applied": self.applied,
            "reason": self.reason,
        }


def resolve_reasoning_plan(
    provider: str,
    model: str,
    *,
    assessment: Optional[DifficultyAssessment] = None,
    role_path: str = "",
    include_reasoning: Optional[bool] = None,
    force_effort: Optional[str] = None,
    benchmarks_path: Optional[Path] = None,
) -> ReasoningPlan:
    """Build provider-native kwargs for this model + difficulty."""
    bench = _load_benchmarks(benchmarks_path) if benchmarks_path else _load_benchmarks()
    cfg = _reasoning_cfg(bench)
    rank = _effort_rank(cfg)

    if not cfg.get("enabled", True):
        return ReasoningPlan(
            effort="low",
            provider=provider,
            model=model,
            reason="reasoning disabled in model_benchmarks.yaml",
        )

    if assessment is None:
        effort = force_effort or "medium"
    else:
        effort = force_effort or difficulty_to_effort(
            assessment, role_path=role_path, benchmarks=bench
        )
    effort = _clamp_effort(effort, rank=rank)

    cap = get_model_reasoning_capability(provider, model, benchmarks=bench)
    if not cap:
        return ReasoningPlan(
            effort=effort,
            provider=provider,
            model=model,
            reason=f"no reasoning capability for {provider}/{model}",
        )

    style = str(cap.get("style") or "")
    native = _map_effort_for_style(style, effort)
    inc = (
        include_reasoning
        if include_reasoning is not None
        else bool(cfg.get("default_include_reasoning", False))
    )

    kwargs: dict[str, Any] = {}
    if style == "groq_gpt_oss":
        kwargs["reasoning_effort"] = native
        kwargs["include_reasoning"] = inc
    elif style == "groq_qwen":
        kwargs["reasoning_effort"] = native
        # Prefer hidden CoT in content for structured pipelines
        if not inc:
            kwargs["reasoning_format"] = "hidden"
        else:
            kwargs["reasoning_format"] = "parsed"
    else:
        return ReasoningPlan(
            effort=effort,
            provider=provider,
            model=model,
            style=style or None,
            reason=f"unknown reasoning style {style!r}",
        )

    return ReasoningPlan(
        effort=effort,
        provider=provider,
        model=model,
        style=style,
        kwargs=kwargs,
        applied=True,
        reason=f"style={style} effort={effort}→{native} role={role_path or '-'}",
    )


def resolve_reasoning_kwargs(
    provider: str,
    model: str,
    *,
    assessment: Optional[DifficultyAssessment] = None,
    role_path: str = "",
    include_reasoning: Optional[bool] = None,
    force_effort: Optional[str] = None,
) -> dict[str, Any]:
    """Convenience: only the kwargs to merge into ``chat.completions.create``."""
    plan = resolve_reasoning_plan(
        provider,
        model,
        assessment=assessment,
        role_path=role_path,
        include_reasoning=include_reasoning,
        force_effort=force_effort,
    )
    if plan.applied:
        logger.debug(
            "Reasoning %s/%s → %s (%s)",
            provider,
            model,
            plan.kwargs,
            plan.reason,
        )
    return dict(plan.kwargs)


def strip_reasoning_kwargs(kwargs: Mapping[str, Any]) -> dict[str, Any]:
    """Remove all reasoning-related keys (cascade to unsupported models)."""
    return {k: v for k, v in kwargs.items() if k not in REASONING_KWARG_KEYS}


def sanitize_call_kwargs(
    provider: str,
    model: str,
    kwargs: Mapping[str, Any],
    *,
    assessment: Optional[DifficultyAssessment] = None,
    role_path: str = "",
    reapply: bool = True,
) -> dict[str, Any]:
    """Strip unsupported reasoning keys; optionally re-apply for *this* model.

    Always call this in the router before ``_dispatch`` so cascade hops do not
    send ``reasoning_effort`` to Agnes/Codestral/etc.
    """
    base = strip_reasoning_kwargs(kwargs)
    # Preserve explicit caller overrides if they only set effort on a capable model
    explicit_effort = kwargs.get("reasoning_effort")
    explicit_include = kwargs.get("include_reasoning")
    if not reapply:
        return base

    force = None
    if isinstance(explicit_effort, str) and explicit_effort in (
        "low",
        "medium",
        "high",
        "none",
        "default",
    ):
        # Map native back to abstract if needed
        if explicit_effort in ("none",):
            force = "low"
        elif explicit_effort in ("default",):
            force = "medium"
        elif explicit_effort in ("low", "medium", "high"):
            force = explicit_effort

    plan = resolve_reasoning_plan(
        provider,
        model,
        assessment=assessment,
        role_path=role_path,
        include_reasoning=(
            bool(explicit_include) if explicit_include is not None else None
        ),
        force_effort=force,
    )
    if plan.applied:
        # Caller non-reasoning kwargs win over plan for non-reasoning keys only
        return {**base, **plan.kwargs}
    return base
