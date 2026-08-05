#!/usr/bin/env python3
"""WAVE-20: live efficiency benchmark for every configured text model.

Measures one tiny streaming completion per catalog model (time-to-first-token,
tokens/sec, context window from the live /models metadata) and writes a
stack-relative rubric (speed 0.50 / context 0.25 / capacity 0.25) into
``config/model_efficiency.json`` so ``core/model_scoring.efficiency_score``
can route on measured data instead of estimates.

Usage::

    python scripts/benchmark_models.py                 # dry-run: plan only
    python scripts/benchmark_models.py --yes           # run, print, no persist
    python scripts/benchmark_models.py --yes --write   # run + persist JSON
    python scripts/benchmark_models.py --only groq,mistral --yes --write
    python scripts/benchmark_models.py --yes --quota-margin 20

The script never edits ``model_router.yaml``; it only reads it. Quota ledger
(``data/quotas.db``) is honoured when present: providers below the margin are
skipped, and successful measurements are booked via the tracker.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# Keep single measurements bounded: never let a slow free endpoint stall the
# whole run. Client timeout is read lazily inside _openai_compat_client.
os.environ.setdefault("MULTIAGENT_HTTP_TIMEOUT", "60")

_PROMPT = "Write a short sentence describing a calm blue ocean at sunset."
_MAX_TOKENS = 128
_MAX_ATTEMPTS = 2
_ATTEMPT_DELAY_S = 3.0
_QUOTA_DB = _PROJECT_ROOT / "data" / "quotas.db"
_DEFAULT_OUT = _PROJECT_ROOT / "config" / "model_efficiency.json"
_UA = {"User-Agent": "Free-MultiAgent/1.0 efficiency-benchmark (read-only)"}
_COHERE_BASE = "https://api.cohere.com"
# Non-conversational catalog entries (safety classifiers / guard rails) are not
# benchmarkable via a chat completion and are skipped with a reason.
_NON_CONVERSATIONAL = ("safeguard", "content-safety")
# Providers that do not expose a per-model context window in /models: use a
# conservative documented family value (systems.md §4.1). Unknown -> 0 credit.
_PROVIDER_CONTEXT_FALLBACK: dict[str, int] = {
    "gemini": 1_000_000,  # Gemini flash-class family (public docs)
    "agnes": 100_000,  # agnes-2.x "large context" fair-use tier
    "cerebras": 131_072,  # gpt-oss-120b class
}


def _http_get_json(url: str, bearer: Optional[str] = None) -> dict[str, Any]:
    headers = dict(_UA)
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 (pinned https URLs)
        return json.loads(resp.read().decode("utf-8"))


def _fetch_context_windows(provider: str, meta: dict[str, Any]) -> dict[str, int]:
    """Live ``context_window`` per model id from the provider /models endpoint.

    Returns model-id -> context_window; unknown ids are simply absent.
    """
    out: dict[str, int] = {}
    base = meta.get("base_url")
    env_key = meta.get("env_key")
    import os as _os

    bearer = (_os.environ.get(env_key) or "").strip() if env_key else ""
    if provider == "ollama":
        bearer = ""
    urls: list[str] = []
    if provider == "cohere":
        urls = [f"{_COHERE_BASE}/v2/models", f"{_COHERE_BASE}/v1/models"]
    elif base:
        urls = [base.rstrip("/") + "/models"]
    for url in urls:
        try:
            payload = _http_get_json(url, bearer)
        except Exception:
            continue
        entries = payload.get("data") or payload.get("models") or []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            model_id = str(entry.get("id") or entry.get("name") or entry.get("model") or "")
            if not model_id:
                continue
            if model_id.startswith("models/"):
                model_id = model_id[len("models/") :]
            ctx = (
                entry.get("context_window")
                or entry.get("context_length")
                or entry.get("max_context_length")
                or 0
            )
            try:
                ctx_int = int(ctx)
            except (TypeError, ValueError):
                ctx_int = 0
            if ctx_int > 0:
                out[model_id] = ctx_int
    return out


def _delta_text(event: Any, provider: str) -> str:
    """All streamed text from one event (content + reasoning, or cohere content/thinking).

    Reasoning/thinking tokens are user-visible output in most free models, so the
    rubric measures raw token throughput across both streams.
    """
    if provider == "cohere":
        delta = getattr(event, "delta", None)
        message = getattr(delta, "message", None) if delta is not None else None
        content = getattr(message, "content", None) if message is not None else None
        thinking = str(getattr(content, "thinking", "") or "")
        text = str(getattr(content, "text", "") or "")
        return thinking + text
    choices = getattr(event, "choices", None)
    if not choices:
        return ""
    delta = getattr(choices[0], "delta", None)
    if delta is None:
        return ""
    content = str(getattr(delta, "content", "") or "")
    reasoning = str(getattr(delta, "reasoning_content", None) or "")
    return content + reasoning


def _completion(
    client: Any,
    provider: str,
    model: str,
) -> tuple[float, float, float]:
    """One timed streaming completion.

    Returns ``(first_token_ms, tokens_per_sec, wall_s)``. Token count is the
    accumulated output word count (rubric-grade approximation — the prompt
    forces a short sentence reply so variance is acceptable).
    """
    messages = [{"role": "user", "content": _PROMPT}]
    t0 = time.perf_counter()
    if provider == "cohere":
        stream = client.chat_stream(
            model=model, messages=messages, max_tokens=_MAX_TOKENS
        )
    else:
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=_MAX_TOKENS,
            stream=True,
        )
    first_s: Optional[float] = None
    words = 0
    for event in stream:
        text = _delta_text(event, provider)
        if not text:
            continue
        if first_s is None:
            first_s = time.perf_counter()
        words += len(text.split())
    t_end = time.perf_counter()
    if first_s is None:
        raise RuntimeError(f"{model}: no content tokens received")
    first_ms = (first_s - t0) * 1000.0
    out_tokens = max(1.0, float(words))
    tps = out_tokens / max(1e-6, t_end - first_s)
    return round(first_ms, 1), round(tps, 2), round(t_end - t0, 3)


def _stack_scores(measured: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Stack-relative rubric (systems.md §4.1): speed linear, context log, capacity = tps*ctx."""
    tps_vals = [m["tokens_per_sec"] for m in measured.values() if m.get("tokens_per_sec")]
    max_tps = max(tps_vals) if tps_vals else 1.0
    ctx_vals = [int(m["context_window"]) for m in measured.values() if m.get("context_window")]
    max_ctx = max(ctx_vals) if ctx_vals else 1
    out: dict[str, dict[str, Any]] = {}
    for key, m in measured.items():
        tps = m.get("tokens_per_sec") or 0.0
        ctx = int(m.get("context_window") or 0)
        speed = round(min(100.0, 100.0 * tps / max_tps), 1) if tps else 0.0
        context = (
            round(100.0 * math.log(ctx + 1) / math.log(max_ctx + 1), 1) if ctx else 0.0
        )
        capacity = (
            round(min(100.0, 100.0 * (tps * ctx) / (max_tps * max_ctx)), 1)
            if tps and ctx
            else 0.0
        )
        out[key] = {
            "tokens_per_sec": m["tokens_per_sec"],
            "first_token_ms": m["first_token_ms"],
            "context_window": ctx,
            "speed_score": speed,
            "context_score": context,
            "capacity_score": capacity,
        }
    return out


