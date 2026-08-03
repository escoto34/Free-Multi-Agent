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
# Derived from the single provider registry so a new provider added to
# config/model_router.yaml automatically gets a fake key here (WAVE-06).
from core.provider_registry import NO_KEY_PROVIDERS, get_registered_providers

for _name, _meta in get_registered_providers().items():
    _env_key = _meta.get("env_key")
    if not _env_key:
        continue
    if _name in NO_KEY_PROVIDERS:
        os.environ.setdefault(_env_key, "ollama")
    else:
        os.environ.setdefault(_env_key, f"test-{_name}-key-fake")


@pytest.fixture(autouse=True)
def _isolate_clients():
    """Clear cached LLM clients between tests to avoid cross-contamination."""
    from core.clients import clear_client_cache

    clear_client_cache()
    _clear_http_cache()
    yield
    clear_client_cache()
    _clear_http_cache()


def _clear_http_cache() -> None:
    """Drop the process-wide HTTP cache between tests (WAVE-09B)."""
    try:
        from core.http_cache import get_default_cache

        get_default_cache().clear()
    except Exception:
        pass


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
