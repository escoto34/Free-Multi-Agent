"""
WAVE-10: concurrent (parallel) fetching.

The three previously-serial HTTP loops are now ThreadPoolExecutor-driven,
matching the existing convention in source_fetch.py (``min(3, n)`` workers).
These timing-bound tests prove the parallelism without depending on exact
wall-clock values: each loop completes in roughly ``ceil(n/3) * delay`` instead
of ``n * delay``. Content and ordering must be unaffected.

All HTTP is faked with simple delays — no real network, no LLM.
"""

from __future__ import annotations

import time

import agents.deep_research.source_fetch as sf
from agents.deep_research.source_fetch import FetchedSource
from agents.deep_research.contracts import SourceResultStatus

_SEARCH_DELAY = 0.2
_FETCH_DELAY = 0.2

_PAGE = (
    "Acme Clinic is the district's specialist centre offering medical "
    "consultations, physiotherapy, dentistry and emergency care with extended "
    "hours every weekday."
) * 4


def _sleeper(delay: float):
    def fake(url: str, *, timeout: float = 18.0, max_chars: int = 12000, **kwargs) -> FetchedSource:
        time.sleep(delay)
        return FetchedSource(
            url=url,
            status=SourceResultStatus.SUCCESS,
            http_status=200,
            text=_PAGE,
            error="",
        )

    return fake


def _search_many_urls():
    def fake(q: str, *, max_chars: int = 9000, timeout: float = 12.0) -> str:
        time.sleep(_SEARCH_DELAY)
        return "\n".join(f"URL: https://host{i}.test/" for i in range(6))

    return fake


def _search_no_urls():
    def fake(q: str, *, max_chars: int = 9000, timeout: float = 12.0) -> str:
        time.sleep(_SEARCH_DELAY)
        return "RESULT summary text without any machine-readable URLs."

    return fake


def test_fetch_search_documents_searches_in_parallel(monkeypatch):
    monkeypatch.setattr(sf, "search_duckduckgo", _search_no_urls())
    monkeypatch.setattr(sf, "fetch_url", _sleeper(0.0))

    queries = [f"query {i}" for i in range(6)]
    started = time.monotonic()
    sf.fetch_search_documents(queries, timeout=12.0, max_chars=8000)
    elapsed = time.monotonic() - started

    # Serial ≈ 6 × 0.2 = 1.2s; parallel (min(3,6)=3) ≈ 2 × 0.2 = 0.4s.
    assert elapsed < 1.0


def test_fetch_search_documents_fetches_pages_in_parallel(monkeypatch):
    monkeypatch.setattr(sf, "search_duckduckgo", _search_many_urls())
    monkeypatch.setattr(sf, "fetch_url", _sleeper(_FETCH_DELAY))

    queries = ["q"]
    started = time.monotonic()
    sf.fetch_search_documents(queries, max_fetches=6, timeout=12.0, max_chars=8000)
    elapsed = time.monotonic() - started

    # 6 urls / 3 workers ≈ 2 × 0.2s; serial ≈ 6 × 0.2 = 1.2s.
    assert elapsed < 1.0


def test_verify_cited_urls_parallel(monkeypatch):
    import core.search_guards as sg

    monkeypatch.setattr(sf, "fetch_url", _sleeper(_FETCH_DELAY))

    urls = " ".join(f"https://url{i}.test/" for i in range(8))
    content = f"Cited sources: {urls}"

    started = time.monotonic()
    sg.verify_cited_urls(content, [], max_verify=8, timeout=6.0)
    elapsed = time.monotonic() - started

    # 8 urls / 3 workers ≈ ceil(8/3) × 0.2 ≈ 0.6s; serial ≈ 1.6s.
    assert elapsed < 1.0


def test_parallel_fetch_preserves_ordering(monkeypatch):
    """Parallelism must not change which URLs appear or their relative order."""
    monkeypatch.setattr(sf, "search_duckduckgo", _search_many_urls())
    monkeypatch.setattr(sf, "fetch_url", _sleeper(_FETCH_DELAY))

    out = sf.fetch_search_documents(["q"], max_fetches=6, timeout=12.0, max_chars=8000)

    # All six hosts appear, in original registration order.
    assert "URL: https://host0.test/" in out
    idx = [out.find(f"host{i}.test/") for i in range(6)]
    assert all(i >= 0 for i in idx)
    assert idx == sorted(idx)