"""
Primary vs fallback model selection from difficulty scores + benchmarks YAML.

Consumes:

* ``config/model_benchmarks.yaml`` — scores (systems.md §4.2), thresholds (§4.3),
  model ``free_until`` dates
* ``config/model_router.yaml`` — live primary/fallback per role
* :class:`~core.difficulty_scorer.DifficultyAssessment`

Policy (systems.md §4.3) — WAVE-21 score-driven selection:

1. Build the candidate set (role primary + role fallback + every available,
   unexpired, quota-healthy catalog model with a benchmark row) and rank it by
   ``core.model_scoring.fitness()`` (quality 0.75 + efficiency 0.25).
2. **Primary unavailable/degraded** (expired promo, quota, 429, empty
   completion) → best-ranked non-primary candidate.
3. **Hard tasks** (``assessment.relevant_max(areas) >= hard_threshold``) →
   the picked model's role quality must also clear ``hard_threshold``;
   escalate to the best-ranked candidate that does.
4. **Anti-churn hysteresis**: on a healthy primary, only switch when the best
   candidate's fitness beats the primary by ≥ ``score_advantage_threshold``
   (default **8**) — never on a marginal edge.
5. **Pinned roles** (``roles.<path>.pin: true``, e.g. ``deep_research.web_search``)
   are never proposed for a swap — structural, not incidental.

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
from typing import Any, Callable, Mapping, MutableMapping, Optional, Sequence

import yaml

from core.agent_config import get_agent_config
from core.difficulty_scorer import DifficultyAssessment
from core.handoff import transfer_control
from core.model_scoring import fitness, quality_for_role, rank_candidates, split_model_key
from schemas.handoff import PipelineName

logger = logging.getLogger(__name__)

_BENCHMARKS_PATH = Path(__file__).parent.parent / "config" / "model_benchmarks.yaml"

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
_quota_tracker: Optional["Any"] = None


def default_quota_remaining(provider: str, model: str) -> int:
    """Live remaining-call budget for *provider*/*model* (WAVE-21).

    Production call sites pass this as ``quota_remaining=`` so ``select_for_role``
    derives ``quota_exhausted`` from real ledger state instead of the hardcoded
    ``"ok"`` default. Lazy singleton: the SQLite ledger is only touched on first
    use. Tests should inject a stub rather than touching the real ledger.
    """
    global _quota_tracker
    if _quota_tracker is None:
        from core.quotas import QuotaTracker

        _quota_tracker = QuotaTracker()
    return _quota_tracker.remaining(provider, model)


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


def temporal_status(
    provider: str,
    model: str,
    *,
    today: Optional[date] = None,
    benchmarks: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Status dict for any model row carrying ``free_until`` (CLI / diagnostics).

    Generic replacement for the former hy3-specific status: driven entirely
    by the model row's ``free_until`` + ``expired_fallback`` fields, never by
    a hardcoded model constant.
    """
    day = today or date.today()
    until = model_free_until(provider, model, benchmarks=benchmarks)
    assert until is not None, f"{provider}/{model} has no free_until to report"
    delta = (until - day).days
    entry = get_model_entry(provider, model, benchmarks=benchmarks)
    fb = entry.get("expired_fallback") or {
        "provider": "groq",
        "model": "openai/gpt-oss-120b",
    }
    bench = benchmarks if benchmarks is not None else _load_benchmarks()
    warn_days = int((bench.get("selection_defaults") or {}).get("warn_hy3_days", 3))
    return {
        "model": model,
        "provider": provider,
        "free_until": until.isoformat(),
        "days_remaining": delta,
        "expired": delta < 0,
        "warn": 0 <= delta <= warn_days,
        "expired_fallback": dict(fb),
    }


def hy3_status(*, today: Optional[date] = None) -> dict[str, Any]:
    """CLI status for the ``tencent/hy3:free`` row — the documented expiry example.

    The expiry mechanism itself is fully generic (:func:`temporal_status`);
    this thin wrapper keeps the historical CLI call site intact even though
    hy3 left the catalog (the benchmark row still holds the ``free_until``).
    """
    return temporal_status("openrouter", "tencent/hy3:free", today=today)


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
    return None


def _is_primary_degraded(status: str) -> bool:
    return (status or "ok").strip().lower() in DEGRADED_STATUSES


def select_for_role(
    *role_path: str,
    assessment: DifficultyAssessment,
    today: Optional[date] = None,
    config_path: Optional[Path] = None,
    benchmarks_path: Optional[Path] = None,
    force_primary: bool = False,
    primary_status: str = "ok",
    quota_remaining: Optional[Callable[[str, str], int]] = None,
) -> ModelSelection:
    """Choose the best model for ``role_path`` by WAVE-20 fitness ranking.

    Pure decision function — no HTTP. Expired promos are replaced
    automatically; pinned roles never swap; a healthy primary keeps its seat
    unless the best candidate wins by ``score_advantage_threshold``.

    Parameters
    ----------
    primary_status:
        ``\"ok\"`` (default) or a degraded signal from
        :data:`DEGRADED_STATUSES` (``quota_exhausted``, ``rate_limited_429``,
        ``empty_completion``, ``unavailable``, ``degraded``). When left
        ``\"ok\"`` and *quota_remaining* is provided, primary quota exhaustion
        is derived from real ledger state.
    quota_remaining:
        Optional ``(provider, model) -> remaining calls`` callable (e.g.
        :func:`default_quota_remaining`). Exhausted models are excluded from
        the candidate set; an exhausted primary is treated as degraded.
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
    status = (primary_status or "ok").strip().lower()

    def _quota_healthy(provider: str, model: str) -> bool:
        if quota_remaining is None:
            return True
        try:
            return int(quota_remaining(provider, model)) > 0
        except Exception:
            return True

    # WAVE-21: derive quota degradation from the real ledger unless the caller
    # supplied an explicit status signal.
    if status == "ok" and not _quota_healthy(primary_p, primary_m):
        status = "quota_exhausted"

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
            },
        )

    def _pick(
        key: str,
        *,
        used_fallback: bool,
        reason: str,
        chain: Optional[dict[str, str]] = None,
    ) -> ModelSelection:
        provider, model = split_model_key(key)
        return _sel(
            provider,
            model,
            used_fallback=used_fallback,
            reason=reason,
            chain_fallback=chain,
        )

    def _role_chain_for(key: str) -> Optional[dict[str, str]]:
        """Role fallback as the runtime next hop — unless the pick IS it."""
        if not (fb_p and fb_m):
            return None
        picked_p, picked_m = split_model_key(key)
        if (picked_p, picked_m) == (fb_p, fb_m):
            return None
        return {"provider": fb_p, "model": fb_m}

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

    if force_primary:
        return _sel(
            primary_p,
            primary_m,
            used_fallback=False,
            reason="Stay on primary (force_primary)",
            chain_fallback=dict(fb_cfg) if isinstance(fb_cfg, dict) else None,
        )

    # --- Pinned roles never swap (structural; web_search abort-not-swap rule) ---
    if bool(rules.get("pin")):
        return _sel(
            primary_p,
            primary_m,
            used_fallback=False,
            reason=(
                f"Role {dotted} pinned to primary {primary_p}/{primary_m}; "
                f"no model swap allowed"
            ),
            chain_fallback=dict(fb_cfg) if isinstance(fb_cfg, dict) else None,
        )

    # --- WAVE-21: candidate set + fitness ranking ---
    # Role primary + role fallback + every available, unexpired,
    # quota-healthy catalog model with a benchmark row.
    primary_key = model_key(primary_p, primary_m)
    candidates: list[str] = [primary_key]
    if fb_p and fb_m:
        candidates.append(model_key(fb_p, fb_m))
    for key, row in (bench.get("models") or {}).items():
        if not isinstance(row, dict) or row.get("available") is False:
            continue
        if key in candidates:
            continue
        try:
            cand_p, cand_m = split_model_key(key)
        except ValueError:
            continue
        if not is_model_available(cand_p, cand_m, today=day, benchmarks=bench):
            continue
        if not _quota_healthy(cand_p, cand_m):
            continue
        candidates.append(key)
    ranked = rank_candidates(dotted, candidates, benchmarks=bench)
    primary_fit = fitness(primary_key, dotted, benchmarks=bench)

    # --- (1) Primary degraded / unhealthy (quota, 429, empty) ---
    if _is_primary_degraded(status):
        for key, fit in ranked:
            if key == primary_key:
                continue
            return _pick(
                key,
                used_fallback=True,
                reason=(
                    f"Primary degraded ({status}); score-driven switch to best "
                    f"candidate {key} (fitness {fit})"
                ),
                chain=_role_chain_for(key),
            )
        return _sel(
            primary_p,
            primary_m,
            used_fallback=False,
            reason=f"Primary degraded ({status}) but no alternative candidate",
            chain_fallback=dict(fb_cfg) if isinstance(fb_cfg, dict) else None,
        )

    # --- (2) Healthy primary: hard-threshold escalation + hysteresis ---
    selected_key = primary_key
    if (
        assessment.relevant_max(areas) >= hard_th
        and quality_for_role(primary_key, dotted, benchmarks=bench) < hard_th
    ):
        for key, fit in ranked:
            if key == primary_key:
                continue
            if quality_for_role(key, dotted, benchmarks=bench) >= hard_th:
                selected_key, selected_fit = key, fit
                break

    if selected_key == primary_key and ranked and ranked[0][0] != primary_key:
        best_key, best_fit = ranked[0]
        if best_fit - primary_fit >= advantage_th:
            selected_key, selected_fit = best_key, best_fit

    if selected_key != primary_key:
        return _pick(
            selected_key,
            used_fallback=True,
            reason=(
                f"Score-driven routing prefers {selected_key} over primary "
                f"{primary_key} (fitness Δ{selected_fit - primary_fit:.2f} "
                f">= {advantage_th})"
            ),
            chain=_role_chain_for(selected_key),
        )

    # Healthy primary, adequate specialization → keep primary
    # (even if the best candidate edges fitness by < score_advantage_threshold)
    return _sel(
        primary_p,
        primary_m,
        used_fallback=False,
        reason=(
            f"Primary healthy and adequate for {dotted} "
            f"(overall={assessment.overall}, status={status}, "
            f"areas={areas}, advantage_th={advantage_th})"
        ),
        chain_fallback={"provider": fb_p, "model": fb_m} if fb_p and fb_m else None,
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
