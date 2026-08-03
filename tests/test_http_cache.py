"""
WAVE-09A: HttpCache unit tests — fully in-process, no network, no LLM.

Covers the four contract functions plus the roadmap's mandatory checks:
size-guard rejection, re-validation catching a deliberately-corrupted entry,
single-flight coalescing under concurrent access (fetch called exactly once
for N requesters), and a negative-TTL that is shorter and configurable.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from core.http_cache import HttpCache, cache_key


def test_cache_key_deterministic_and_version_sensitive():
    a = cache_key("https://example.com", "v1", q="hello world")
    b = cache_key("https://example.com", "v1", q="hello world")
    assert a == b
    # Adapter version participates: a parser change busts everything under it.
    assert cache_key("https://example.com", "v2", q="hello world") != a
    # Params matter; param order does not.
    assert cache_key("u", "v1", a="1", b="2") == cache_key("u", "v1", b="2", a="1")
    assert cache_key("u", "v1", a="1") != cache_key("u", "v1", a="2")


def test_get_miss_and_put_hit():
    cache = HttpCache()
    assert cache.get("nope") is None
    assert cache.put("k", b"body", ttl_seconds=60.0) is True
    assert cache.get("k") == b"body"


def test_put_second_write_overwrites():
    cache = HttpCache()
    cache.put("k", b"first", ttl_seconds=60.0)
    cache.put("k", b"second", ttl_seconds=60.0)
    assert cache.get("k") == b"second"


def test_size_guard_refuses_oversized_values():
    cache = HttpCache(max_value_bytes=1024)
    big = b"x" * 1025
    assert cache.put("k", big, ttl_seconds=60.0) is False
    assert cache.get("k") is None
    # A value that fits is accepted.
    assert cache.put("k2", b"y" * 100, ttl_seconds=60.0) is True
    assert cache.get("k2") == b"y" * 100


def test_revalidation_catches_corrupted_entry():
    cache = HttpCache()
    cache.put("k", b"trusted payload", ttl_seconds=60.0)
    # Corrupt the stored value directly (simulates disk/bit-rot poisoning).
    with cache._store_lock:
        entry = cache._store["k"]
        corrupted = b"\x00" * len(entry.value)
        cache._store["k"] = type(entry)(value=corrupted, expires_at=entry.expires_at, negative=False)

    assert cache.get("k") is None  # re-validation rejects it
    assert cache.get("k") is None  # and the poisoned entry is evicted


def test_expiry():
    cache = HttpCache()
    cache.put("k", b"data", ttl_seconds=0.05)
    assert cache.get("k") == b"data"
    time.sleep(0.08)
    assert cache.get("k") is None


def test_negative_ttl_is_shorter_and_configurable():
    # default 60s vs negative 50ms: negative must expire far sooner.
    cache = HttpCache(default_ttl_seconds=60.0, negative_ttl_seconds=0.05)

    cache.put("neg", b"", negative=True)
    assert cache.get("neg") == b""
    cache.put("pos", b"data", ttl_seconds=60.0)
    assert cache.get("pos") == b"data"

    time.sleep(0.08)
    assert cache.get("neg") is None  # negative expired quickly…
    assert cache.get("pos") == b"data"  # …positive survives


def test_put_uses_default_ttl_when_not_specified():
    cache = HttpCache(default_ttl_seconds=0.05, negative_ttl_seconds=0.01)
    cache.put("k", b"data")  # no explicit ttl -> default_ttl_seconds
    assert cache.get("k") == b"data"
    time.sleep(0.08)
    assert cache.get("k") is None


def test_invalidate_and_clear():
    cache = HttpCache()
    cache.put("a", b"1", ttl_seconds=60.0)
    cache.put("b", b"2", ttl_seconds=60.0)
    cache.invalidate("a")
    assert cache.get("a") is None
    assert cache.get("b") == b"2"
    cache.clear()
    assert cache.get("b") is None


def test_coalesce_single_flight_under_concurrency():
    """N concurrent requesters of one key → exactly one underlying fetch."""
    cache = HttpCache()
    key = cache_key("https://example.com", "v1")
    fetch_count = 0
    fetch_lock = threading.Lock()

    def fetch():
        nonlocal fetch_count
        time.sleep(0.05)  # make the race observable
        with fetch_lock:
            fetch_count += 1
        cache.put(key, b"shared payload", ttl_seconds=60.0)
        return b"shared payload"

    from functools import partial

    with ThreadPoolExecutor(max_workers=8) as pool:
        run = partial(cache.coalesce, key, fetch, deadline_seconds=5.0)
        futures = [pool.submit(run) for _ in range(16)]
        results = [f.result() for f in futures]

    assert all(r == b"shared payload" for r in results)
    assert fetch_count == 1


def test_coalesce_returns_cached_value_on_second_phase():
    cache = HttpCache()
    key = "k"
    fetches = []

    def fetch():
        fetches.append(1)
        cache.put(key, b"v1", ttl_seconds=60.0)
        return b"v1"

    assert cache.coalesce(key, fetch, deadline_seconds=5.0) == b"v1"
    assert cache.coalesce(key, fetch, deadline_seconds=5.0) == b"v1"
    # Second phase must be a pure cache hit — fetch not re-invoked.
    assert len(fetches) == 1


def test_coalesce_validates_deadline():
    cache = HttpCache()
    with pytest.raises(ValueError):
        cache.coalesce("k", lambda: b"x", deadline_seconds=0)
    with pytest.raises(ValueError):
        cache.coalesce("k", lambda: b"x", deadline_seconds=-1)


def test_lock_dict_is_refcount_cleaned():
    """coalesce() must not leak one lock per historical key."""
    cache = HttpCache()
    for i in range(5):
        cache.coalesce(f"k{i}", lambda: (cache.put(f"k{i}", b"x", ttl_seconds=60.0), b"x")[1], deadline_seconds=2.0)
    assert cache._locks == {}
    assert cache._lock_users == {}


def test_default_cache_singleton():
    from core.http_cache import get_default_cache

    assert get_default_cache() is get_default_cache()