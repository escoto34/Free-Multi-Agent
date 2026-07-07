"""
Tests for ModelRouter, QuotaTracker, and fallback cascade.
These tests mock HTTP calls entirely using respx or manual mock client patching,
ensuring zero external calls are made.
"""

import pytest
import respx
from httpx import Response, HTTPStatusError, Request

from core.router import ModelRouter, QuotaExhaustedError, LLMResponse
from core.quotas import QuotaTracker
from core.clients import clear_client_cache


@pytest.fixture()
def custom_tracker(tmp_quota_db):
    """Provide an isolated QuotaTracker using a temp database."""
    return QuotaTracker(db_path=tmp_quota_db)


@pytest.fixture()
def router_with_tracker(custom_tracker):
    """Provide a ModelRouter bound to the isolated QuotaTracker."""
    return ModelRouter(quota_tracker=custom_tracker)


# ---------------------------------------------------------------------------
# Quota Tracker Tests
# ---------------------------------------------------------------------------

def test_quota_tracker_limits_and_reset(custom_tracker):
    # Initial status
    assert custom_tracker.can_call("groq", "openai/gpt-oss-120b") is True
    assert custom_tracker.get_usage("groq", "openai/gpt-oss-120b") == 0
    assert custom_tracker.remaining("groq", "openai/gpt-oss-120b") == 800

    # Record calls
    custom_tracker.record_call("groq", "openai/gpt-oss-120b")
    assert custom_tracker.get_usage("groq", "openai/gpt-oss-120b") == 1
    assert custom_tracker.remaining("groq", "openai/gpt-oss-120b") == 799

    # OpenRouter has shared daily limit
    assert custom_tracker.can_call("openrouter", "tencent/hy3:free") is True
    custom_tracker.record_call("openrouter", "tencent/hy3:free")
    # Shared usage should reflect on another openrouter model
    assert custom_tracker.get_usage("openrouter", "cohere/north-mini-code:free") == 1
    assert custom_tracker.remaining("openrouter", "cohere/north-mini-code:free") == 44

    # Cohere has shared daily limit
    assert custom_tracker.can_call("cohere", "command-a-plus-05-2026") is True
    custom_tracker.record_call("cohere", "command-a-plus-05-2026")
    assert custom_tracker.get_usage("cohere", "command-a-plus-05-2026") == 1
    assert custom_tracker.remaining("cohere", "command-a-plus-05-2026") == 27

    # Reset
    custom_tracker.reset()
    assert custom_tracker.get_usage("groq", "openai/gpt-oss-120b") == 0
    assert custom_tracker.get_usage("openrouter", "tencent/hy3:free") == 0


def test_quota_tracker_exhaustion(custom_tracker):
    # artifically exhaust cohere (limit is 28)
    for _ in range(28):
        custom_tracker.record_call("cohere", "command-a-plus-05-2026")

    assert custom_tracker.can_call("cohere", "command-a-plus-05-2026") is False
    assert custom_tracker.remaining("cohere", "command-a-plus-05-2026") == 0


# ---------------------------------------------------------------------------
# Router Fallback & Dispatch Tests
# ---------------------------------------------------------------------------

@respx.mock
def test_router_success_openai_compatible(router_with_tracker):
    # Mock Groq endpoint
    route = respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "Hello from Groq Mock", "role": "assistant"}}
                ]
            }
        )
    )

    resp = router_with_tracker.call_agent(
        provider="groq",
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": "Hi"}],
    )

    assert resp.content == "Hello from Groq Mock"
    assert resp.provider == "groq"
    assert resp.model == "openai/gpt-oss-120b"
    assert resp.used_fallback is False
    assert route.called


@respx.mock
def test_router_fallback_on_http_error(router_with_tracker, monkeypatch):
    # 1. Groq request fails with 429
    groq_route = respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=Response(429, content="Rate Limit")
    )

    # 2. OpenRouter fallback succeeds
    or_route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "Hello from OpenRouter Fallback", "role": "assistant"}}
                ]
            }
        )
    )

    # Let's perform a call to groq
    # General cascade for groq should fall back to OpenRouter (cohere/north-mini-code:free)
    resp = router_with_tracker.call_agent(
        provider="groq",
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": "Hi"}],
        max_retries=1,  # Speed up test
    )

    assert resp.content == "Hello from OpenRouter Fallback"
    assert resp.provider == "openrouter"
    assert resp.model == "cohere/north-mini-code:free"
    assert resp.used_fallback is True
    assert "Rate Limit" in resp.fallback_reason or "retries exhausted" in resp.fallback_reason
    assert groq_route.called
    assert or_route.called


