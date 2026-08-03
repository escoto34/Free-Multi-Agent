"""
WAVE-07: quota ledger — reserve-before-call with confirm/refund by row id.

The router now creates a reservation *before* an LLM call goes out on the
wire and resolves it afterwards based on the WAVE-05 CallOutcome:

* provider reached (success, HTTP error, empty HTTP-200 completion) -> confirmed
* provider never reached (no HTTP response at all)                  -> refunded

These tests pin the ledger semantics: pending reservations already eat into
the bucket, transitions are one-way from RESERVED, the refund/confirm is
addressed by row id (so a day rollover between reservation and resolution
attributes the call to the day it was reserved), and concurrent callers can
never over-commit past a provider's limit.
"""

import sqlite3
import threading

import pytest

from core.quotas import QuotaTracker, ReserveState
from core.router import EmptyCompletionError, ModelRouter, QuotaExhaustedError


@pytest.fixture()
def tracker(tmp_quota_db):
    return QuotaTracker(db_path=tmp_quota_db)


@pytest.fixture()
def router(tracker):
    return ModelRouter(quota_tracker=tracker)


def _row_states(db_path, provider, usage_date):
    """Return {(id, state)} for a provider's reservations on a given day."""
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT id, state FROM quota_reservations "
            "WHERE provider = ? AND usage_date = ?",
            (provider, usage_date),
        ).fetchall()
    return dict(rows)


def _legacy_count(db_path, provider, model):
    key = QuotaTracker._quota_key(provider, model)
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT call_count FROM quota_usage "
            "WHERE provider = ? AND quota_key = ? AND usage_date = ?",
            (provider, key, QuotaTracker._today()),
        ).fetchone()
    return row[0] if row else 0


# ---------------------------------------------------------------------------
# Ledger semantics
# ---------------------------------------------------------------------------


def test_pending_reservation_eats_into_bucket(tracker):
    row_id = tracker.reserve("groq", "openai/gpt-oss-120b")
    assert row_id > 0
    assert tracker.get_usage("groq", "openai/gpt-oss-120b") == 1
    assert tracker.remaining("groq", "openai/gpt-oss-120b") == 799
    assert tracker.can_call("groq", "openai/gpt-oss-120b") is True


def test_confirm_keeps_usage_and_is_guarded(tracker, tmp_quota_db):
    row_id = tracker.reserve("cohere", "command-a-plus-05-2026")
    tracker.confirm(row_id)
    assert tracker.get_usage("cohere", "command-a-plus-05-2026") == 1
    # Double confirm is a no-op guard, not an error or a double count.
    tracker.confirm(row_id)
    tracker.confirm(row_id)
    assert tracker.get_usage("cohere", "command-a-plus-05-2026") == 1
    states = _row_states(tmp_quota_db, "cohere", QuotaTracker._today())
    assert list(states.values()) == [ReserveState.CONFIRMED]


def test_refund_releases_bucket_and_is_auditable(tracker, tmp_quota_db):
    row_id = tracker.reserve("openrouter", "cohere/north-mini-code:free")
    assert tracker.remaining("openrouter", "cohere/north-mini-code:free") == 44
    tracker.refund(row_id)
    assert tracker.get_usage("openrouter", "cohere/north-mini-code:free") == 0
    assert tracker.remaining("openrouter", "cohere/north-mini-code:free") == 45
    # The refunded row stays in the ledger for auditability.
    states = _row_states(tmp_quota_db, "openrouter", QuotaTracker._today())
    assert list(states.values()) == [ReserveState.REFUNDED]


def test_refund_after_confirm_is_noop(tracker):
    row_id = tracker.reserve("cohere", "command-a-plus-05-2026")
    tracker.confirm(row_id)
    tracker.refund(row_id)  # must NOT roll the confirmed call back
    assert tracker.get_usage("cohere", "command-a-plus-05-2026") == 1


def test_mixed_confirm_and_refund_sum_correctly(tracker):
    kept = tracker.reserve("groq", "openai/gpt-oss-120b")
    dropped = tracker.reserve("groq", "openai/gpt-oss-120b")
    tracker.confirm(kept)
    tracker.refund(dropped)
    assert tracker.get_usage("groq", "openai/gpt-oss-120b") == 1


