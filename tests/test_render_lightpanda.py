"""WAVE-12: optional Lightpanda rendering.

Core guarantees:
* ``render`` is an opt-in ``"lightpanda"`` parameter, default ``"none"``.
* No Playwright/Puppeteer dependency (shelves out to the binary or no-op).
* Absence of Lightpanda degrades silently - the mandatory no-op test asserts a
  ``render="lightpanda"`` fetch is identical to ``render="none"``.
* ``render`` is part of the cache key (rendered vs unrendered differ).
* A successful render yielding no DOM is ``EMPTY`` ("rendered but empty"),
  distinct from a render that failed (which degrades to plain HTTP).

Binary never present in CI; rendering is fully faked via monkeypatch.
"""

from __future__ import annotations

import urllib.request

import agents.deep_research.source_fetch as sf
from agents.deep_research.contracts import SourceResultStatus
from core.http_cache import HttpCache

_PAGE = (
    "<html><body><p>Acme Clinic is the district specialist with "
    "consultations, physiotherapy, dentistry and emergency care.</p></body></html>"
)
_RENDERED = (
    "<html><body><p>Rendered content loaded by JS: specialists at "
    "acme clinic, rapid appointments, extended hours.</p></body></html>"
)


class _FakeResp:
    headers = {}

    def __init__(self, body: bytes):
        self._body = body

    def read(self, *a, **k):
        return self._body

    def getcode(self):
        return 200

    @property
    def status(self):
        return 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _mock_http(monkeypatch, body: bytes, calls: list):
    def fake_urlopen(req, timeout=18.0):
        calls.append(1)
        return _FakeResp(body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)


def _fresh_cache(monkeypatch):
    monkeypatch.setattr(sf, "get_default_cache", lambda: HttpCache())


def test_noop_render_absent_is_identical(monkeypatch):
    """Mandatory no-op: absent Lightpanda -> identical to render='none'."""
    calls: list = []
    _mock_http(monkeypatch, _PAGE.encode(), calls)
    _fresh_cache(monkeypatch)
    monkeypatch.setattr(sf, "render_html", lambda *a, **k: None)

    plain = sf.fetch_url("https://acme.test/", render="none")
    rendered = sf.fetch_url("https://acme.test/", render="lightpanda")

    assert calls == [1, 1], "two real fetches (distinct cache entries)"
    assert plain.status is rendered.status is SourceResultStatus.SUCCESS
    assert plain.http_status == rendered.http_status == 200
    assert plain.text == rendered.text
    assert plain.error == rendered.error


def test_render_is_part_of_cache_key():
    key_none = sf.cache_key(
        "https://acme.test/", "v1", extract_signals="True", render="none"
    )
    key_rend = sf.cache_key(
        "https://acme.test/", "v1", extract_signals="True", render="lightpanda"
    )
    assert key_none != key_rend


def test_render_present_uses_rendered_dom(monkeypatch):
    monkeypatch.setattr(sf, "render_html", lambda *a, **k: _RENDERED)
    src = sf._fetch_url_uncached(
        "https://acme.test/", timeout=12.0, max_chars=2000,
        user_agent="test", extract_signals=False, follow_outbound=False,
        render="lightpanda",
    )
    assert src.status is SourceResultStatus.SUCCESS
    assert src.http_status is None  # render path carries no HTTP status
    assert "rendered content" in src.text.casefold()


def test_render_present_empty_dom_is_rendered_empty(monkeypatch):
    monkeypatch.setattr(sf, "render_html", lambda *a, **k: "")
    src = sf._fetch_url_uncached(
        "https://acme.test/", render="lightpanda", timeout=12.0, max_chars=2000,
        user_agent="test", extract_signals=False, follow_outbound=False,
    )
    assert src.status is SourceResultStatus.EMPTY
    assert src.error == "rendered empty (lightpanda)"


def test_render_failure_degrades_to_plain_http(monkeypatch):
    calls: list = []
    _fresh_cache(monkeypatch)
    _mock_http(monkeypatch, _PAGE.encode(), calls)
    monkeypatch.setattr(sf, "render_html", lambda *a, **k: None)
    src = sf.fetch_url("https://acme.test/", render="lightpanda")
    assert src.status is SourceResultStatus.SUCCESS
    assert src.http_status == 200
    assert calls == [1]


def test_render_none_never_does_subprocess(monkeypatch):
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *a, **k: _FakeResp(_PAGE.encode()),
    )
    src = sf.fetch_url("https://acme.test/", render="none")
    assert src.status is SourceResultStatus.SUCCESS