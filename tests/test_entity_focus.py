"""Entity anchoring for deep research (avoid mixing unrelated companies)."""

from __future__ import annotations

from agents.deep_research.entity_focus import (
    entity_focus_block,
    extract_entity_anchors,
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


def test_anchors_include_topic_and_not_only_generics():
    q = "Credental dental clinic San Pedro Sula Honduras"
    anchors = extract_entity_anchors(q)
    assert anchors
    blob = " ".join(anchors).lower()
    assert "credental" in blob
    assert "san pedro" in blob or "honduras" in blob


def test_merge_drops_bare_generics():
    merged = merge_search_terms(
        ["Credental San Pedro Sula"],
        ["dental", "clinic", "Credental reviews"],
        max_terms=8,
    )
    assert "dental" not in [m.lower() for m in merged]
    assert any("credental" in m.lower() for m in merged)


def test_entity_focus_block_mentions_exclusion():
    block = entity_focus_block("Credental San Pedro Sula")
    assert "ENTITY FOCUS" in block
    assert "Unverified" in block or "unrelated" in block.lower()


def test_build_query_list_prefers_original_topic():
    terms = ["Credental reviews", "generic dental"]
    queries = _build_query_list(
        terms,
        "Research Credental clinic San Pedro Sula Honduras",
        max_queries=4,
    )
    assert queries
    assert "Credental" in queries[0] or "credental" in queries[0].lower()
    assert len(queries) <= 4


def test_build_safe_query_still_bounded():
    q = _build_safe_query(["one", "two", "three"] + ["x" * 50] * 10)
    assert len(q) <= 150
