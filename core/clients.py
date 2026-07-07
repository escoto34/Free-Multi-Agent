"""
LLM client initialization for Groq, OpenRouter, and Cohere.

Architecture:
  - Groq and OpenRouter use the OpenAI Python SDK with custom base_url
    (they expose OpenAI-compatible endpoints).
  - Cohere uses the native ``cohere.ClientV2`` SDK.
  - All API keys are loaded from environment variables (never hardcoded).

IMPORTANT:
  - Cohere ClientV2 does NOT support the ``connectors`` parameter (that was v1).
    Web search is handled externally via groq/compound-mini; grounding uses the
    ``documents`` parameter on ``ClientV2.chat()``.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Union

from dotenv import load_dotenv
from openai import OpenAI

import cohere

# Load .env file if present (no-op if already loaded or missing)
load_dotenv()

# ---------------------------------------------------------------------------
# Type alias for any LLM client this module can return
# ---------------------------------------------------------------------------
LLMClient = Union[OpenAI, cohere.ClientV2]


# ---------------------------------------------------------------------------
# Cached client factories — one instance per provider for the process lifetime
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_groq_client() -> OpenAI:
    """Initialize and cache the Groq client (OpenAI-compatible).

    Requires ``GROQ_API_KEY`` in the environment.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY environment variable is not set. "
            "Copy .env.example → .env and fill in your Groq API key."
        )
    return OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
    )


@lru_cache(maxsize=1)
def get_openrouter_client() -> OpenAI:
    """Initialize and cache the OpenRouter client (OpenAI-compatible).

    Requires ``OPENROUTER_API_KEY`` in the environment.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENROUTER_API_KEY environment variable is not set. "
            "Copy .env.example → .env and fill in your OpenRouter API key."
        )
    return OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )


@lru_cache(maxsize=1)
def get_cohere_client() -> cohere.ClientV2:
    """Initialize and cache the Cohere v2 client.

    Requires ``COHERE_API_KEY`` in the environment.

    IMPORTANT: This client is ``cohere.ClientV2``.  It does **not** support
    the ``connectors`` parameter that existed in v1.  Web search is performed
    by ``groq/compound-mini`` (Tavily-integrated); grounding/citations use
    ``documents=[{"data": {"text": ...}}]`` on ``ClientV2.chat()``.
    """
    api_key = os.environ.get("COHERE_API_KEY")
    if not api_key:
        raise ValueError(
            "COHERE_API_KEY environment variable is not set. "
            "Copy .env.example → .env and fill in your Cohere API key."
        )
    return cohere.ClientV2(api_key=api_key)


# ---------------------------------------------------------------------------
# Convenience dispatcher
# ---------------------------------------------------------------------------

_FACTORIES: dict[str, callable] = {
    "groq": get_groq_client,
    "openrouter": get_openrouter_client,
    "cohere": get_cohere_client,
}


def get_client(provider: str) -> LLMClient:
    """Return the cached client for *provider*.

    Args:
        provider: One of ``"groq"``, ``"openrouter"``, ``"cohere"``.

    Raises:
        ValueError: If the provider name is not recognised.
    """
    factory = _FACTORIES.get(provider)
    if factory is None:
        raise ValueError(
            f"Unknown provider: {provider!r}. "
            f"Valid providers: {sorted(_FACTORIES)}"
        )
    return factory()


def clear_client_cache() -> None:
    """Clear all cached clients.  Mainly useful for testing."""
    get_groq_client.cache_clear()
    get_openrouter_client.cache_clear()
    get_cohere_client.cache_clear()
