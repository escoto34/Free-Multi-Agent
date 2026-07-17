"""
Context Compressor agent for System B (Deep Research).

Provider/model/fallback from config/model_router.yaml.
"""

from __future__ import annotations

from typing import Optional

from agents.deep_research.entity_focus import extract_entity_anchors, merge_search_terms
from core.agent_runtime import run_structured_agent
from schemas.deep_research import CondensedTrends

SYSTEM_PROMPT = """You are an expert information synthesis and context compression agent.
Identify the core entities, name variants, and focused search queries for the research topic.
Generate a structured query list to guide search engines.

CRITICAL CONSTRAINTS on the "technologies" field (search terms):
- Return AT MOST 8 items.
- For company / clinic / person research, EACH term MUST include the exact
  entity name (or a clear spelling variant) plus one facet, e.g.:
  "Credental San Pedro Sula", "Credentalhn.com", "Credental orthodontics reviews".
- Prefer precise queries over generic ones. NEVER emit bare generics like
  "dental clinic", "Honduras dentists", or "patient reviews" alone — those
  mix unrelated businesses.
- Each item should be a search-engine style phrase (about 2–8 words).
  Proper names may stay together even if slightly longer.
- Cover facets when relevant: official website, address, phone, services,
  ownership/history, Google/Facebook reviews, accreditations, news.

You MUST output your response strictly as a JSON object matching this schema:
{
  "technologies": ["Search term 1", "Search term 2", "Search term 3"],
  "rationale": "Brief explanation of why these search terms were prioritized."
}
Only return raw JSON. Do not wrap in markdown code blocks like ```json ... ```.
"""


def run_context_compressor(
    query: str,
    router_instance=None,
    fallback_override: Optional[dict[str, str]] = None,
) -> CondensedTrends:
    """Extract short search terms from the research query, entity-anchored."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Extract search targets for: {query}"},
    ]
    trends = run_structured_agent(
        "deep_research",
        "context_compressor",
        messages=messages,
        schema=CondensedTrends,
        router_instance=router_instance,
        fallback_override=fallback_override,
    )

    # Defensive normalization — never trust the model alone.
    trimmed: list[str] = []
    for term in trends.technologies[:8]:
        term = term.strip()
        if len(term) > 100:
            term = " ".join(term.split()[:10])
        if term:
            trimmed.append(term)

    anchors = extract_entity_anchors(query, max_anchors=6)
    trends.technologies = merge_search_terms(anchors, trimmed, max_terms=8)
    if not trends.technologies:
        trends.technologies = anchors[:4] or [query[:150]]
    if not (trends.rationale or "").strip():
        trends.rationale = "Entity-anchored search terms from the research topic."
    return trends
