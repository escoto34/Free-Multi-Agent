"""WAVE-02: fixtures resolve get_client through the fake without per-test patches.

These tests prove that the single ``core.clients.get_client`` factory seam
carries the ``FakeLLMProvider`` into the router transparently, so downstream
tests do not need to monkeypatch ``invoke_router`` / router internals per file.
"""

from __future__ import annotations

import pytest


def test_get_client_returns_the_fixture(fake_llm_provider):
    from core.clients import get_client

    assert get_client("groq") is fake_llm_provider
    assert get_client("openrouter") is fake_llm_provider
    assert get_client("cohere") is fake_llm_provider


def test_router_dispatches_through_fake_provider(fake_llm_provider, tmp_quota_db):
    """A real ModelRouter call must transparently use the fake, keyless."""
    from core.router import ModelRouter
    from core.quotas import QuotaTracker

    fake_llm_provider.responses["a"] = "hello from the fake"

    router = ModelRouter(quota_tracker=QuotaTracker(db_path=tmp_quota_db))
    result = router.call_agent(
        "groq",
        "a",
        [{"role": "user", "content": "hi"}],
        fallback=None,
        max_retries=1,
    )
    assert result.content == "hello from the fake"
    assert result.provider == "groq"
    assert result.model == "a"
    assert not result.used_fallback
    assert len(fake_llm_provider.call_log) == 1


def test_fake_transient_failures_drive_router_retry(fake_llm_provider, tmp_quota_db):
    """transient_failures=2 + max_retries=3 → succeeds on the third attempt."""
    from core.router import ModelRouter
    from core.quotas import QuotaTracker

    fake_llm_provider.transient_failures = 2
    fake_llm_provider._transient_remaining = 2
    fake_llm_provider.responses["a"] = "recovered"

    router = ModelRouter(quota_tracker=QuotaTracker(db_path=tmp_quota_db))
    result = router.call_agent(
        "groq",
        "a",
        [{"role": "user", "content": "hi"}],
        fallback={"provider": "groq", "model": "b"},
        max_retries=3,
        base_delay=0.001,
    )
    assert result.content == "recovered"
    assert not result.used_fallback
    assert len(fake_llm_provider.call_log) == 3