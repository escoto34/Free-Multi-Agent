"""Entity anchoring for deep research (avoid mixing unrelated companies)."""

from __future__ import annotations

from agents.deep_research.entity_focus import (
    entity_focus_block,
    extract_entity_anchors,
    extract_location_phrases,
    extract_name_variants,
    merge_search_terms,
)
from agents.deep_research.web_search import _build_query_list, _build_safe_query


def test_name_variants_credental():
    q = (
        "investiga todo sobre Creddental o Credental (misma empresa) "
        "la clinica dental en Honduras, San Pedro Sula"
    )
    variants = extract_name_variants(q)
    joined = " ".join(variants).lower()
    assert "creddental" in joined or "credental" in joined
    # Both spellings should surface when "o" split works
    assert any("cred" in v.lower() for v in variants)


def test_name_variants_english_planner_phrasing():
    q = (
        "Research comprehensive information about Creddental "
        "(also known as Credental), a dental clinic located in "
        "San Pedro Sula, Honduras."
    )
    variants = extract_name_variants(q)
    joined = " ".join(variants).lower()
    assert "creddental" in joined
    assert "credental" in joined
    # Must not treat the whole English essay as the company name
    assert not any("comprehensive information" in v.lower() for v in variants)


def test_anchors_include_topic_and_not_only_generics():
    q = "Acme Widgets company located in Berlin Germany"
    anchors = extract_entity_anchors(q)
    assert anchors
    blob = " ".join(anchors).lower()
    assert "acme" in blob or "widgets" in blob
    assert "berlin" in blob or "germany" in blob


def test_merge_drops_bare_generics():
    merged = merge_search_terms(
        ["Acme Widgets Berlin"],
        ["reviews", "website", "Acme Widgets reviews"],
        max_terms=8,
    )
    assert "reviews" not in [m.lower() for m in merged]
    assert "website" not in [m.lower() for m in merged]
    assert any("acme" in m.lower() for m in merged)


def test_entity_focus_block_mentions_exclusion():
    block = entity_focus_block("Credental San Pedro Sula")
    assert "ENTITY FOCUS" in block
    assert "Unverified" in block or "unrelated" in block.lower()


def test_build_query_list_prefers_entity_anchors():
    terms = ["Credental reviews", "generic dental"]
    queries = _build_query_list(
        terms,
        "Research Credental clinic San Pedro Sula Honduras",
        max_queries=1,
    )
    assert queries
    blob = " ".join(queries).lower()
    assert "credental" in blob
    # Facet list can be longer than max_queries (hints for one live call)
    assert any("credental" in q.lower() for q in queries)


def test_build_safe_query_still_bounded():
    q = _build_safe_query(["one", "two", "three"] + ["x" * 50] * 10)
    assert len(q) <= 150


def test_location_phrases_from_prepositions():
    locs = extract_location_phrases(
        "Research FooBar Inc located in Austin Texas, USA"
    )
    blob = " ".join(locs).lower()
    assert "austin" in blob or "texas" in blob or "usa" in blob
