"""
Root conftest — sets up fake API keys so that imports of core.clients
don't raise ValueError during test collection.

All tests must mock actual HTTP calls (respx for OpenAI-compat,
manual mocks for cohere.ClientV2) — zero real quota consumed.
"""

import os
import sys
from pathlib import Path

import pytest

# Ensure the project root is on sys.path for imports
_PROJECT_ROOT = Path(__file__).parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Inject fake API keys so client factories don't error during import.
# These are NEVER sent to any real endpoint — all HTTP is mocked in tests.
os.environ.setdefault("GROQ_API_KEY", "test-groq-key-fake")
os.environ.setdefault("OPENROUTER_API_KEY", "test-openrouter-key-fake")
os.environ.setdefault("COHERE_API_KEY", "test-cohere-key-fake")
os.environ.setdefault("MISTRAL_API_KEY", "test-mistral-key-fake")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key-fake")
os.environ.setdefault("CEREBRAS_API_KEY", "test-cerebras-key-fake")
os.environ.setdefault("OLLAMA_API_KEY", "ollama")
os.environ.setdefault("AGNES_API_KEY", "test-agnes-key-fake")


@pytest.fixture(autouse=True)
def _isolate_clients():
    """Clear cached LLM clients between tests to avoid cross-contamination."""
    from core.clients import clear_client_cache

    clear_client_cache()
    yield
    clear_client_cache()


@pytest.fixture()
def tmp_quota_db(tmp_path: Path):
    """Provide a temporary SQLite path for QuotaTracker in tests."""
    return tmp_path / "test_quotas.db"


@pytest.fixture()
def fake_llm_provider(monkeypatch):
    """WAVE-02: route every get_client() call through a FakeLLMProvider.

    Enables the factory-level test-mode flag (``MULTIAGENT_FAKE_PROVIDER``) that
    ``core.clients.get_client`` consults, so code paths that bind ``get_client``
    at import time (including the router) transparently get the fake without any
    per-call-site monkeypatching. The provider instance is returned so tests can
    configure canned responses / failure modes.
    """
    from tests.fakes.llm_provider import FakeLLMProvider
    from core.clients import fake_provider_override

    monkeypatch.setenv("MULTIAGENT_FAKE_PROVIDER", "1")
    provider = FakeLLMProvider()
    fake_provider_override.set(provider)
    try:
        yield provider
    finally:
        fake_provider_override.clear()