def _targets(only: Optional[list[str]] = None) -> list[tuple[str, str, str]]:
    """Catalog targets: (provider, model, kind) — text models only."""
    from core.provider_registry import all_registered_models, get_provider_meta

    out: list[tuple[str, str, str]] = []
    for provider, model in all_registered_models():
        lower = model.lower()
        if "embed" in lower or lower.startswith("embed-"):
            continue
        if any(tag in lower for tag in _NON_CONVERSATIONAL):
            continue
        kind = (get_provider_meta(provider) or {}).get("kind", "openai_compatible")
        out.append((provider, model, kind))
    out.sort()
    if only:
        wanted = {p.strip().lower() for p in only}
        out = [t for t in out if t[0] in wanted]
    return out


def _make_tracker() -> Optional[Any]:
    if not _QUOTA_DB.exists():
        return None
    from core.quotas import QuotaTracker

    return QuotaTracker()


def _refresh_context(out_path: str) -> int:
    """Re-fetch context windows and rescale an existing JSON (no completions)."""
    from dotenv import load_dotenv

    load_dotenv()
    from core.provider_registry import get_provider_meta

    out = Path(out_path)
    if not out.exists():
        print(f"{out} not found — run --yes --write first.")
        return 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    measured = payload.get("measured") or {}
    by_provider: dict[str, dict[str, int]] = {}
    for key in measured:
        provider = key.split("/", 1)[0]
        if provider not in by_provider:
            by_provider[provider] = _fetch_context_windows(
                provider, get_provider_meta(provider)
            )
        model = key.split("/", 1)[1]
        ctx = 0
        for candidate in (model, model.split("/")[-1]):
            if candidate in by_provider[provider]:
                ctx = by_provider[provider][candidate]
                break
        if not ctx:
            ctx = _PROVIDER_CONTEXT_FALLBACK.get(provider, 0)
        measured[key]["context_window"] = ctx
    fresh = _stack_scores({k: v for k, v in measured.items()})
    payload["measured"] = fresh
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"refreshed context windows for {len(fresh)} models -> {out}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure one tiny completion per catalog model and score the stack."
    )
    parser.add_argument("--yes", action="store_true", help="actually run live (dry-run by default)")
    parser.add_argument("--write", action="store_true", help="persist JSON to --out")
    parser.add_argument("--refresh-context", action="store_true", help="re-fetch context windows + rescale existing JSON (no completions)")
    parser.add_argument("--only", default="", help="comma-separated provider filter")
    parser.add_argument("--quota-margin", type=int, default=10, help="skip providers under this many remaining calls")
    parser.add_argument("--out", default=str(_DEFAULT_OUT), help="JSON output path")
    args = parser.parse_args(argv)

    targets = _targets([p for p in args.only.split(",") if p] or None)
    tracker = _make_tracker()

    plan: list[dict[str, Any]] = []
    for provider, model, kind in targets:
        remaining = None
        if tracker is not None:
            remaining = tracker.remaining(provider, model)
        plan.append(
            {
                "key": f"{provider}/{model}",
                "provider": provider,
                "model": model,
                "kind": kind,
                "remaining": remaining,
                "skip": remaining is not None and remaining < args.quota_margin,
                "reason": "quota<margin" if remaining is not None and remaining < args.quota_margin else "",
            }
        )

    print(f"=== Efficiency benchmark plan: {len(plan)} models (dry-run: {not args.yes}) ===")
    for row in plan:
        flag = "  SKIP" if row["skip"] else ""
        quota = f" remaining={row['remaining']}" if row["remaining"] is not None else ""
        print(f"  {row['key']:<58}{quota}{flag}")

    if not args.yes:
        if args.refresh_context:
            return _refresh_context(args.out)
        print("Dry-run — pass --yes to measure (--write to persist).")
        return 0

    from dotenv import load_dotenv

    load_dotenv()
    from core.clients import get_client

    measured: dict[str, dict[str, Any]] = {}
    skipped: dict[str, str] = {}
    errors: dict[str, str] = {}
    ctx_cache: dict[str, dict[str, int]] = {}

    for row in plan:
        if row["skip"]:
            skipped[row["key"]] = row["reason"]
            continue
        key, provider, model = row["key"], row["provider"], row["model"]
        try:
            if provider not in ctx_cache:
                from core.provider_registry import get_provider_meta

                ctx_cache[provider] = _fetch_context_windows(
                    provider, get_provider_meta(provider)
                )
            ctx_map = ctx_cache[provider]
            ctx = 0
            for candidate in (model, model.split("/")[-1]):
                if candidate in ctx_map:
                    ctx = ctx_map[candidate]
                    break
            if not ctx:
                ctx = _PROVIDER_CONTEXT_FALLBACK.get(provider, 0)
            client = get_client(provider)
            first_ms = tps = wall = None
            last_exc: Optional[Exception] = None
            for attempt in range(_MAX_ATTEMPTS):
                try:
                    first_ms, tps, wall = _completion(client, provider, model)
                    break
                except Exception as exc:  # noqa: BLE001 — transient 429/empty-stream
                    last_exc = exc
                    if attempt < _MAX_ATTEMPTS - 1:
                        time.sleep(_ATTEMPT_DELAY_S)
            if first_ms is None:
                raise RuntimeError(f"{last_exc}") from last_exc
        except Exception as exc:  # noqa: BLE001 — one bad model must not kill the run
            errors[key] = f"{type(exc).__name__}: {exc}"
            print(f"  ERROR {key}: {errors[key]}")
            continue
        measured[key] = {
            "tokens_per_sec": tps,
            "first_token_ms": first_ms,
            "context_window": ctx,
            "wall_s": wall,
        }
        if tracker is not None:
            row_id = tracker.try_reserve(provider, model)
            if row_id is not None:
                tracker.confirm(row_id)
        print(f"  OK    {key}: {tps} tps, ttft {first_ms} ms, ctx {ctx}")

    scores = _stack_scores(measured)
    payload: dict[str, Any] = {
        "updated": date.today().isoformat(),
        "note": (
            f"one {_MAX_TOKENS}-token completion per model; stack-relative scores "
            "(speed 0.50 linear / context 0.25 log / capacity 0.25 = tps*ctx). "
            "ttft = first streamed text token incl. reasoning. systems.md §4.1 WAVE-20."
        ),
        "measured": scores,
        "skipped": skipped,
        "errors": errors,
    }
    print(
        f"=== done: {len(scores)} measured, {len(skipped)} skipped, {len(errors)} errors ==="
    )
    if args.write:
        out = Path(args.out)
        out.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
