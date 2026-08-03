"""
LLM client initialization for free-tier-friendly providers.

Architecture:
  - Most providers use the OpenAI Python SDK with a custom ``base_url``
    (OpenAI-compatible Chat Completions API).
  - Cohere uses the native ``cohere.ClientV2`` SDK (documents= grounding).
  - Provider metadata (base_url, env_key, models, limits) lives in
    ``config/model_router.yaml`` under ``providers:`` so new free APIs can be
    added without hardcoding Python factories for every vendor. The single
    source of truth is ``core/provider_registry`` (WAVE-06).

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

import os
from functools import lru_cache
from typing import Any, Optional, Union

from dotenv import load_dotenv
from openai import OpenAI

import cohere

from core.provider_registry import (
    NO_KEY_PROVIDERS,
    get_provider_meta,
    list_provider_names,
)

# Load .env file if present (no-op if already loaded or missing)
load_dotenv()

# Type alias for any LLM client this module can return
LLMClient = Union[OpenAI, cohere.ClientV2]


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


def _fake_provider() -> Optional[Any]:
    """Return a FakeLLMProvider when the test-mode flag is set, else None.

    Wired through this single factory so the router (which binds ``get_client``
    at import time) and every other call site transparently get the fake once
    ``MULTIAGENT_FAKE_PROVIDER=1`` is set. Kept behind the explicit flag so a
    real provider is never substituted in normal operation.
    """
    if os.environ.get("MULTIAGENT_FAKE_PROVIDER", "").strip().lower() not in {
        "1",
        "true",
        "yes",
    }:
        return None
    try:
        from tests.fakes.llm_provider import FakeLLMProvider

        return FakeLLMProvider()
    except Exception:
        return None


class _FakeProviderOverride:
    """Settable holder so tests can inject a specific FakeLLMProvider instance."""

    def __init__(self) -> None:
        self._value: Optional[Any] = None

    def set(self, provider: Any) -> None:
        self._value = provider

    def clear(self) -> None:
        self._value = None

    def get(self) -> Optional[Any]:
        return self._value


# Global holder for the fake provider (test injection / cached instance).
fake_provider_override = _FakeProviderOverride()


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
    if fake_provider_override.get() is not None:
        return fake_provider_override.get()
    if os.environ.get("MULTIAGENT_FAKE_PROVIDER", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        fake = _fake_provider()
        if fake is not None:
            return fake
    if alias == "cohere":
        return get_cohere_client()
    meta = get_provider_meta(alias)
    return _openai_compat_client(alias, meta["base_url"], meta["env_key"])


def clear_fake_provider() -> None:
    """Drop the cached fake provider instance."""
    fake_provider_override.clear()


def clear_client_cache() -> None:
    """Clear all cached clients. Mainly useful for testing / key rotation."""
    _openai_compat_client.cache_clear()
    get_cohere_client.cache_clear()