def test_shared_bucket_reservations_are_per_key(tracker):
    a = tracker.reserve("openrouter", "cohere/north-mini-code:free")
    b = tracker.reserve("openrouter", "tencent/hy3:free")
    assert tracker.get_usage("openrouter", "cohere/north-mini-code:free") == 2
    assert tracker.get_usage("openrouter", "tencent/hy3:free") == 2
    tracker.refund(a)
    assert tracker.get_usage("openrouter", "tencent/hy3:free") == 1
    tracker.confirm(b)
    assert tracker.get_usage("openrouter", "tencent/hy3:free") == 1


# ---------------------------------------------------------------------------
# Day boundary: reservation day is the attribution day
# ---------------------------------------------------------------------------


def test_day_boundary_resolution_keeps_reservation_day(tracker, tmp_quota_db, monkeypatch):
    monkeypatch.setattr(
        QuotaTracker, "_today", staticmethod(lambda: "2026-08-03")
    )
    row_id = tracker.reserve("cohere", "command-a-plus-05-2026")
    assert tracker.get_usage("cohere", "command-a-plus-05-2026") == 1

    # Midnight rolls over while the call is still in flight.
    monkeypatch.setattr(
        QuotaTracker, "_today", staticmethod(lambda: "2026-08-04")
    )
    tracker.confirm(row_id)
    # Today (day 4) shows nothing; day 3 keeps the confirmed call.
    assert tracker.get_usage("cohere", "command-a-plus-05-2026") == 0
    states = _row_states(tmp_quota_db, "cohere", "2026-08-03")
    assert list(states.values()) == [ReserveState.CONFIRMED]

    # A refund made after midnight also resolves the *reserved* day's row.
    monkeypatch.setattr(
        QuotaTracker, "_today", staticmethod(lambda: "2026-08-03")
    )
    dropped = tracker.reserve("cohere", "command-a-plus-05-2026")
    monkeypatch.setattr(
        QuotaTracker, "_today", staticmethod(lambda: "2026-08-04")
    )
    tracker.refund(dropped)
    states = _row_states(tmp_quota_db, "cohere", "2026-08-03")
    assert states[row_id] == ReserveState.CONFIRMED
    assert states[dropped] == ReserveState.REFUNDED


# ---------------------------------------------------------------------------
# Concurrency: never over-commit past the limit
# ---------------------------------------------------------------------------


def test_try_reserve_returns_none_when_exhausted(tracker):
    for _ in range(45):
        tracker.record_call("openrouter", "cohere/north-mini-code:free")
    assert tracker.try_reserve("openrouter", "cohere/north-mini-code:free") is None
    assert tracker.try_reserve("openrouter", "tencent/hy3:free") is None


