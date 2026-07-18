"""
Primary vs fallback model selection from difficulty scores + benchmarks YAML.

Consumes:

* ``config/model_benchmarks.yaml`` — scores (systems.md §4.2), thresholds (§4.3),
  hy3 ``free_until``
* ``config/model_router.yaml`` — live primary/fallback per role
* :class:`~core.difficulty_scorer.DifficultyAssessment`

Policy (systems.md §4.3) — prefer fallback when:

1. Primary is **unavailable/degraded** (expired promo, quota, 429, empty
   completion) and a role (or catalog) fallback exists; **or**
2. Primary is **mis-specialized** for a relevant area:
   ``score_fallback(area) − score_primary(area) ≥ score_advantage_threshold``
   (default **8**, editable in YAML) **and** (primary score is weak **or**
   task difficulty on that area exceeds primary capacity).

Healthy primary + easy/adequate task → **stay on primary** even if the
fallback edges higher by a few points on one area.

When the decision leaves the configured primary, callers **must** record the
transition with :func:`record_model_selection_handoff` (uses
``core.handoff.transfer_control``).
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Optional, Sequence

import yaml

from core.agent_config import get_agent_config
from core.difficulty_scorer import DifficultyAssessment
from core.handoff import transfer_control
from schemas.handoff import PipelineName

logger = logging.getLogger(__name__)

_BENCHMARKS_PATH = Path(__file__).parent.parent / "config" / "model_benchmarks.yaml"
_HY3_MODEL_ID = "tencent/hy3:free"
_HY3_DEFAULT_UNTIL = "2026-07-21"

# Caller / runtime signals that primary is unhealthy (systems.md §4.3).
DEGRADED_STATUSES = frozenset(
    {
        "quota_exhausted",
        "rate_limited_429",
        "empty_completion",
        "unavailable",
        "degraded",
    }
)

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


def reload_benchmarks() -> None:
    """Clear benchmarks cache (tests / live YAML edit)."""
    global _bench_cache
    _bench_cache = None


def model_key(provider: str, model: str) -> str:
    return f"{provider}/{model}"


def get_model_entry(
    provider: str,
    model: str,
    *,
    benchmarks: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    bench = benchmarks if benchmarks is not None else _load_benchmarks()
    models = bench.get("models") or {}
    return dict(models.get(model_key(provider, model)) or {})


def get_model_scores(
    provider: str,
    model: str,
    *,
    benchmarks: Optional[Mapping[str, Any]] = None,
    today: Optional[date] = None,
    role_cfg: Optional[Mapping[str, Any]] = None,
) -> dict[str, int]:
    """Return area scores; expired promos are capped at ``expired_score_cap`` (≤49)."""
    bench = benchmarks if benchmarks is not None else _load_benchmarks()
    entry = get_model_entry(provider, model, benchmarks=bench)
    raw = entry.get("scores") or {}
    scores = {k: int(v) for k, v in raw.items()}
    if not scores:
        return scores
    if not is_model_available(
        provider, model, today=today, role_cfg=role_cfg, benchmarks=bench
    ):
        defaults = bench.get("selection_defaults") or {}
        cap = int(defaults.get("expired_score_cap", 49))
        scores = {k: min(v, cap) for k, v in scores.items()}
    return scores


def parse_free_until(raw: Any) -> Optional[date]:
    if raw is None or raw == "":
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    text = str(raw).strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def model_free_until(
    provider: str,
    model: str,
    *,
    role_cfg: Optional[Mapping[str, Any]] = None,
    benchmarks: Optional[Mapping[str, Any]] = None,
) -> Optional[date]:
    """Resolve free_until from role YAML, then benchmarks catalog."""
    if role_cfg and role_cfg.get("free_until"):
        d = parse_free_until(role_cfg.get("free_until"))
        if d:
            return d
    entry = get_model_entry(provider, model, benchmarks=benchmarks)
    if entry.get("free_until"):
        return parse_free_until(entry.get("free_until"))
    # Built-in knowledge of hy3 promo even if YAML drifts
    if model == _HY3_MODEL_ID or model.endswith("/" + _HY3_MODEL_ID):
        return parse_free_until(_HY3_DEFAULT_UNTIL)
    return None


def is_model_available(
    provider: str,
    model: str,
    *,
    today: Optional[date] = None,
    role_cfg: Optional[Mapping[str, Any]] = None,
    benchmarks: Optional[Mapping[str, Any]] = None,
) -> bool:
    """False when free_until is strictly before *today* (promo expired)."""
    until = model_free_until(
        provider, model, role_cfg=role_cfg, benchmarks=benchmarks
    )
    if until is None:
        return True
    day = today or date.today()
    return day <= until


def hy3_status(*, today: Optional[date] = None) -> dict[str, Any]:
    """Status dict for CLI / diagnostics (days remaining, expired, fallback)."""
    day = today or date.today()
    until = model_free_until("openrouter", _HY3_MODEL_ID) or parse_free_until(
        _HY3_DEFAULT_UNTIL
    )
    assert until is not None
    delta = (until - day).days
    entry = get_model_entry("openrouter", _HY3_MODEL_ID)
    fb = entry.get("expired_fallback") or {
        "provider": "groq",
        "model": "openai/gpt-oss-120b",
    }
    return {
        "model": _HY3_MODEL_ID,
        "provider": "openrouter",
        "free_until": until.isoformat(),
        "days_remaining": delta,
        "expired": delta < 0,
        "warn": 0 <= delta <= int(
            (_load_benchmarks().get("selection_defaults") or {}).get("warn_hy3_days", 3)
        ),
        "expired_fallback": dict(fb),
    }


@dataclass
class ModelSelection:
    """Result of primary vs fallback decision for one role invocation."""

    provider: str
    model: str
    used_fallback: bool
    reason: str
    role_path: tuple[str, ...]
    primary_provider: str
    primary_model: str
    fallback_provider: Optional[str] = None
    fallback_model: Optional[str] = None
    forced_expiry: bool = False
    assessment_overall: int = 0
    chain_fallback: Optional[dict[str, str]] = None
    primary_status: str = "ok"
    extras: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["role_path"] = list(self.role_path)
        return d


def _role_dotted(role_path: Sequence[str]) -> str:
    return ".".join(role_path)


def _role_rules(dotted: str, bench: Mapping[str, Any]) -> dict[str, Any]:
    defaults = dict(bench.get("selection_defaults") or {})
    roles = bench.get("roles") or {}
    specific = dict(roles.get(dotted) or {})
    # role overrides win for known keys; relevant_areas only from role if set
    merged = {**defaults, **specific}
    if "relevant_areas" not in merged:
        merged["relevant_areas"] = ["reason"]
    return merged


def _expired_fallback_for(
    provider: str,
    model: str,
    *,
    benchmarks: Mapping[str, Any],
) -> Optional[dict[str, str]]:
    entry = get_model_entry(provider, model, benchmarks=benchmarks)
    fb = entry.get("expired_fallback")
    if isinstance(fb, dict) and fb.get("provider") and fb.get("model"):
        return {"provider": str(fb["provider"]), "model": str(fb["model"])}
    if model == _HY3_MODEL_ID:
        return {"provider": "groq", "model": "openai/gpt-oss-120b"}
    return None


def _is_primary_degraded(status: str) -> bool:
    return (status or "ok").strip().lower() in DEGRADED_STATUSES


def _mis_specialization_reasons(
    *,
    p_scores: Mapping[str, int],
    f_scores: Mapping[str, int],
    assessment: DifficultyAssessment,
    areas: Sequence[str],
    advantage_th: int,
    weak_max: int,
    hard_th: int,
) -> list[str]:
    """systems.md mis-specialized path (e.g. Safeguard on coding).

    Prefer fallback only when, on a relevant area:
    ``score_fallback − score_primary ≥ advantage_th`` **and**
    primary score is in the weak band (≤ ``weak_max``, default 49).

    A healthy specialist (Codestral code 88) must **not** lose the role just
    because the fallback edges higher on a secondary area (e.g. reason).
    Hard-task routing without degradation stays on primary; ops degradation
    is handled separately via ``primary_status``.
    """
    del assessment, hard_th  # reserved for future planner hooks / diagnostics
    why: list[str] = []
    for area in areas:
        sp = int(p_scores.get(area, 60))
        sf = int(f_scores.get(area, 60))
        delta = sf - sp
        if delta < advantage_th:
            continue
        if sp <= weak_max:
            why.append(
                f"{area}: mis-specialized primary={sp}<={weak_max}, "
                f"fallback={sf} (Δ{delta}>={advantage_th})"
            )
    return why


def select_for_role(
    *role_path: str,
    assessment: DifficultyAssessment,
    today: Optional[date] = None,
    config_path: Optional[Path] = None,
    benchmarks_path: Optional[Path] = None,
    force_primary: bool = False,
    primary_status: str = "ok",
) -> ModelSelection:
    """Choose primary or fallback for ``role_path`` given a difficulty assessment.

    Pure decision function — no HTTP. Hy3 (and any model with ``free_until``)
    past expiry is treated as unavailable and replaced automatically.

    Parameters
    ----------
    primary_status:
        ``\"ok\"`` (default) or a degraded signal from
        :data:`DEGRADED_STATUSES` (``quota_exhausted``, ``rate_limited_429``,
        ``empty_completion``, ``unavailable``, ``degraded``).
    """
    if len(role_path) < 1:
        raise ValueError("role_path required")

    bench = _load_benchmarks(benchmarks_path) if benchmarks_path else _load_benchmarks()
    role_cfg = get_agent_config(*role_path, config_path=config_path)
    primary_p = str(role_cfg["provider"])
    primary_m = str(role_cfg["model"])
    fb_cfg = role_cfg.get("fallback")
    fb_p = str(fb_cfg["provider"]) if isinstance(fb_cfg, dict) and fb_cfg.get("provider") else None
    fb_m = str(fb_cfg["model"]) if isinstance(fb_cfg, dict) and fb_cfg.get("model") else None

    day = today or date.today()
    dotted = _role_dotted(role_path)
    rules = _role_rules(dotted, bench)
    areas: list[str] = list(rules.get("relevant_areas") or ["reason"])
    hard_th = int(rules.get("hard_threshold", 70))
    margin = int(rules.get("capacity_margin", 5))
    advantage_th = int(rules.get("score_advantage_threshold", 8))
    weak_max = int(rules.get("weak_specialization_max", 49))
    status = (primary_status or "ok").strip().lower()

    def _sel(
        provider: str,
        model: str,
        *,
        used_fallback: bool,
        reason: str,
        forced_expiry: bool = False,
        chain_fallback: Optional[dict[str, str]] = None,
    ) -> ModelSelection:
        return ModelSelection(
            provider=provider,
            model=model,
            used_fallback=used_fallback,
            reason=reason,
            role_path=tuple(role_path),
            primary_provider=primary_p,
            primary_model=primary_m,
            fallback_provider=fb_p,
            fallback_model=fb_m,
            forced_expiry=forced_expiry,
            assessment_overall=assessment.overall,
            chain_fallback=chain_fallback,
            primary_status=status,
            extras={
                "relevant_areas": areas,
                "hard_threshold": hard_th,
                "capacity_margin": margin,
                "score_advantage_threshold": advantage_th,
                "weak_specialization_max": weak_max,
            },
        )

    # --- Primary expired (e.g. hy3 after 2026-07-21) ---
    primary_ok = is_model_available(
        primary_p, primary_m, today=day, role_cfg=role_cfg, benchmarks=bench
    )
    if not primary_ok:
        exp_fb = _expired_fallback_for(primary_p, primary_m, benchmarks=bench)
        if fb_p and fb_m and is_model_available(fb_p, fb_m, today=day, benchmarks=bench):
            return _sel(
                fb_p,
                fb_m,
                used_fallback=True,
                forced_expiry=True,
                reason=(
                    f"Primary {primary_p}/{primary_m} expired or unavailable; "
                    f"using role fallback {fb_p}/{fb_m}"
                ),
                chain_fallback=None,
            )
        if exp_fb and is_model_available(
            exp_fb["provider"], exp_fb["model"], today=day, benchmarks=bench
        ):
            return _sel(
                exp_fb["provider"],
                exp_fb["model"],
                used_fallback=True,
                forced_expiry=True,
                reason=(
                    f"Primary {primary_p}/{primary_m} expired; "
                    f"using catalog expired_fallback "
                    f"{exp_fb['provider']}/{exp_fb['model']}"
                ),
            )
        return _sel(
            primary_p,
            primary_m,
            used_fallback=False,
            forced_expiry=True,
            reason=f"Primary expired but no usable fallback for {dotted}",
        )

    if force_primary or not fb_p or not fb_m:
        return _sel(
            primary_p,
            primary_m,
            used_fallback=False,
            reason="Stay on primary (no fallback configured or force_primary)",
            chain_fallback=dict(fb_cfg) if isinstance(fb_cfg, dict) else None,
        )

    # Fallback also expired?
    fb_ok = is_model_available(fb_p, fb_m, today=day, benchmarks=bench)
    if not fb_ok:
        return _sel(
            primary_p,
            primary_m,
            used_fallback=False,
            reason=f"Fallback {fb_p}/{fb_m} unavailable; keep primary",
            chain_fallback=None,
        )

    # --- (1) Primary degraded / unhealthy (quota, 429, empty) ---
    if _is_primary_degraded(status):
        return _sel(
            fb_p,
            fb_m,
            used_fallback=True,
            reason=(
                f"Primary degraded ({status}); using role fallback {fb_p}/{fb_m} "
                f"(systems.md §4.3 operational switch)"
            ),
            chain_fallback=None,
        )

    # --- (2) Mis-specialization: score_fb − score_p ≥ threshold + weak/hard ---
    p_scores = get_model_scores(
        primary_p, primary_m, benchmarks=bench, today=day, role_cfg=role_cfg
    )
    f_scores = get_model_scores(fb_p, fb_m, benchmarks=bench, today=day)
    if not p_scores:
        p_scores = {a: 60 for a in ("code", "reason", "ground", "synth", "safety")}
    if not f_scores:
        f_scores = {a: 60 for a in ("code", "reason", "ground", "synth", "safety")}

    mis_why = _mis_specialization_reasons(
        p_scores=p_scores,
        f_scores=f_scores,
        assessment=assessment,
        areas=areas,
        advantage_th=advantage_th,
        weak_max=weak_max,
        hard_th=hard_th,
    )
    if mis_why:
        return _sel(
            fb_p,
            fb_m,
            used_fallback=True,
            reason="Mis-specialized primary prefers fallback: " + "; ".join(mis_why),
            chain_fallback=None,
        )

    # Healthy primary, adequate specialization → keep primary
    # (even if fallback is slightly better on one area by < advantage_th)
    return _sel(
        primary_p,
        primary_m,
        used_fallback=False,
        reason=(
            f"Primary healthy and specialized enough for {dotted} "
            f"(overall={assessment.overall}, status={status}, "
            f"areas={areas}, advantage_th={advantage_th})"
        ),
        chain_fallback={"provider": fb_p, "model": fb_m},
    )


def record_model_selection_handoff(
    state: Mapping[str, Any],
    selection: ModelSelection,
    *,
    role: str,
    user_input_key: str,
    pipeline: PipelineName,
    updates: Optional[MutableMapping[str, Any]] = None,
) -> dict[str, Any]:
    """Record primary→fallback (or expiry) model switch via ``transfer_control``.

    Always call this when ``selection.used_fallback`` or ``forced_expiry`` is
    true before invoking the worker LLM. Safe to call for primary-stay too
    (audits which model was chosen).
    """
    from_agent = f"{role}@primary({selection.primary_provider}/{selection.primary_model})"
    to_agent = f"{role}@{selection.provider}/{selection.model}"
    patch_updates: dict[str, Any] = dict(updates or {})
    patch_updates["last_model_selection"] = selection.as_dict()

    note = json.dumps(
        {
            "used_fallback": selection.used_fallback,
            "forced_expiry": selection.forced_expiry,
            "primary_status": selection.primary_status,
            "overall": selection.assessment_overall,
            "reason": selection.reason,
        },
        ensure_ascii=False,
    )
    return transfer_control(
        state,
        from_agent=from_agent,
        to_agent=to_agent,
        reason=selection.reason,
        pipeline=pipeline,
        user_input_key=user_input_key,
        updates=patch_updates,
        note=note,
    )
