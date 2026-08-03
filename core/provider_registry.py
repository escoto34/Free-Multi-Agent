"""
Single source of truth for the provider catalog (WAVE-06).

Collapses the three parallel provider lists that previously lived in:

* ``core/clients.py`` ``_DEFAULT_OPENAI_COMPAT``
* ``core/config_editor.py`` ``KNOWN_PROVIDERS``
* ``core/quotas.py`` ``_YAML_LIMIT_KEY`` + ``_PER_MODEL_PROVIDERS``

The canonical layer is ``config/model_router.yaml``'s ``providers:`` block —
the same file ``get_provider_meta()`` already treated as the override layer.
The builtin defaults table below exists only as a *fallback* when YAML omits
``base_url``/``env_key``; YAML always wins for overlapping fields.

Modules that need provider facts should import from here instead of keeping
parallel lists::

    from core.provider_registry import (
        get_registered_providers,
        get_provider_meta,
        list_provider_names,
        all_registered_models,
        provider_limit_key,
        is_per_model_provider,
    )
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path
from typing import Any

import yaml

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "model_router.yaml"

# Builtin OpenAI-compatible endpoints (used only if YAML omits base_url).
# Cohere is the sole native-SDK provider and needs no base_url.
_DEFAULT_OPENAI_COMPAT: dict[str, dict[str, Any]] = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "env_key": "GROQ_API_KEY",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "env_key": "OPENROUTER_API_KEY",
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "env_key": "MISTRAL_API_KEY",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "env_key": "GEMINI_API_KEY",
    },
    "cerebras": {
        "base_url": "https://api.cerebras.ai/v1",
        "env_key": "CEREBRAS_API_KEY",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "env_key": "OLLAMA_API_KEY",
    },
    "agnes": {
        "base_url": "https://apihub.agnes-ai.com/v1",
        "env_key": "AGNES_API_KEY",
    },
}


def _load_providers_yaml() -> dict[str, Any]:
    try:
        if _CONFIG_PATH.exists():
            data = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
            providers = data.get("providers") or {}
            if isinstance(providers, dict):
                return providers
    except Exception:
        pass
    return {}


def get_registered_providers() -> dict[str, dict[str, Any]]:
    """Return the merged provider catalog: builtin defaults + YAML overrides.

    YAML wins on overlapping fields (matches the historical
    ``get_provider_meta()`` merge order). Cohere is included via its YAML
    block; the builtin table does not need a cohere row because its native
    ``cohere.ClientV2`` factory does not use ``base_url``.
    """
    yaml_providers = _load_providers_yaml()
    names = set(_DEFAULT_OPENAI_COMPAT) | set(yaml_providers)
    merged: dict[str, dict[str, Any]] = {}
    for name in sorted(names):
        entry: dict[str, Any] = {}
        entry.update(_DEFAULT_OPENAI_COMPAT.get(name) or {})
        entry.update(yaml_providers.get(name) or {})
        merged[name] = entry
    return merged


def list_provider_names() -> list[str]:
    """All known provider aliases (YAML + builtin defaults)."""
    return list(get_registered_providers().keys())


def all_registered_models() -> list[tuple[str, str]]:
    """Return every ``(provider, model)`` declared in the catalog."""
    out: list[tuple[str, str]] = []
    for provider, meta in get_registered_providers().items():
        for model in meta.get("models") or []:
            out.append((provider, str(model)))
    return out


def get_provider_meta(provider: str) -> dict[str, Any]:
    """Full merged metadata for a single provider (throws on unknown)."""
    alias = provider.strip().lower()
    meta = get_registered_providers().get(alias)
    if meta is None:
        raise ValueError(
            f"Unknown provider {provider!r}. Registered: {list_provider_names()}"
        )

    if alias == "cohere":
        return {
            "provider": alias,
            "kind": "cohere_v2",
            "env_key": meta.get("env_key") or "COHERE_API_KEY",
            "base_url": None,
            "models": list(meta.get("models") or []),
            "daily_limit": meta.get("daily_limit"),
            "daily_limit_shared": meta.get("daily_limit_shared"),
            "daily_limit_per_model": meta.get("daily_limit_per_model"),
            "notes": meta.get("notes"),
            "signup": meta.get("signup"),
            "requires_key": True,
        }

    if not meta.get("base_url") or not meta.get("env_key"):
        raise ValueError(
            f"Provider {provider!r} has no base_url/env_key. "
            f"Add them under providers: in config/model_router.yaml"
        )

    if alias == "ollama":
        return _ollama_meta(meta)

    return {
        "provider": alias,
        "kind": "openai_compatible",
        "env_key": meta.get("env_key"),
        "base_url": meta.get("base_url"),
        "models": list(meta.get("models") or []),
        "daily_limit": meta.get("daily_limit"),
        "daily_limit_shared": meta.get("daily_limit_shared"),
        "daily_limit_per_model": meta.get("daily_limit_per_model"),
        "notes": meta.get("notes") or "",
        "signup": meta.get("signup") or "",
        "requires_key": alias not in NO_KEY_PROVIDERS,
    }


def _normalize_openai_base_url(url: str) -> str:
    u = (url or "").strip().rstrip("/")
    if not u:
        return u
    if u.endswith("/v1") or u.endswith("/openai") or "/v1beta" in u:
        return u if u.endswith("/") is False else u.rstrip("/")
    return u + "/v1"


def _ollama_base_url(yaml_or_default: str) -> str:
    for key in ("OLLAMA_BASE_URL", "OLLAMA_HOST"):
        raw = os.environ.get(key)
        if raw and str(raw).strip():
            return _normalize_openai_base_url(str(raw).strip())
    return yaml_or_default


def list_ollama_local_models(base_url: str | None = None, *, timeout: float = 1.5) -> list[str]:
    """Query local Ollama ``/api/tags`` for installed model names (best-effort)."""
    base = (base_url or _ollama_base_url("http://localhost:11434/v1")).rstrip("/")
    root = base[:-3] if base.endswith("/v1") else base
    tags_url = root.rstrip("/") + "/api/tags"
    try:
        req = urllib.request.Request(
            tags_url,
            headers={"User-Agent": "Free-Multi-Agent/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        models = data.get("models") or []
        names: list[str] = []
        for m in models:
            if isinstance(m, dict):
                n = m.get("name") or m.get("model")
                if n:
                    names.append(str(n))
            elif isinstance(m, str):
                names.append(m)
        return names
    except Exception:
        return []


def provider_limit_key(provider: str) -> str | None:
    """Return which limit key a provider declares (daily_limit_* variants)."""
    meta = get_registered_providers().get(provider.strip().lower())
    if not meta:
        return None
    for key in ("daily_limit", "daily_limit_shared", "daily_limit_per_model"):
        if key in meta:
            return key
    return None


def is_per_model_provider(provider: str) -> bool:
    """True when the provider tracks quota per model (e.g. groq)."""
    return provider_limit_key(provider) == "daily_limit_per_model"


# Providers that work without a real API key (dummy key is fine).
NO_KEY_PROVIDERS = frozenset({"ollama"})


def _ollama_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """Ollama meta: env overrides for host + models from the live daemon."""
    base_url = _ollama_base_url(str(meta.get("base_url") or "http://localhost:11434/v1"))
    models = list_ollama_local_models(base_url)
    notes = meta.get("notes") or (
        "Local OpenAI-compatible server. Models = output of `ollama list` only. "
        "Pull with: ollama pull <name>. Override host: OLLAMA_BASE_URL / OLLAMA_HOST."
    )
    if not models:
        notes = (
            notes
            + " No models detected — is `ollama serve` running? "
            "Try: ollama list && ollama pull llama3.2"
        )
    return {
        "provider": "ollama",
        "kind": "openai_compatible",
        "env_key": meta.get("env_key") or "OLLAMA_API_KEY",
        "base_url": base_url,
        "models": models,
        "daily_limit": meta.get("daily_limit"),
        "daily_limit_shared": meta.get("daily_limit_shared"),
        "daily_limit_per_model": meta.get("daily_limit_per_model"),
        "notes": notes,
        "signup": meta.get("signup") or "https://ollama.com/download",
        "requires_key": False,
        "models_source": "ollama list",
    }