def test_try_reserve_never_over_commits_under_concurrency(tracker, tmp_quota_db):
    limit = 45  # openrouter shared daily limit
    granted: list[int] = []
    granted_lock = threading.Lock()

    def worker() -> None:
        row = tracker.try_reserve("openrouter", "cohere/north-mini-code:free")
        if row is not None:
            with granted_lock:
                granted.append(row)

    threads = [threading.Thread(target=worker) for _ in range(300)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Never over-committed past the limit…
    assert len(granted) <= limit
    assert tracker.get_usage("openrouter", "cohere/north-mini-code:free") == len(granted)
    assert tracker.remaining("openrouter", "cohere/north-mini-code:free") == limit - len(granted)

    # …and every granted row resolves to a terminal state exactly once.
    for row_id in granted:
        tracker.confirm(row_id)
    assert tracker.get_usage("openrouter", "cohere/north-mini-code:free") == len(granted)
    states = set(_row_states(tmp_quota_db, "openrouter", QuotaTracker._today()).values())
    assert states <= {ReserveState.CONFIRMED}


def test_reset_clears_pending_reservations(tracker):
    row_id = tracker.reserve("cohere", "command-a-plus-05-2026")
    assert tracker.get_usage("cohere", "command-a-plus-05-2026") == 1
    tracker.reset()
    assert tracker.get_usage("cohere", "command-a-plus-05-2026") == 0
    # The row id is now dangling: resolving it is a guarded no-op.
    tracker.confirm(row_id)
    assert tracker.get_usage("cohere", "command-a-plus-05-2026") == 0


# ---------------------------------------------------------------------------
# Router integration
# ---------------------------------------------------------------------------


def test_success_confirms_reservation_and_skips_legacy_table(router, monkeypatch, tmp_quota_db):
    tracker = router.quota
    seen = {}

    def fake_dispatch(provider, model, messages, **kwargs):
        # The reservation must already exist *before* the dispatch goes out.
        seen["usage_at_dispatch"] = tracker.get_usage(provider, model)
        return ("Hello from fake", None)

    monkeypatch.setattr(router, "_dispatch", fake_dispatch)
    resp = router.call_agent(
        "groq", "openai/gpt-oss-120b", [{"role": "user", "content": "Hi"}]
    )

    assert resp.content == "Hello from fake"
    assert seen["usage_at_dispatch"] == 1  # reserved before dispatch
    assert tracker.get_usage("groq", "openai/gpt-oss-120b") == 1  # confirmed
    assert _legacy_count(tmp_quota_db, "groq", "openai/gpt-oss-120b") == 0


def test_network_error_before_any_response_refunds(router, monkeypatch):
    tracker = router.quota

    def boom(provider, model, messages, **kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(router, "_dispatch", boom)
    with pytest.raises(QuotaExhaustedError):
        router.call_agent(
            "cohere",
            "command-a-plus-05-2026",
            [{"role": "user", "content": "Hi"}],
            max_retries=1,
        )
    # Every hop died before reaching its provider: nothing consumed.
    assert tracker.get_usage("cohere", "command-a-plus-05-2026") == 0
    for provider, model in (
        ("mistral", "mistral-small-latest"),
        ("agnes", "agnes-2.0-flash"),
    ):
        assert tracker.get_usage(provider, model) == 0


def test_http_error_reaches_provider_and_confirms(router, monkeypatch):
    tracker = router.quota

    class _RateLimit(Exception):
        status_code = 429
        body = "Rate Limit"

    def boom(provider, model, messages, **kwargs):
        raise _RateLimit()

    monkeypatch.setattr(router, "_dispatch", boom)
    with pytest.raises(QuotaExhaustedError):
        router.call_agent(
            "cohere",
            "command-a-plus-05-2026",
            [{"role": "user", "content": "Hi"}],
            max_retries=1,
        )
    # The provider answered with 429 — the slot stays consumed.
    assert tracker.get_usage("cohere", "command-a-plus-05-2026") == 1


def test_empty_http_200_completion_confirms(router, monkeypatch):
    tracker = router.quota

    def empty(provider, model, messages, **kwargs):
        raise EmptyCompletionError("empty body")

    monkeypatch.setattr(router, "_dispatch", empty)
    with pytest.raises(QuotaExhaustedError):
        router.call_agent(
            "cohere",
            "command-a-plus-05-2026",
            [{"role": "user", "content": "Hi"}],
            max_retries=1,
        )
    # HTTP 200 (empty) still means the provider was reached.
    assert tracker.get_usage("cohere", "command-a-plus-05-2026") == 1


def test_quota_exhaustion_during_retry_rounds_cascades(router, monkeypatch):
    """A provider that hits its wall mid-retry loop must cascade cleanly."""
    tracker = router.quota
    for _ in range(28):
        tracker.record_call("cohere", "command-a-plus-05-2026")

    # First hop is exhausted before dispatch: try_reserve refuses the slot
    # and the router cascades. Every later hop hits a quota wall too.
    class _QuotaWall(Exception):
        status_code = 429
        body = "Insufficient quota — please top up."

    def wall(provider, model, messages, **kwargs):
        raise _QuotaWall()

    monkeypatch.setattr(router, "_dispatch", wall)
    with pytest.raises(QuotaExhaustedError):
        router.call_agent(
            "cohere",
            "command-a-plus-05-2026",
            [{"role": "user", "content": "Hi"}],
            max_retries=1,
        )
    assert tracker.get_usage("cohere", "command-a-plus-05-2026") == 28