def test_router_fallback_on_quota_gate(router_with_tracker, monkeypatch):
    # Exhaust Cohere quota directly in tracker
    tracker = router_with_tracker.quota
    for _ in range(28):
        tracker.record_call("cohere", "command-a-plus-05-2026")

    # Mock OpenRouter (Cohere's fallback)
    with respx.mock:
        or_route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
            return_value=Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": "Fallback output", "role": "assistant"}}
                    ]
                }
            )
        )

        # Call cohere — it should immediately skip cohere due to quota gate
        # and request the fallback on OpenRouter
        resp = router_with_tracker.call_agent(
            provider="cohere",
            model="command-a-plus-05-2026",
            messages=[{"role": "user", "content": "Hi"}],
        )

        assert resp.content == "Fallback output"
        assert resp.provider == "openrouter"
        assert resp.model == "tencent/hy3:free"
        assert resp.used_fallback is True
        assert "Quota exhausted" in resp.fallback_reason
        assert or_route.called


@respx.mock
def test_router_cycle_detection(router_with_tracker):
    # Force a loop: Groq fallback configured to go to Groq
    # We can inject a custom cascade to simulate a loop
    router_with_tracker._config["fallback_cascade"]["groq_fallback"] = {
        "provider": "groq",
        "model": "openai/gpt-oss-120b",
    }

    # Make Groq post return 429 so it tries to fallback
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=Response(429, content="Rate Limit")
    )

    with pytest.raises(QuotaExhaustedError) as exc_info:
        router_with_tracker.call_agent(
            provider="groq",
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": "Hi"}],
            max_retries=1,
        )

    assert "Cycle detected" in str(exc_info.value)


@respx.mock
def test_cohere_v2_call_mocked(router_with_tracker, monkeypatch):
    """Test cohere routing through ClientV2 mock/interceptor."""
    # We can patch get_client("cohere") or mock Cohere V2 chat call
    # Since ClientV2 uses standard requests or httpx under the hood,
    # let's look at what cohere SDK v2 uses. In 5.x+, cohere uses httpx.
    # We can mock the cohere API endpoint using respx.
    # The Cohere V2 API path for chat is POST https://api.cohere.com/v2/chat or https://api.cohere.ai/v2/chat
    cohere_route = respx.post("https://api.cohere.com/v2/chat").mock(
        return_value=Response(
            200,
            json={
                "message": {
                    "content": [{"type": "text", "text": "Hello from Cohere V2 Mock"}]
                }
            }
        )
    )

    resp = router_with_tracker.call_agent(
        provider="cohere",
        model="command-a-plus-05-2026",
        messages=[{"role": "user", "content": "Hello"}],
    )

    assert resp.content == "Hello from Cohere V2 Mock"
    assert resp.provider == "cohere"
    assert resp.model == "command-a-plus-05-2026"
    assert cohere_route.called


def test_openrouter_shared_quota_across_models(custom_tracker):
    """Verify that OpenRouter uses a single SHARED counter for all :free models.

    Consuming 40 calls via north-mini-code should leave only 5 for hy3
    (total shared limit = 45).  This is the critical distinction vs Groq,
    where each model has its own independent 800-call budget.
    """
    model_a = "cohere/north-mini-code:free"
    model_b = "tencent/hy3:free"

    # Precondition: both models start at full quota (45 shared)
    assert custom_tracker.remaining("openrouter", model_a) == 45
    assert custom_tracker.remaining("openrouter", model_b) == 45

    # Consume 40 calls via model_a
    for _ in range(40):
        custom_tracker.record_call("openrouter", model_a)

    # model_a sees 5 remaining
    assert custom_tracker.remaining("openrouter", model_a) == 5
    # model_b ALSO sees 5 remaining — they share the counter
    assert custom_tracker.remaining("openrouter", model_b) == 5
    assert custom_tracker.get_usage("openrouter", model_b) == 40  # shared usage

    # Consume the remaining 5 via model_b
    for _ in range(5):
        custom_tracker.record_call("openrouter", model_b)

    # Both models are now exhausted
    assert custom_tracker.can_call("openrouter", model_a) is False
    assert custom_tracker.can_call("openrouter", model_b) is False
    assert custom_tracker.remaining("openrouter", model_a) == 0
    assert custom_tracker.remaining("openrouter", model_b) == 0

    # Contrast with Groq: independent counters
    assert custom_tracker.remaining("groq", "openai/gpt-oss-120b") == 800
    assert custom_tracker.remaining("groq", "openai/gpt-oss-safeguard-20b") == 800


def test_quota_isolation_between_providers(custom_tracker):
    """Verify that OpenRouter and Cohere quotas are isolated from each other.

    OpenRouter returning "__shared__" and Cohere returning "__shared__" should not
    bleed because queries utilize the `provider` field as part of the primary key.
    """
    openrouter_model = "tencent/hy3:free"
    cohere_model = "command-r-plus-08-2024"

    # 1. Reset counters to guarantee baseline
    custom_tracker.reset()

    # Verify initial state
    assert custom_tracker.remaining("openrouter", openrouter_model) == 45
    assert custom_tracker.remaining("cohere", cohere_model) == 28

    # 2. Consume 40 calls on OpenRouter
    for _ in range(40):
        custom_tracker.record_call("openrouter", openrouter_model)

    # 3. OpenRouter should have decreased, Cohere MUST remain at 28
    assert custom_tracker.remaining("openrouter", openrouter_model) == 5
    assert custom_tracker.remaining("cohere", cohere_model) == 28
    assert custom_tracker.get_usage("cohere", cohere_model) == 0

    # 4. Consume 10 calls on Cohere
    for _ in range(10):
        custom_tracker.record_call("cohere", cohere_model)

    # 5. Cohere should have decreased, OpenRouter must remain at 5
    assert custom_tracker.remaining("cohere", cohere_model) == 18
    assert custom_tracker.remaining("openrouter", openrouter_model) == 5
    assert custom_tracker.get_usage("openrouter", openrouter_model) == 40


