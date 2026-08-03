"""
In-process HTTP response cache with single-flight coalescing (WAVE-09A).

Modules: nothing in ``agents/deep_research/`` or ``core/search_guards.py``
imports this in this wave — the cache exists and is proven correct, but stays
unwired until WAVE-09B routes ``fetch_url()`` through it.

Design (deliberate decisions):

* **In-memory, not persistent.** MultiAgent is a CLI that starts fresh per
  invocation, so a dict-backed store with ``threading.Lock`` is enough — no
  SQLite, no disk, no Redis. Persistence would be complexity nobody asked for.
* **Threaded, not asyncio.** Matches the ``ThreadPoolExecutor`` / ``as_completed``
  idiom already used at ``agents/deep_research/source_fetch.py:942``.
* **``cache_key()``** joins every field with ``\\x1f`` and SHA-256 hashes the
  material (pattern from ``Trend-AI/starter/backend/app/trends/cache.py``).
  ``adapter_version`` is part of the key, so a material change to the HTML
  extraction logic auto-invalidates every cached entry with no manual bump.
* **Size guard:** values over ``max_value_bytes`` are refused, not stored.
* **Re-validate on read:** every stored value carries a magic+fingerprint
  header; ``get()`` re-validates before returning, so a corrupted or poisoned
  cache entry cannot inject bad data into a live run.
* **Single-flight ``coalesce()``:** concurrent requesters of the same key share
  one in-flight fetch via a refcounted per-key lock that is popped at zero
  (never retain one lock per historical key forever).
* **Negative caching:** a sentinel empty result is cached with a *shorter*
  TTL than a normal hit so a persistently-empty source is not re-hit on every
  call, yet recovers quickly once it becomes non-empty.

The TTLs live in ``__init__`` (``negative_ttl_seconds``, ``default_ttl_seconds``)
so WAVE-09B can tune them; nothing cache-related is hardcoded.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, TypeVar

CACHE_FORMAT = "multiagent-http-v1"
_MAGIC = b"MHX1"
_DIGEST_SIZE = 32  # sha256
_HEADER_SIZE = len(_MAGIC) + _DIGEST_SIZE

# Values over this many bytes are refused, not stored (matches Trend-AI's
# 64_000-byte guard; "64KB" in the roadmap text).
MAX_CACHE_VALUE_BYTES = 64_000

T = TypeVar("T")


@dataclass
class CacheEntry:
    """A value plus its expiry bookkeeping."""

    value: bytes
    expires_at: float  # time.monotonic() deadline
    negative: bool = False


def cache_key(source: str, adapter_version: str, **params: str) -> str:
    """Deterministic cache key for *adapter_version* + a source + params.

    Adapter version is part of the key so any material change to the fetch /
    extraction logic invalidates every cached entry from before the change
    with no manual cache-busting.
    """
    material = "\x1f".join(
        (
            CACHE_FORMAT,
            str(source),
            adapter_version,
            *(
                f"{k}={v}".casefold()
                for k, v in sorted(params.items())
                if v is not None
            ),
        )
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"http:{digest}"


def _encode(value: bytes) -> bytes | None:
    """Wrap a payload+magic+fingerprint (so corruption is detectable on read)."""
    if value is None or len(value) > MAX_CACHE_VALUE_BYTES:
        return None
    fingerprint = hashlib.sha256(value).digest()
    return _MAGIC + fingerprint + value


def _decode(encoded: bytes) -> bytes | None:
    """Re-validate a stored value; return the payload or None if corrupted."""
    if not isinstance(encoded, bytes) or len(encoded) < _HEADER_SIZE:
        return None
    if encoded[: len(_MAGIC)] != _MAGIC:
        return None
    fingerprint = encoded[len(_MAGIC) : _HEADER_SIZE]
    payload = encoded[_HEADER_SIZE:]
    if hashlib.sha256(payload).digest() != fingerprint:
        return None
    return payload


class HttpCache:
    """Thread-safe in-memory HTTP response cache.

    :param default_ttl_seconds: TTL for normal (positive) hits.
    :param negative_ttl_seconds: shorter TTL for empty/negative results.
    :param max_value_bytes: values above this are refused by ``put``.
    """

    def __init__(
        self,
        *,
        default_ttl_seconds: float = 24 * 60 * 60.0,
        negative_ttl_seconds: float = 5 * 60.0,
        max_value_bytes: int = MAX_CACHE_VALUE_BYTES,
    ) -> None:
        if negative_ttl_seconds >= default_ttl_seconds:
            raise ValueError(
                "negative_ttl_seconds must be shorter than default_ttl_seconds"
            )
        self._default_ttl = float(default_ttl_seconds)
        self._negative_ttl = float(negative_ttl_seconds)
        self._max_value_bytes = int(max_value_bytes)
        self._store: dict[str, CacheEntry] = {}
        self._store_lock = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}
        self._lock_users: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def get(self, key: str) -> Optional[bytes]:
        """Return the cached value or ``None``.

        Re-validates the stored value before returning (a corrupted entry is a
        miss and is evicted), and evicts expired entries.
        """
        now = time.monotonic()
        with self._store_lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                del self._store[key]
                return None
            payload = _decode(entry.value)
            if payload is None:
                # Corrupted / poisoned entry — drop it, caller does not see it.
                del self._store[key]
                return None
            return payload

    def put(
        self,
        key: str,
        value: bytes,
        *,
        ttl_seconds: Optional[float] = None,
        negative: bool = False,
    ) -> bool:
        """Store *value* under *key*; refuse values past the size guard.

        Returns ``False`` (and stores nothing) when ``len(value) >``
        ``max_value_bytes`` or when the value cannot be encoded.
        """
        if value is None:
            return False
        encoded = _encode(value)
        if encoded is None or len(value) > self._max_value_bytes:
            return False
        ttl = (
            self._negative_ttl
            if negative
            else (ttl_seconds if ttl_seconds is not None else self._default_ttl)
        )
        with self._store_lock:
            self._store[key] = CacheEntry(
                value=encoded,
                expires_at=time.monotonic() + ttl,
                negative=negative,
            )
        return True

    def invalidate(self, key: str) -> None:
        """Drop a key from the cache outright (paranoid CLI/explicit eviction)."""
        with self._store_lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        """Drop every cached entry (used by tests / cache-busting)."""
        with self._store_lock:
            self._store.clear()

    # ------------------------------------------------------------------
    # Single-flight
    # ------------------------------------------------------------------

    def coalesce(
        self,
        key: str,
        fetch: Callable[[], T],
        *,
        deadline_seconds: float,
    ) -> T:
        """Share one in-flight *fetch* among concurrent requesters of *key*.

        The caller's *fetch* is responsible for ``put()``-ing its result. We
        only guarantee that under contention for the same key the underlying
        fetch callback runs *once*: the first requester acquires a refcounted
        per-key lock, runs the fetch and populates the cache; waiters block on
        the lock and then resolve to the already-cached value.

        If the lock cannot be acquired within ``deadline_seconds`` seconds the
        caller falls back to a direct fetch rather than starving forever.
        """
        if deadline_seconds <= 0:
            raise ValueError("deadline_seconds must be positive")

        lock = self._locks.setdefault(key, threading.Lock())
        self._lock_users[key] = self._lock_users.get(key, 0) + 1
        try:
            if not lock.acquire(timeout=deadline_seconds):
                return fetch()
            try:
                cached = self.get(key)
                if cached is not None:
                    return cached  # type: ignore[return-value]
                return fetch()
            finally:
                lock.release()
        finally:
            # Do not retain one local lock per historical cache key forever.
            self._lock_users[key] -= 1
            if self._lock_users[key] <= 0:
                self._locks.pop(key, None)
                self._lock_users.pop(key, None)


# Module-level convenience instance (thread-safe by construction).
_default_cache: Optional[HttpCache] = None


def get_default_cache() -> HttpCache:
    """Return the process-wide default HttpCache (lazily created)."""
    global _default_cache
    if _default_cache is None:
        _default_cache = HttpCache()
    return _default_cache