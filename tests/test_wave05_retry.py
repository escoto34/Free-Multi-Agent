"""WAVE-05 tests: per-class retry budgets, quota-body classifier, repair-once."""

import pytest
from pydantic import BaseModel

from core.agent_runtime import run_structured_agent
from core.call_outcome import CallOutcome, classify_http_status, retry_budget_for
from core.router import LLMResponse
from core.clients import clear_client_cache


class _FakeSchema(BaseModel):
    name: str
    count: int


# ---------------------------------------------------------------------------
# CallOutcome taxonomy / classifier
# ---------------------------------------------------------------------------

def test_quota_body_429_classified_as_quota_not_rate_limited():
    assert (
        classify_http_status(429, body="Daily quota exhausted") is CallOutcome.QUOTA_EXHAUSTED
    )
    assert classify_http_status(429, body="rate limit") is CallOutcome.RATE_LIMITED


def test_plain_rate_limit_and_transient():
    assert classify_http_status(429, body="") is CallOutcome.RATE_LIMITED
    assert classify_http_status(503, body="") is CallOutcome.NETWORK_TRANSIENT
    assert classify_http_status(422, body="invalid") is CallOutcome.QUALITY_REJECTED
    assert classify_http_status(404, body="") is CallOutcome.PROVIDER_ERROR


def test_retry_budgets_formalized():
    assert retry_budget_for(CallOutcome.NETWORK_TRANSIENT) == 2
    assert retry_budget_for(CallOutcome.SCHEMA_INVALID) == 1
    assert retry_budget_for(CallOutcome.QUALITY_REJECTED) == 1
    assert retry_budget_for(CallOutcome.QUOTA_EXHAUSTED) == 0


# ---------------------------------------------------------------------------
# Repair-once in run_structured_agent
# ---------------------------------------------------------------------------

def test_repair_once_succeeds_on_schema_invalid_then_valid(monkeypatch):
    calls = []

    def mock_router(provider, model, messages, **kwargs):
        call_index = len(calls)
        calls.append((provider, model, len(messages)))
        if call_index == 0:
            return LLMResponse(
                content='{"name": "x", "count": "not-an-int"}',
                provider=provider,
                model=model,
            )
        return LLMResponse(
            content='{"name": "x", "count": 1}',
            provider=provider,
            model=model,
        )

    result = run_structured_agent(
        "vibe_coding",
        "architect",
        messages=[{"role": "user", "content": "Build X"}],
        schema=_FakeSchema,
        router_instance=mock_router,
        skip_difficulty_selection=True,
    )
    assert result.count == 1
    assert len(calls) == 2  # original + exactly one repair
    assert calls[1][2] == 2  # repair message appended (1 original + 1 repair)


def test_repair_does_not_retry_twice(monkeypatch):
    calls = []

    def mock_router(provider, model, messages, **kwargs):
        calls.append(len(messages))
        return LLMResponse(
            content='{"name": "x"}',  # missing required field 'count'
            provider=provider,
            model=model,
        )

    with pytest.raises(Exception):
        run_structured_agent(
            "vibe_coding",
            "architect",
            messages=[{"role": "user", "content": "Build X"}],
            schema=_FakeSchema,
            router_instance=mock_router,
            skip_difficulty_selection=True,
        )
    assert len(calls) == 2  # only a single repair pass, never a third call


@pytest.fixture(autouse=True)
def _clean_clients():
    clear_client_cache()
    yield
    clear_client_cache()