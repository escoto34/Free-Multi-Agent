"""
LLM client initialization for free-tier-friendly providers.

Architecture:
  - Most providers use the OpenAI Python SDK with a custom ``base_url``
    (OpenAI-compatible Chat Completions API).
  - Cohere uses the native ``cohere.ClientV2`` SDK (documents= grounding).
  - Provider metadata (base_url, env_key, models, limits) lives in
    ``config/model_router.yaml`` under ``providers:`` so new free APIs can be
    added without hardcoding Python factories for every vendor.

Supported out of the box (see model_router.yaml):
  groq, openrouter, cohere, mistral, gemini, cerebras, ollama, agnes

IMPORTANT:
  - Cohere ClientV2 does NOT support the ``connectors`` parameter (that was v1).
    Web search is handled externally (e.g. groq/compound-mini); grounding uses
    ``documents=[{"data": {"text": ...}}]`` on ``ClientV2.chat()``.
  - Ollama is local OpenAI-compatible (``http://localhost:11434/v1``); no real
    API key required. Override host with ``OLLAMA_BASE_URL`` / ``OLLAMA_HOST``.
  - Agnes AI is a free OpenAI-compatible multimodal gateway
    (``https://apihub.agnes-ai.com/v1``); use text chat model ``agnes-2.0-flash``.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional, Union

from dotenv import load_dotenv
from openai import OpenAI

import cohere

# Load .env file if present (no-op if already loaded or missing)
load_dotenv()

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "model_router.yaml"

# Type alias for any LLM client this module can return
LLMClient = Union[OpenAI, cohere.ClientV2]

# Providers that work without a real API key (dummy key is fine).
NO_KEY_PROVIDERS = frozenset({"ollama"})

# Built-in OpenAI-compatible endpoints (used if YAML omits base_url).
_DEFAULT_OPENAI_COMPAT: dict[str, dict[str, str]] = {
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
    # Google AI Studio — OpenAI-compatible surface for Gemini free tier
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "env_key": "GEMINI_API_KEY",
    },
    "cerebras": {
        "base_url": "https://api.cerebras.ai/v1",
        "env_key": "CEREBRAS_API_KEY",
    },
    # Local Ollama — OpenAI-compatible chat completions
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "env_key": "OLLAMA_API_KEY",
    },
    # Agnes AI free multimodal gateway — OpenAI-compatible
    "agnes": {
        "base_url": "https://apihub.agnes-ai.com/v1",
        "env_key": "AGNES_API_KEY",
    },
}


def _load_providers_yaml() -> dict[str, Any]:
    try:
        import yaml

        if _CONFIG_PATH.exists():
            data = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
            providers = data.get("providers") or {}
            if isinstance(providers, dict):
                return providers
    except Exception:
        pass
    return {}


def list_provider_names() -> list[str]:
    """All known provider aliases (YAML + builtins + cohere)."""
    names = set(_DEFAULT_OPENAI_COMPAT) | {"cohere"}
    names |= set(_load_providers_yaml().keys())
    return sorted(names)


def _normalize_openai_base_url(url: str) -> str:
    """Ensure OpenAI-compatible base URLs end with /v1 when appropriate."""
    u = (url or "").strip().rstrip("/")
    if not u:
        return u
    # OLLAMA_HOST is often http://host:11434 without /v1
    if u.endswith("/v1") or u.endswith("/openai") or "/v1beta" in u:
        return u if u.endswith("/") is False else u.rstrip("/")
    # bare host:port or host → append /v1
    return u + "/v1"


def _ollama_base_url(yaml_or_default: str) -> str:
    """Resolve Ollama base URL from env overrides then YAML/default."""
    for key in ("OLLAMA_BASE_URL", "OLLAMA_HOST"):
        raw = os.environ.get(key)
        if raw and str(raw).strip():
            return _normalize_openai_base_url(str(raw).strip())
    return yaml_or_default


def list_ollama_local_models(base_url: Optional[str] = None, *, timeout: float = 1.5) -> list[str]:
    """Query local Ollama ``/api/tags`` for installed model names (best-effort)."""
    base = (base_url or _ollama_base_url("http://localhost:11434/v1")).rstrip("/")
    # strip trailing /v1 for native Ollama API
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


def get_provider_meta(provider: str) -> dict[str, Any]:
    """Return base_url / env_key / limits / models for *provider*."""
    alias = provider.strip().lower()
    yaml_p = _load_providers_yaml().get(alias) or {}
    builtin = _DEFAULT_OPENAI_COMPAT.get(alias) or {}

    if alias == "cohere":
        return {
            "provider": alias,
            "kind": "cohere_v2",
            "env_key": yaml_p.get("env_key") or "COHERE_API_KEY",
            "base_url": None,
            "models": list(yaml_p.get("models") or []),
            "daily_limit": yaml_p.get("daily_limit"),
            "daily_limit_shared": yaml_p.get("daily_limit_shared"),
            "daily_limit_per_model": yaml_p.get("daily_limit_per_model"),
            "notes": yaml_p.get("notes")
            or "Trial / free tier often non-commercial; check Cohere ToS.",
            "signup": "https://dashboard.cohere.com/api-keys",
            "requires_key": True,
        }

    base_url = yaml_p.get("base_url") or builtin.get("base_url")
    env_key = yaml_p.get("env_key") or builtin.get("env_key")
    if not base_url or not env_key:
        raise ValueError(
            f"Unknown provider {provider!r}. "
            f"Add it under providers: in config/model_router.yaml "
            f"(base_url + env_key) or use one of: {list_provider_names()}"
        )

    if alias == "ollama":
        base_url = _ollama_base_url(str(base_url))
        # Only models actually installed (same source as `ollama list` /api/tags).
        # Never advertise YAML placeholders the user has not pulled.
        models = list_ollama_local_models(base_url)
        notes = yaml_p.get("notes") or (
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
            "provider": alias,
            "kind": "openai_compatible",
            "env_key": env_key,
            "base_url": base_url,
            "models": models,
            "daily_limit": yaml_p.get("daily_limit"),
            "daily_limit_shared": yaml_p.get("daily_limit_shared"),
            "daily_limit_per_model": yaml_p.get("daily_limit_per_model"),
            "notes": notes,
            "signup": yaml_p.get("signup") or "https://ollama.com/download",
            "requires_key": False,
            "models_source": "ollama list",
        }

    models = list(yaml_p.get("models") or [])

    return {
        "provider": alias,
        "kind": "openai_compatible",
        "env_key": env_key,
        "base_url": base_url,
        "models": models,
        "daily_limit": yaml_p.get("daily_limit"),
        "daily_limit_shared": yaml_p.get("daily_limit_shared"),
        "daily_limit_per_model": yaml_p.get("daily_limit_per_model"),
        "notes": yaml_p.get("notes") or "",
        "signup": yaml_p.get("signup") or "",
        "requires_key": alias not in NO_KEY_PROVIDERS,
    }


def _require_env(env_key: str, provider: str) -> str:
    alias = provider.strip().lower()
    api_key = os.environ.get(env_key)
    if api_key and str(api_key).strip() and "your_" not in str(api_key):
        return str(api_key).strip()
    # Local providers: OpenAI SDK still wants a non-empty api_key string.
    if alias in NO_KEY_PROVIDERS:
        return "ollama"
    raise ValueError(
        f"{env_key} is not set (needed for provider {provider!r}). "
        f"Set it with: multiagent keys set {provider}  "
        f"or add it to MultiAgent/.env"
    )


@lru_cache(maxsize=16)
def _openai_compat_client(provider: str, base_url: str, env_key: str) -> OpenAI:
    api_key = _require_env(env_key, provider)
    # Compound / tool-using models can take a while; never hang forever.
    # Connect timeout 20s; overall read/write up to 180s per request.
    timeout = float(os.environ.get("MULTIAGENT_HTTP_TIMEOUT", "180") or "180")
    kwargs: dict[str, Any] = {
        "api_key": api_key,
        "base_url": base_url,
        "timeout": timeout,
    }
    # OpenRouter asks for optional attribution headers (harmless if missing).
    if provider == "openrouter":
        kwargs["default_headers"] = {
            "HTTP-Referer": "https://github.com/local/MultiAgent",
            "X-Title": "Free-Multi-Agent",
        }
    return OpenAI(**kwargs)


@lru_cache(maxsize=1)
def get_cohere_client() -> cohere.ClientV2:
    """Initialize and cache the Cohere v2 client."""
    meta = get_provider_meta("cohere")
    api_key = _require_env(meta["env_key"], "cohere")
    return cohere.ClientV2(api_key=api_key)


# Back-compat aliases used by older tests / docs
def get_groq_client() -> OpenAI:
    meta = get_provider_meta("groq")
    return _openai_compat_client("groq", meta["base_url"], meta["env_key"])


def get_openrouter_client() -> OpenAI:
    meta = get_provider_meta("openrouter")
    return _openai_compat_client(
        "openrouter", meta["base_url"], meta["env_key"]
    )


def get_client(provider: str) -> LLMClient:
    """Return the cached client for *provider*."""
    alias = provider.strip().lower()
    if alias == "cohere":
        return get_cohere_client()
    meta = get_provider_meta(alias)
    return _openai_compat_client(alias, meta["base_url"], meta["env_key"])


def clear_client_cache() -> None:
    """Clear all cached clients. Mainly useful for testing / key rotation."""
    _openai_compat_client.cache_clear()
    get_cohere_client.cache_clear()
