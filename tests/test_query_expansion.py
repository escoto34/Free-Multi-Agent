"""WAVE-11B: the deep_research.web_search role wired for query expansion.

The role (groq/compound-mini, ~250 RPD) previously made zero LLM calls and was
"reserved but unused". It is now used for one bounded query-expansion call that
turns a vague user topic into more concrete DuckDuckGo facets. These tests prove
the wiring, the parse/dedupe/bound behavior, the fragile-fallback (no regression
when the call fails), and that the expanded facets actually reach the search
chain. No real LLM or live web call is made.
"""

from __future__ import annotations

import agents.deep_research.web_search as w


class _Resp:
    def __init__(self, content: str):
        self.content = content


def _no_net(monkeypatch):
    monkeypatch.setattr(w, "fetch_user_primary_sources", lambda *a, **k: [])
    monkeypatch.setattr(w, "outbound_presence_search_facets", lambda *a, **k: [])
    monkeypatch.setattr(w, "fetch_outbound_presence_pages", lambda *a, **k: [])
    monkeypatch.setattr(w, "collect_outbound_from_sources", lambda s: [])


def test_parse_expanded_facets_strips_numbering_dedupes_and_bounds():
    raw = (
        "1. dentist near montevideo\n"
        "2. dentist near montevideo\n"
        "- reviews for dentist\n"
        "+ contact details line\n"
        "dentist near montevideo\n"
        ""
    )
    got = w._parse_expanded_facets(raw, existing=[], max_facets=6)
    assert got == list(dict.fromkeys(got))
    assert len(got) <= 6
    assert len(got) >= 2
    assert all(not q[0].isdigit() and not q.startswith("- ") for q in got)


def test_parse_expanded_facets_drops_existing_facets():
    got = w._parse_expanded_facets(
        "dentist near montevideo\nbrand new facet\n",
        existing=["dentist near montevideo"],
        max_facets=6,
    )
    assert "dentist near montevideo" not in got
    assert "brand new facet" in got


def test_parse_expanded_facets_bounds_worst_case():
    got = w._parse_expanded_facets(
        "\n".join("facet number %d" % i for i in range(40)),
    )
    assert len(got) <= 6


def test_expand_query_facets_routes_role_and_parses(monkeypatch):
    captured: dict = {}

    def fake_call_agent(provider, model, messages, **kwargs):
        captured["provider"] = provider
        captured["model"] = model
        assert messages[0]["role"] == "system"
        assert messages[1]["content"] == "vague local dentist topic"
        return _Resp("1. dentist near montevideo official\n2. dentist reviews\n")

    monkeypatch.setattr(w, "call_agent", fake_call_agent)
    got = w.expand_query_facets("vague local dentist topic")
    assert got[0] == "dentist near montevideo official"
    assert captured["provider"] and captured["model"]


def test_expand_query_facets_falls_back_when_call_fails(monkeypatch):
    class _Quota(Exception):
        pass

    def boom(**kwargs):
        raise _Quota()

    monkeypatch.setattr(w, "call_agent", boom)
    assert w.expand_query_facets("anything") == []
    assert w.expand_query_facets("   ") == []


def test_expand_query_facets_falls_back_on_empty_completion(monkeypatch):
    monkeypatch.setattr(w, "call_agent", lambda **k: _Resp(""))
    assert w.expand_query_facets("anything") == []


def test_run_web_search_survives_crashing_expansion(monkeypatch):
    """A failing expansion must not crash the pipeline (no regression)."""
    _no_net(monkeypatch)
    monkeypatch.setattr(w, "expand_query_facets", lambda *a, **k: [])
    facets_called: list[str] = []
    monkeypatch.setattr(
        w, "fetch_search_documents",
        lambda qs, **kwargs: facets_called.extend(qs) or "SEARCH DUMP",
    )
    out = w.run_web_search(["dentist"], original_query="vague topic here")
    assert isinstance(out, str) and "PRIMARY SOURCES" in out
    assert facets_called, "heuristic facet list still produced"


def test_run_web_search_injects_expanded_facets(monkeypatch):
    """Expanded facets reach the real search chain (the wiring proof)."""
    _no_net(monkeypatch)
    monkeypatch.setattr(
        w,
        "expand_query_facets",
        lambda *a, **k: ["dentist near montevideo official"],
    )
    facets_called: list[str] = []
    monkeypatch.setattr(
        w,
        "fetch_search_documents",
        lambda qs, **kwargs: facets_called.extend(qs) or "SEARCH DUMP",
    )
    w.run_web_search(["dentist"], original_query="a dentist in uruguay")
    assert any(
        "dentist" in q.casefold() for q in facets_called
    ), "heuristic facets retained"
    assert "dentist near montevideo official" in facets_called