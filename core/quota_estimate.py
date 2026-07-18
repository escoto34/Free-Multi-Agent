"""
Live estimates of how many full System A / System B runs remain today.

Reads roles + limits from ``config/model_router.yaml`` (via agent_config) and
optional multiplicity from ``config/model_benchmarks.yaml``. Never hardcodes
current model IDs — swapping YAML changes the estimate immediately.

Two routing scenarios (PARTE 3 difficulty selector):

* **primary** — every role uses its configured primary model.
* **fallback** — every role that has a role-level ``fallback`` uses it
  (realistic worst case for scarce buckets; not the optimistic mix).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import yaml

from core.agent_config import get_agent_config, get_full_config, get_max_fix_cycles, reload_config
from core.model_selector import reload_benchmarks
from core.quotas import QuotaTracker, _PER_MODEL_PROVIDERS

_BENCHMARKS_PATH = Path(__file__).resolve().parent.parent / "config" / "model_benchmarks.yaml"

# Roles that invoke an LLM (exclude pure local nodes: test_executor, git_*).
# Multiplicity is "calls per complete successful-ish run" for *typical* path.
# System A: architect → coder → debugger once (tests pass on first try).
# System B: each research node once.
_DEFAULT_SYSTEM_SPECS: dict[str, list[tuple[tuple[str, ...], int]]] = {
    "vibe_coding": [
        (("vibe_coding", "architect"), 1),
        (("vibe_coding", "coder"), 1),
        (("vibe_coding", "debugger"), 1),
    ],
    "deep_research": [
        (("deep_research", "safety_filter"), 1),
        (("deep_research", "context_compressor"), 1),
        (("deep_research", "web_search"), 1),
        (("deep_research", "grounding"), 1),
        (("deep_research", "synthesizer"), 1),
    ],
}


def _load_benchmarks() -> dict[str, Any]:
    try:
        with open(_BENCHMARKS_PATH, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except OSError:
        return {}


def pipeline_role_calls(
    system: str,
    *,
    config_path: Optional[Path] = None,
    typical: bool = True,
) -> list[tuple[tuple[str, ...], int]]:
    """Return [(role_path_tuple, calls_per_run), ...] for a system.

    *typical=True*: one pass of coder/debugger (happy path).
    *typical=False*: worst fix loop — coder + debugger each ``max_fix_cycles``.
    """
    # Prefer optional YAML override under model_benchmarks.pipeline_calls
    bench = _load_benchmarks()
    override = (bench.get("pipeline_calls") or {}).get(system)
    if isinstance(override, list) and override:
        out: list[tuple[tuple[str, ...], int]] = []
        for item in override:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "")
            if not role:
                continue
            parts = tuple(role.split("."))
            n = int(item.get("calls", 1))
            out.append((parts, max(1, n)))
        if out:
            return out

    base = list(_DEFAULT_SYSTEM_SPECS.get(system) or [])
    if not base:
        return []

    if system == "vibe_coding" and not typical:
        max_c = get_max_fix_cycles(config_path=config_path)
        rewritten: list[tuple[tuple[str, ...], int]] = []
        for path, n in base:
            if path[-1] in ("coder", "debugger"):
                rewritten.append((path, max(1, max_c)))
            else:
                rewritten.append((path, n))
        return rewritten
    return base


def resolve_role_endpoint(
    role_path: Sequence[str],
    *,
    scenario: str,
    config_path: Optional[Path] = None,
) -> dict[str, str]:
    """Map a role to provider/model for ``primary`` or ``fallback`` scenario."""
    cfg = get_agent_config(*role_path, config_path=config_path)
    if not isinstance(cfg, dict) or "provider" not in cfg:
        raise KeyError(f"Not a role config: {'.'.join(role_path)}")

    primary = {
        "provider": str(cfg["provider"]),
        "model": str(cfg["model"]),
        "source": "primary",
    }
    if scenario != "fallback":
        return primary

    fb = cfg.get("fallback")
    if isinstance(fb, dict) and fb.get("provider") and fb.get("model"):
        return {
            "provider": str(fb["provider"]),
            "model": str(fb["model"]),
            "source": "fallback",
        }
    return primary


def quota_bucket(provider: str, model: str) -> str:
    """Stable key matching :class:`~core.quotas.QuotaTracker` accounting."""
    if provider in _PER_MODEL_PROVIDERS:
        return f"{provider}/{model}"
    return f"{provider}/__shared__"


@dataclass
class RoleCallPlan:
    role: str
    calls: int
    provider: str
    model: str
    source: str  # primary | fallback
    bucket: str


@dataclass
class BucketDemand:
    bucket: str
    provider: str
    model_sample: str
    calls_per_run: int
    used: int
    limit: int
    remaining: int
    runs_supported: int  # floor(remaining / calls_per_run), or inf-like large


@dataclass
class SystemEstimate:
    system: str
    label: str
    scenario: str
    roles: list[RoleCallPlan] = field(default_factory=list)
    buckets: list[BucketDemand] = field(default_factory=list)
    total_llm_calls: int = 0
    bottleneck_bucket: Optional[str] = None
    runs_remaining: int = 0


def _provider_limit(
    provider: str,
    *,
    tracker: QuotaTracker,
    config_path: Optional[Path] = None,
) -> int:
    """Daily soft-cap for *provider* from the active (or fixture) router YAML."""
    yaml_keys = (
        "daily_limit",
        "daily_limit_shared",
        "daily_limit_per_model",
    )
    if config_path is not None:
        try:
            cfg = get_agent_config("providers", provider, config_path=config_path)
            for key in yaml_keys:
                if key in cfg:
                    return int(cfg[key])
        except (KeyError, TypeError, ValueError):
            pass
    try:
        return int(tracker._limit_for(provider))  # noqa: SLF001 — public via remaining math
    except Exception:
        return 200


def _limit_and_usage(
    tracker: QuotaTracker,
    provider: str,
    model: str,
    *,
    config_path: Optional[Path] = None,
) -> tuple[int, int, int]:
    used = tracker.get_usage(provider, model)
    limit = _provider_limit(provider, tracker=tracker, config_path=config_path)
    remaining = max(0, limit - used)
    return used, limit, remaining


def build_system_estimate(
    system: str,
    *,
    scenario: str = "primary",
    tracker: Optional[QuotaTracker] = None,
    config_path: Optional[Path] = None,
    typical: bool = True,
    reload: bool = True,
) -> SystemEstimate:
    """Compute remaining full runs for one system + routing scenario."""
    if reload:
        reload_config()
        reload_benchmarks()

    qt = tracker or QuotaTracker()
    labels = {
        "vibe_coding": "System A — Vibe Coding",
        "deep_research": "System B — Deep Research",
    }
    est = SystemEstimate(
        system=system,
        label=labels.get(system, system),
        scenario=scenario,
    )

    role_calls = pipeline_role_calls(
        system, config_path=config_path, typical=typical
    )
    demand: dict[str, dict[str, Any]] = {}

    for role_path, n_calls in role_calls:
        ep = resolve_role_endpoint(
            role_path, scenario=scenario, config_path=config_path
        )
        role_id = ".".join(role_path)
        bucket = quota_bucket(ep["provider"], ep["model"])
        plan = RoleCallPlan(
            role=role_id,
            calls=n_calls,
            provider=ep["provider"],
            model=ep["model"],
            source=ep["source"],
            bucket=bucket,
        )
        est.roles.append(plan)
        est.total_llm_calls += n_calls

        slot = demand.setdefault(
            bucket,
            {
                "provider": ep["provider"],
                "model": ep["model"],
                "calls": 0,
            },
        )
        slot["calls"] += n_calls
        # Keep a representative model id for display
        slot["model"] = ep["model"]

    runs_list: list[int] = []
    for bucket, info in sorted(demand.items()):
        provider = info["provider"]
        model = info["model"]
        used, limit, remaining = _limit_and_usage(
            qt, provider, model, config_path=config_path
        )
        cpr = int(info["calls"])
        if cpr <= 0:
            supported = 10**9
        else:
            supported = remaining // cpr
        runs_list.append(supported)
        est.buckets.append(
            BucketDemand(
                bucket=bucket,
                provider=provider,
                model_sample=model,
                calls_per_run=cpr,
                used=used,
                limit=limit,
                remaining=remaining,
                runs_supported=supported,
            )
        )

    if est.buckets:
        # Bottleneck = min runs_supported
        worst = min(est.buckets, key=lambda b: b.runs_supported)
        est.bottleneck_bucket = worst.bucket
        est.runs_remaining = max(0, worst.runs_supported)
    else:
        est.runs_remaining = 0

    return est


def estimate_all(
    *,
    tracker: Optional[QuotaTracker] = None,
    config_path: Optional[Path] = None,
    typical: bool = True,
) -> dict[str, Any]:
    """Full report structure for CLI / tests."""
    reload_config()
    reload_benchmarks()
    qt = tracker or QuotaTracker()

    systems = ("vibe_coding", "deep_research")
    scenarios = ("primary", "fallback")
    out: dict[str, Any] = {
        "systems": {},
        "usage_today": qt.status_summary(),
    }
    for system in systems:
        out["systems"][system] = {}
        for sc in scenarios:
            est = build_system_estimate(
                system,
                scenario=sc,
                tracker=qt,
                config_path=config_path,
                typical=typical,
                reload=False,  # already reloaded once
            )
            out["systems"][system][sc] = est
    return out


def format_quota_report(
    report: Optional[Mapping[str, Any]] = None,
    *,
    tracker: Optional[QuotaTracker] = None,
    config_path: Optional[Path] = None,
) -> str:
    """Human-readable multi-section report for the ``quota`` CLI command."""
    data = report or estimate_all(tracker=tracker, config_path=config_path)
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("QUOTA & PIPELINE CAPACITY (live from model_router.yaml)")
    lines.append("=" * 72)

    usage = data.get("usage_today") or {}
    lines.append("")
    lines.append("Today's recorded usage (data/quotas.db):")
    if not usage:
        lines.append("  (no calls recorded yet today)")
    else:
        for label, stats in sorted(usage.items()):
            lines.append(
                f"  • {label}: used {stats['used']}, remaining {stats['remaining']}"
            )

    for system in ("vibe_coding", "deep_research"):
        block = (data.get("systems") or {}).get(system) or {}
        for sc in ("primary", "fallback"):
            est: SystemEstimate = block[sc]
            sc_label = (
                "ALL PRIMARY"
                if sc == "primary"
                else "PLANNER FALLBACK (worst-case: every role with fallback uses it)"
            )
            lines.append("")
            lines.append("-" * 72)
            lines.append(f"{est.label}  |  scenario: {sc_label}")
            lines.append("-" * 72)
            lines.append(
                f"LLM calls per typical run: {est.total_llm_calls} "
                f"(local nodes like test_executor/git excluded)"
            )
            lines.append("Per-role plan:")
            for r in est.roles:
                lines.append(
                    f"  • {r.role}: {r.calls}×  →  {r.provider}/{r.model}  [{r.source}]"
                )
            lines.append("Quota buckets touched:")
            for b in est.buckets:
                lines.append(
                    f"  • {b.bucket}: {b.calls_per_run} call(s)/run | "
                    f"used {b.used}/{b.limit} | remaining {b.remaining} | "
                    f"supports ~{b.runs_supported} run(s)"
                )
            lines.append(
                f"→ Complete runs remaining today: **{est.runs_remaining}** "
                f"(bottleneck: {est.bottleneck_bucket or 'n/a'})"
            )

    lines.append("")
    lines.append(
        "Note: estimates re-read model_router.yaml + model_benchmarks.yaml each run. "
        "Groq limits are per-model; OpenRouter/Cohere/etc. share one daily bucket."
    )
    lines.append("=" * 72)
    return "\n".join(lines)