def test_grounding_empty_search_validation():
    """Verify that run_grounding raises a ValueError if search_results is empty/whitespace."""
    from agents.deep_research.grounding import run_grounding
    import pytest

    with pytest.raises(ValueError) as exc:
        run_grounding("Quantum Computers", "")
    assert "Los resultados de búsqueda web están vacíos" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        run_grounding("Quantum Computers", "    \n   ")
    assert "Los resultados de búsqueda web están vacíos" in str(exc.value)


def test_grounding_defensive_retry_on_json_error():
    """Verify that run_grounding retries once if first response contains invalid/truncated JSON."""
    from agents.deep_research.grounding import run_grounding
    from core.router import LLMResponse

    call_count = 0

    def mock_router(provider, model, messages, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call returns truncated JSON
            return LLMResponse(
                content='{"content": "Truncated report...',
                provider=provider,
                model=model,
            )
        else:
            # Second call (retry) returns valid JSON
            return LLMResponse(
                content='{"content": "Full valid report", "sources": ["http://quantum.org"]}',
                provider=provider,
                model=model,
            )

    result = run_grounding("Quantum Computers", "Search info here", router_instance=mock_router)
    assert call_count == 2  # Proves the retry was executed
    assert result.content == "Full valid report"
    assert result.sources == ["http://quantum.org"]


@respx.mock
def test_cohere_v2_thinking_blocks_handled(router_with_tracker):
    """Cohere command-a-plus may return 'thinking' content blocks before 'text' blocks.

    Regression test: the router must skip ThinkingAssistantMessageResponseContentItem
    (which has .thinking but NOT .text) and find the TextAssistantMessageResponseContentItem.
    """
    cohere_route = respx.post("https://api.cohere.com/v2/chat").mock(
        return_value=Response(
            200,
            json={
                "message": {
                    "content": [
                        {"type": "thinking", "thinking": "Let me think about this..."},
                        {"type": "text", "text": "Here is the actual answer."},
                    ]
                }
            }
        )
    )

    resp = router_with_tracker.call_agent(
        provider="cohere",
        model="command-a-plus-05-2026",
        messages=[{"role": "user", "content": "Hello"}],
    )

    assert resp.content == "Here is the actual answer."
    assert resp.provider == "cohere"
    assert cohere_route.called


def test_grounding_hard_barrier_against_no_search():
    """Verify that run_grounding raises a ValueError with the correct warning message

    if search_results contains any self-declared non-live search phrases.
    """
    from agents.deep_research.grounding import run_grounding
    import pytest

    bad_search_results = (
        "Some details from my memory. Note: no live web-search was performed on this query."
    )

    with pytest.raises(ValueError) as exc:
        run_grounding("Quantum physics updates", bad_search_results)

    assert "El paso de búsqueda no devolvió resultados verificados en vivo" in str(exc.value)


def test_synthesizer_cross_reference_citations():
    """Verify that run_synthesizer marks citations not found in raw search results."""
    from agents.deep_research.synthesizer import run_synthesizer
    from schemas.deep_research import GroundedReport
    from core.router import LLMResponse

    raw_report = GroundedReport(
        content="NASA did a case study on Shuttle flight software. See http://nasa.gov/shuttle.",
        sources=["http://nasa.gov/shuttle", "http://unverified-source.com"]
    )

    # Mock router to return same content & sources
    def mock_router(provider, model, messages, **kwargs):
        return LLMResponse(
            content='{"content": "NASA did a case study on Shuttle flight software. See http://nasa.gov/shuttle and http://unverified-source.com.", "sources": ["http://nasa.gov/shuttle", "http://unverified-source.com"]}',
            provider=provider,
            model=model,
        )

    # Raw search results only contain the NASA URL
    raw_search = "NASA Shuttle software report is found at http://nasa.gov/shuttle in detail."

    final_report = run_synthesizer(raw_report, search_results=raw_search, router_instance=mock_router)

    # http://nasa.gov/shuttle should NOT be marked (it was in raw search results)
    # http://unverified-source.com MUST be marked with warning
    assert "http://nasa.gov/shuttle" in final_report.content
    assert "http://nasa.gov/shuttle (⚠️" not in final_report.content
    assert "http://unverified-source.com (⚠️ fuente no verificada en esta ejecución — revisar manualmente)" in final_report.content

