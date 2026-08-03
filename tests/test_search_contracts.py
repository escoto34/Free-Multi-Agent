"""WAVE-11A: search/fetch status contracts, partial validation, and scoring.

Covers the three mandatory test families of WAVE-11A:
1. DDG-markup-change resilience: a malformed result page must yield an
   ``INVALID``/partial-drop outcome, never a silent empty return.
2. Status taxonomy: every prior ``.ok`` boolean is now a ``SourceResultStatus``
   value, and HTTP failures map to the correct member.
3. Scoring: versioned decomposed ``score_result`` returns ``(components, total)``
   with ``total`` in ``[0, 1]`` and a pinned ``SCORING_VERSION``.

No live network or LLM calls — all markup is a static fixture.
"""

from __future__ import annotations

import agents.deep_research.source_fetch as sf
from agents.deep_research.contracts import (
    SCORING_VERSION,
    SearchResult,
    SourceResultStatus,
    http_status_to_source_status,
    score_result,
)

_SUPPORT_STATUS_MEMBERS = {
    SourceResultStatus.SUCCESS,
    SourceResultStatus.EMPTY,
    SourceResultStatus.TIMEOUT,
    SourceResultStatus.ERROR,
    SourceResultStatus.INVALID,
    SourceResultStatus.RATE_LIMITED,
    SourceResultStatus.QUOTA_EXHAUSTED,
    SourceResultStatus.NOT_APPLICABLE,
}


def _ddg_page(rows: list[tuple[str, str, str]]) -> str:
    """Build a realistic DDG-lite fragment from (url, title, snippet) rows."""
    parts = []
    for url, title, snippet in rows:
        parts.append(
            '<tr><td class="result-snippet">'
            f'<a rel="nofollow" href="{url}">{title}</a>'
            "</td></tr>"
            f'<tr><td class="result-snippet">{snippet}</td></tr>'
        )
    return (
        '<form action="//lite.duckduckgo.com/lite/">'
        '<input type="submit" value="Search">'
        "</form>"
        '<div class="results">' + "".join(parts) + "</div>"
    )


# --- DDG-markup resilience --------------------------------------------------


def test_ddg_parse_wellformed_rows_succeeds():
    html = _ddg_page(
        [
            ("https://acme.example.com", "Acme Official",
             "Acme is the district specialist offering consultations and care."),
            ("https://review.example/acme", "Acme reviews",
             "Users rate Acme highly for rapid appointments."),
        ]
    )
    results, status = sf._parse_ddg_results(html)
    assert status is SourceResultStatus.SUCCESS
    assert [r.url for r in results] == [
        "https://acme.example.com",
        "https://review.example/acme",
    ]


def test_ddg_parse_partially_malformed_keeps_good_rows():
    """A batch with one malformed row keeps the good rows (partial validation)."""
    html = _ddg_page(
        [
            # malformed: relative href, must be dropped individually
            ("/noredir?u=bad", "Dropped row", "useless"),
            ("https://acme.example", "Acme Acme", "real official site details"),
        ]
    )
    results, status = sf._parse_ddg_results(html)
    assert status is SourceResultStatus.SUCCESS
    assert [r.url for r in results] == ["https://acme.example"]
    assert results[0].title == "Acme Acme"


def test_ddg_parse_malformed_page_is_invalid_not_silent():
    # Markup present (result-snippet) but no parseable rows → INVALID, not EMPTY.
    html = '<div class="results"><tr><td class="result-snippet"><a href="/oops">'
    results, status = sf._parse_ddg_results(html)
    assert results == []
    assert status is SourceResultStatus.INVALID


def test_ddg_parse_page_without_markers_is_empty():
    html = "<html><body>We could not find anything for that query.</body></html>"
    results, status = sf._parse_ddg_results(html)
    assert results == []
    assert status is SourceResultStatus.EMPTY


def test_search_duckduckgo_invalid_logs_and_returns_empty(monkeypatch, caplog):
    def fake_open(req, timeout=15.0):
        return _FakeResp(b'<td class="result-snippet"><a href="/mangled">')

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", fake_open)
    with caplog.at_level("WARNING"):
        out = sf.search_duckduckgo("vague topic")
    assert out == ""
    assert any("markup may have changed" in rec.message for rec in caplog.records)


class _FakeResp:
    def __init__(self, raw: bytes):
        self._raw = raw

    def read(self, *a, **k):
        return self._raw

    def getcode(self):
        return 200

    headers = {}

    @property
    def status(self):
        return 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


# --- status taxonomy --------------------------------------------------------


def test_source_result_status_reserved_members():
    """Binding decision 5: the enum is its own type, not CallOutcome's."""
    assert set(SourceResultStatus) == _SUPPORT_STATUS_MEMBERS
    assert SourceResultStatus.NOT_APPLICABLE in SourceResultStatus


def test_http_status_map():
    assert http_status_to_source_status(200) is SourceResultStatus.SUCCESS
    assert http_status_to_source_status(204) is SourceResultStatus.SUCCESS
    assert http_status_to_source_status(503) is SourceResultStatus.TIMEOUT
    assert http_status_to_source_status(504) is SourceResultStatus.TIMEOUT
    assert http_status_to_source_status(429) is SourceResultStatus.RATE_LIMITED
    assert http_status_to_source_status(
        402, body="insufficient quota"
    ) is SourceResultStatus.QUOTA_EXHAUSTED
    assert http_status_to_source_status(
        429, body="usage limit quota exhausted"
    ) is SourceResultStatus.QUOTA_EXHAUSTED
    assert http_status_to_source_status(422) is SourceResultStatus.INVALID
    assert http_status_to_source_status(404) is SourceResultStatus.ERROR


def test_fetched_source_success_status():
    """A SUCCESS-status source drives the call sites that used to read `.ok`."""
    src = sf.FetchedSource(
        url="https://acme.example",
        status=SourceResultStatus.SUCCESS,
        http_status=200,
        text="Acme is the specialist.",
        error="",
    )
    assert sf.format_primary_source_block([src]).startswith("=== PRIMARY SOURCES")
    assert "PRIMARY OK" in sf.format_primary_source_block([src])
    collected = sf.collect_outbound_from_sources([src])
    assert isinstance(collected, list)


def test_empty_url_fetch_returns_error_status():
    empty = sf.fetch_url("  ")
    assert empty.status is SourceResultStatus.ERROR
    assert empty.http_status is None
    assert empty.error == "empty url"


# --- scoring -----------------------------------------------------------------


def test_score_result_shape_and_range():
    components, total = score_result(
        SearchResult(
            url="https://acme.example/",
            title="Acme Clinic Domestic",
            snippet="Medical specialists with extended hours." * 3,
        )
    )
    assert set(components) == {"transport", "homepage_bias", "title", "snippet"}
    assert all(0.0 <= v <= 1.0 for v in components.values())
    assert 0.0 <= total <= 1.0
    assert SCORING_VERSION == "search-v1"


def test_score_result_orders_by_snippet_and_url():
    rich = SearchResult(
        url="https://acme.example/", title="Acme Clinic",
        snippet="detailed verified listing about the doctor's own good public ",
    )
    weak = SearchResult(url="", title="", snippet="")
    assert score_result(rich)[1] > score_result(weak)[1]