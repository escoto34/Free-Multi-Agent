"""
WAVE-09B: HttpCache wired into fetch_url — cache-aware fetch chokepoint.

All HTTP in the research pipeline funnels through
``agents/deep_research/source_fetch.py:fetch_url``, which now:

* serves identical in-process fetches from the HttpCache (miss -> real
  urlopen -> put),
* coalesces concurrent callers of the same URL into one real request,
* negative-caches the "empty body after extract" case with a shorter TTL.

``core/search_guards.verify_cited_urls`` sits on top of ``fetch_url``, so the
grounding -> synthesizer double-verification becomes cache hits for free.

These tests mock ``urllib.request.urlopen`` entirely — zero external calls.
"""

from __future__ import annotations

import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import agents.deep_research.source_fetch as sf
from core.http_cache import HttpCache

_PAGE = b"<html><body><h1>Acme Clinic</h1><p>Acme Clinic is the district's specialist centre offering medical consultations, physiotherapy, dentistry and emergency care with extended weekday hours.</p></body></html>"
_EMPTY = b"<html><body></body></html>"


class _FakeResp:
    def __init__(self, body: bytes, status: int = 200, ctype: str = "text/html"):
        self._body = body
        self.status = status
        self.headers = {"Content-Type": ctype}

    def read(self, n: int = -1) -> bytes:
        return self._body

    def getcode(self) -> int:
        return self.status

    def __enter__(self) -> "_FakeResp":
        return self

    def __exit__(self, *exc) -> bool:
        return False


def _mock_urlopen(monkeypatch, body: bytes, calls: list):
    def fake_urlopen(req, timeout=18.0):
        calls.append(str(req.full_url if hasattr(req, "full_url") else req))
        return _FakeResp(body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)


def test_fetch_url_second_call_is_cache_hit(monkeypatch):
    calls: list = []
    _mock_urlopen(monkeypatch, _PAGE, calls)

    a = sf.fetch_url("https://example.test/")
    b = sf.fetch_url("https://example.test/")

    assert a.ok and b.ok
    assert a.text == b.text
    assert len(calls) == 1  # second call served from cache


def test_fetch_url_cache_key_includes_fetch_parameters(monkeypatch):
    calls: list = []
    _mock_urlopen(monkeypatch, _PAGE, calls)

    sf.fetch_url("https://example.test/", max_chars=5000)
    sf.fetch_url("https://example.test/", max_chars=5000)  # cache hit
    sf.fetch_url("https://example.test/", max_chars=12000)  # different key

    assert len(calls) == 2


def test_verify_cited_urls_second_call_hits_cache(monkeypatch):
    """grounding -> synthesizer double-verification now costs one fetch."""
    from core.search_guards import verify_cited_urls

    calls: list = []
    _mock_urlopen(monkeypatch, _PAGE, calls)

    content = "Acme Clinic is the region's specialist. See https://example.test/ for services."
    sources = ["https://example.test/"]

    _, verified1, _ = verify_cited_urls(content, sources)
    _, verified2, _ = verify_cited_urls(content, sources)

    assert "https://example.test/" in verified1
    assert "https://example.test/" in verified2
    # One real HTTP fetch for the URL shared by both verification passes.
    assert len(calls) == 1


def test_negative_cache_empty_body_expires_faster_than_positive(monkeypatch):
    custom = HttpCache(default_ttl_seconds=60.0, negative_ttl_seconds=0.05)
    monkeypatch.setattr(sf, "get_default_cache", lambda: custom)
    calls: list = []
    _mock_urlopen(monkeypatch, _EMPTY, calls)

    first = sf.fetch_url("https://empty.test/")
    assert not first.ok and first.error == "empty body after extract"
    assert len(calls) == 1

    # Negative-cached: immediate re-request does NOT re-fetch.
    sf.fetch_url("https://empty.test/")
    assert len(calls) == 1

    # Shorter negative TTL expires: it re-fetches sooner than a normal hit.
    time.sleep(0.08)
    sf.fetch_url("https://empty.test/")
    assert len(calls) == 2


def test_positive_hit_survives_negative_ttl_window(monkeypatch):
    custom = HttpCache(default_ttl_seconds=60.0, negative_ttl_seconds=0.05)
    monkeypatch.setattr(sf, "get_default_cache", lambda: custom)
    calls: list = []
    _mock_urlopen(monkeypatch, _PAGE, calls)

    sf.fetch_url("https://full.test/")
    time.sleep(0.08)  # longer than the negative TTL…
    sf.fetch_url("https://full.test/")
    assert len(calls) == 1  # …but the positive hit survives


def test_fetch_url_single_flight_concurrent(monkeypatch):
    """12 concurrent requesters of one URL share exactly one real fetch."""
    calls: list = []

    def slow_urlopen(req, timeout=18.0):
        time.sleep(0.05)  # make the race observable
        calls.append(1)
        return _FakeResp(_PAGE)

    monkeypatch.setattr(urllib.request, "urlopen", slow_urlopen)

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(sf.fetch_url, "https://one.test/") for _ in range(12)]
        results = [f.result() for f in futures]

    assert all(r.ok for r in results)
    assert len(calls) == 1


def test_fetch_url_errors_are_not_poisoned(monkeypatch):
    """A transient HTTP error must not be cached as if it were real content."""
    calls: list = []

    def failing_urlopen(req, timeout=18.0):
        calls.append(1)
        raise urllib.error.HTTPError(
            req.full_url if hasattr(req, "full_url") else "u", 503, "Unavailable", {}, None
        )

    monkeypatch.setattr(urllib.request, "urlopen", failing_urlopen)

    a = sf.fetch_url("https://down.test/")
    b = sf.fetch_url("https://down.test/")

    assert not a.ok and a.status == 503
    assert not b.ok and b.status == 503
    assert len(calls) == 2  # non-empty-body failures are not cached (only negative empties)