"""Self-tests for WAVE-02's FakeLLMProvider and the keyless fixture.

These are the wave's primary deliverable: they prove the fake behaves
deterministically before any downstream wave relies on it.
"""

from __future__ import annotations

import time

import pytest

from tests.fakes.llm_provider import FakeLLMProvider


def test_transient_failures_fail_exactly_n_times_then_succeed():
    provider = FakeLLMProvider(transient_failures=2)

    with pytest.raises(Exception) as first:
        provider._create("model", [{"role": "user", "content": "hi"}])
    assert first.value.status_code == 429

    with pytest.raises(Exception) as second:
        provider._create("model", [{"role": "user", "content": "hi"}])
    assert second.value.status_code == 429

    content = provider._create("model", [{"role": "user", "content": "hi"}])
    assert content
    # A fourth call must also succeed.
    assert provider._create("model", [{"role": "user", "content": "hi"}])


def test_permanent_failure_always_fails():
    provider = FakeLLMProvider(permanent_failure=True)
    for _ in range(3):
        with pytest.raises(Exception) as exc_info:
            provider._create("model", [{"role": "user", "content": "hi"}])
        assert exc_info.value.status_code == 500


def test_permanent_failure_custom_status():
    provider = FakeLLMProvider(permanent_failure=True, permanent_failure_status=429)
    with pytest.raises(Exception) as exc_info:
        provider._create("model", [{"role": "user", "content": "hi"}])
    assert exc_info.value.status_code == 429


def test_delay_seconds_is_honored_bounded():
    provider = FakeLLMProvider(delay_seconds=0.05)
    start = time.monotonic()
    provider._create("model", [{"role": "user", "content": "hi"}])
    elapsed = time.monotonic() - start
    assert elapsed >= 0.045  # bounded assertion, not exact timing
    assert elapsed < 1.0


def test_canned_response_by_model():
    provider = FakeLLMProvider(responses={"groq/a": "answer-a"})
    content = provider._create("groq/a", [{"role": "user", "content": "hi"}])
    assert content == "answer-a"


def test_canned_response_by_user_substring_longest_match():
    provider = FakeLLMProvider(
        responses={
            "short": "SHORT",
            "a longer distinctive phrase": "LONG",
        }
    )
    content = provider._create(
        "model", [{"role": "user", "content": "x a longer distinctive phrase z"}]
    )
    assert content == "LONG"


def test_default_content_when_no_match():
    provider = FakeLLMProvider(default_content="fallback")
    assert provider._create("model", [{"role": "user", "content": "nope"}]) == "fallback"


def test_call_log_records_each_call():
    provider = FakeLLMProvider()
    provider._create("m1", [{"role": "user", "content": "a"}], temperature=0.5)
    provider._create("m2", [{"role": "user", "content": "b"}])
    assert len(provider.call_log) == 2
    model, messages, kwargs = provider.call_log[0]
    assert model == "m1"
    assert messages[0]["content"] == "a"
    assert kwargs["temperature"] == 0.5


@pytest.mark.asyncio
async def test_router_shape_through_chat_completions():
    """Mimics core.router._call_openai_compatible exactly."""
    provider = FakeLLMProvider(responses={"m": "hello world"})
    resp = provider.chat.completions.create(
        model="m",
        messages=[{"role": "user", "content": "hi"}],
    )
    assert resp.choices[0].message.content == "hello world"


def test_reset_restores_transient_state():
    provider = FakeLLMProvider(transient_failures=1)
    with pytest.raises(Exception):
        provider._create("m", [{"role": "user", "content": "hi"}])
    provider.reset()
    # Without reset this would now succeed on the second call; after reset it
    # must fail again first.
    with pytest.raises(Exception):
        provider._create("m", [{"role": "user", "content": "hi"}])