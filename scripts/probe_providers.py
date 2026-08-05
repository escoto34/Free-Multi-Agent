"""WAVE-19 — read-only provider catalog probe.

For each provider in ``config/model_router.yaml`` with an API key available,
list the live model ids (``GET /models`` — no completions, no writes) and
diff them against the configured catalog::

    python scripts/probe_providers.py                 # all providers with keys
    python scripts/probe_providers.py --only groq,openrouter

Prints a 3-way diff per provider (matched / gone / live-only) and exits 1
when any configured model is missing from its provider's live catalog.
Providers without a key in the environment are skipped, not failed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:  # noqa: E402
    sys.path.insert(0, str(_ROOT))  # noqa: E402

from core.provider_registry import get_registered_providers  # noqa: E402

_TIMEOUT = 20
_COHERE_V1 = "https://api.cohere.com/v1/models"
_COHERE_V2 = "https://api.cohere.com/v2/models"


@dataclass
class ProbeResult:
    provider: str
    ok: bool
    live: set[str] = field(default_factory=set)
    error: str | None = None

    @property
    def count(self) -> int:
        return len(self.live)


@dataclass
class CatalogDiff:
    gone: list[str] = field(default_factory=list)
    live_only: list[str] = field(default_factory=list)
    matched: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.gone


def _http_get_json(url: str, headers: Mapping[str, str], *, timeout: float = _TIMEOUT) -> Any:
    merged = {"User-Agent": "Free-MultiAgent/1.0 catalog-probe (read-only)"}
    merged.update(dict(headers))
    req = urllib.request.Request(url, headers=merged)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def _normalize_id(raw: str) -> str:
    s = str(raw or "").strip()
    return s[len("models/") :] if s.startswith("models/") else s


def _probe_openai_compat(meta: Mapping[str, Any], env: Mapping[str, str]) -> set[str]:
    key = env.get(str(meta.get("env_key") or ""), "")
    if not key:
        raise RuntimeError(f"no {meta.get('env_key')} in environment")
    base = str(meta.get("base_url") or "").rstrip("/")
    data = _http_get_json(base + "/models", {"Authorization": f"Bearer {key}"})
    return {
        _normalize_id(str(m["id"]))
        for m in (data.get("data") or [])
        if isinstance(m, dict) and m.get("id")
    }


def _probe_cohere(meta: Mapping[str, Any], env: Mapping[str, str]) -> set[str]:
    key = env.get("COHERE_API_KEY", "")
    if not key:
        raise RuntimeError("no COHERE_API_KEY in environment")
    last: Exception | None = None
    for url in (_COHERE_V1, _COHERE_V2):
        try:
            data = _http_get_json(url, {"Authorization": f"Bearer {key}"})
            rows = data.get("models") or []
            if rows and isinstance(rows[0], dict) and "name" in rows[0]:
                ids = {str(m["name"]) for m in rows if m.get("name")}
            else:
                ids = {str(m["id"]) for m in rows if isinstance(m, dict) and m.get("id")}
            if ids:
                return ids
        except urllib.error.HTTPError as exc:
            last = exc
    raise last if last is not None else RuntimeError("cohere probe returned no models")


def _probe_ollama(meta: Mapping[str, Any], env: Mapping[str, str]) -> set[str]:
    base = str(meta.get("base_url") or "http://localhost:11434/v1").rstrip("/")
    root = base[: -len("/v1")] if base.endswith("/v1") else base
    data = _http_get_json(root.rstrip("/") + "/api/tags", {})
    return {
        _normalize_id(str(m.get("name") or m.get("model") or ""))
        for m in (data.get("models") or [])
        if isinstance(m, dict)
    }


def probe_provider(
    name: str,
    meta: Mapping[str, Any],
    *,
    env: Mapping[str, str] | None = None,
) -> ProbeResult:
    """Live ``GET /models`` for one provider — no completions, no writes."""
    env = env if env is not None else os.environ
    try:
        if name == "ollama":
            live = _probe_ollama(meta, env)
        elif name == "cohere":
            live = _probe_cohere(meta, env)
        else:
            live = _probe_openai_compat(meta, env)
        return ProbeResult(provider=name, ok=True, live=set(live))
    except Exception as exc:
        return ProbeResult(provider=name, ok=False, error=str(exc))


def diff_catalog(configured: set[str], live: set[str]) -> CatalogDiff:
    """3-way diff: configured-but-gone / live-only / matched."""
    return CatalogDiff(
        gone=sorted(configured - live),
        live_only=sorted(live - configured),
        matched=sorted(configured & live),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        help="comma-separated provider names to probe (default: all)",
    )
    args = parser.parse_args(argv)

    providers = get_registered_providers()
    names = sorted(providers)
    if args.only:
        wanted = {n.strip().lower() for n in args.only.split(",") if n.strip()}
        names = [n for n in names if n in wanted]

    drift = False
    for name in names:
        meta = providers[name]
        key = meta.get("env_key")
        has_key = name == "ollama" or bool(key and os.environ.get(key))
        if not has_key:
            print(f"[{name}] skipped — no {key} in environment")
            continue
        result = probe_provider(name, meta)
        if not result.ok:
            print(f"[{name}] ERROR — {result.error}")
            continue
        configured = {str(m) for m in (meta.get("models") or [])}
        diff = diff_catalog(configured, result.live)
        status = "OK" if diff.clean else "DRIFT"
        print(f"[{name}] {status} — {result.count} live, {len(configured)} configured")
        for model in diff.gone:
            drift = True
            print(f"  GONE: {model}")
        if diff.matched:
            print(f"  matched ({len(diff.matched)}): " + ", ".join(diff.matched))
        if diff.live_only:
            print(f"  live-only new ({len(diff.live_only)}): " + ", ".join(diff.live_only))
    return 1 if drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
