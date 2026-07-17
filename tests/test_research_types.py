"""Research typology classification (domain-agnostic)."""

from __future__ import annotations

from agents.deep_research.research_types import (
    classify_research,
    profile_from_mapping,
    research_profile_block,
    search_facet_hints,
)
from agents.deep_research.web_search import _build_query_list
from schemas.deep_research import CondensedTrends


def test_applied_descriptive_default_for_entity_profile():
    p = classify_research(
        "Investiga la presencia digital y contacto de Acme Corp en Madrid"
    )
    assert p.purpose == "applied"
    assert p.depth == "descriptive"
    assert p.design == "non_experimental"


def test_basic_exploratory_theory():
    p = classify_research(
        "Estado del arte y marco teórico sobre redes neuronales; "
        "investigación básica exploratoria sin aplicación práctica inmediata"
    )
    assert p.purpose == "basic"
    assert p.depth in ("exploratory", "descriptive")


def test_explanatory_quant():
    p = classify_research(
        "Por qué cae la retención: análisis de causas e impacto con estadísticas "
        "y encuesta (n=400)"
    )
    assert p.depth == "explanatory"
    assert p.data_approach in ("quantitative", "mixed")


def test_experimental_design():
    p = classify_research(
        "Resultados de un A/B test y experimento controlado con grupo de control"
    )
    assert p.design == "experimental"


def test_profile_block_mentions_dimensions():
    p = classify_research("descripción del mercado y características del sector")
    block = research_profile_block(p)
    assert "RESEARCH PROFILE" in block
    assert "Purpose" in block
    assert "Depth" in block


def test_search_facets_change_with_profile():
    basic = classify_research("marco teórico y literature review del concepto X")
    applied = classify_research("cómo implementar una solución práctica para Y")
    fb = " ".join(search_facet_hints(basic, "TopicX")).lower()
    fa = " ".join(search_facet_hints(applied, "TopicY")).lower()
    assert "theory" in fb or "literature" in fb or "academic" in fb
    assert "practical" in fa or "implementation" in fa or "solution" in fa


def test_query_list_includes_typology_facets():
    qs = _build_query_list(
        [],
        "Estado del arte teórico sobre TopicZ frameworks",
        max_queries=1,
        profile=classify_research(
            "Estado del arte teórico sobre TopicZ frameworks investigación básica"
        ),
    )
    blob = " ".join(qs).lower()
    assert "theory" in blob or "literature" in blob or "academic" in blob


def test_condensed_trends_defaults_accept_legacy_json():
    t = CondensedTrends(
        technologies=["Foo reviews"],
        rationale="test",
    )
    assert t.purpose == "applied"
    assert t.depth == "descriptive"
    assert t.data_approach == "mixed"
    assert t.design == "non_experimental"


def test_profile_from_mapping_aliases():
    p = profile_from_mapping(
        {
            "purpose": "aplicada",
            "depth": "explicativa",
            "data_approach": "cualitativa",
            "design": "no experimental",
        }
    )
    assert p.purpose == "applied"
    assert p.depth == "explanatory"
    assert p.data_approach == "qualitative"
    assert p.design == "non_experimental"
