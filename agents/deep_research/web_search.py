"""
Web Search agent for System B (Deep Research).

Provider/model from config/model_router.yaml (typically groq/compound-mini).

Uses a single live compound call that instructs the model to run several
entity-anchored searches *inside that one turn* (multi-tool). Multiple
sequential API calls were too slow and made the CLI look hung.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from agents.deep_research.entity_focus import entity_focus_block, extract_entity_anchors
from core.agent_runtime import run_role_raw
from core.search_guards import NoLiveSearchError, raise_if_no_live_search

logger = logging.getLogger(__name__)

ProgressCb = Optional[Callable[[str], None]]

SYSTEM_PROMPT = """You are a live web-search research agent.
You MUST use live web search tools (not training memory alone).

In THIS single response, run MULTIPLE distinct live searches (several tool
calls) covering different facets of the same subject, then merge the findings.

Rules:
1. Search the EXACT subject the user named. Do not substitute a different clinic,
   hospital, or brand with a similar name or the same city.
2. Collect concrete facts: legal/trade names, addresses, phones, emails, website,
   social profiles that clearly belong to the subject, services, hours,
   staff/doctors if named, reviews (ratings/counts), ownership/history,
   accreditations, news, directories.
3. For every fact, include the source URL.
4. If a result is a DIFFERENT organization, mark it as:
   EXCLUDED (unrelated): <name> — <why> — <url>
   and do NOT fold its contact details into the main subject.
5. Prefer primary sources: official website, Google Business / Maps, Facebook
   page whose title matches the entity, government or professional registries.
6. Return a structured dump with sections:
   - Confirmed facts (with URLs)
   - Contact & locations
   - Services
   - Reviews & reputation
   - History / ownership / staff (if any)
   - EXCLUDED unrelated hits
   - Gaps (what you could not verify)
"""

MAX_SEARCH_TERMS: int = 8
MAX_QUERY_CHARS: int = 150
# Kept for API compatibility; multi-facet search is done in one live call.
MAX_LIVE_QUERIES: int = 1

__all__ = [
    "NoLiveSearchError",
    "MAX_SEARCH_TERMS",
    "MAX_QUERY_CHARS",
    "MAX_LIVE_QUERIES",
    "raise_if_no_live_search",
    "run_web_search",
    "_build_safe_query",
    "_build_query_list",
]


def _build_safe_query(search_terms: list[str]) -> str:
    """Build a short, bounded query string from a list of search terms."""
    normalized: list[str] = []
    for term in search_terms:
        term = term.strip()
        if not term:
            continue
        if len(term) > 80:
            normalized.append(" ".join(term.split()[:10]))
        else:
            normalized.append(term)

    capped_terms = normalized[:MAX_SEARCH_TERMS]
    query = " ".join(capped_terms)
    return query[:MAX_QUERY_CHARS]


def _build_query_list(
    search_terms: list[str],
    original_query: str = "",
    *,
    max_queries: int = MAX_LIVE_QUERIES,
) -> list[str]:
    """Facet list for the search agent (not separate HTTP calls)."""
    queries: list[str] = []
    seen: set[str] = set()

    def _add(q: str) -> None:
        q = " ".join((q or "").split()).strip()
        if not q:
            return
        q = q[:MAX_QUERY_CHARS]
        key = q.casefold()
        if key in seen:
            return
        seen.add(key)
        queries.append(q)

    if original_query:
        for a in extract_entity_anchors(original_query, max_anchors=5):
            _add(a)
        # Short primary subject line (not the whole English planner essay)
        anchors = extract_entity_anchors(original_query, max_anchors=2)
        if anchors:
            _add(anchors[0])
        else:
            _add(original_query)

    for term in search_terms or []:
        _add(term)

    return queries[: max(6, max_queries)]


def run_web_search(
    search_terms: list[str],
    router_instance=None,
    *,
    original_query: str = "",
    max_queries: int = MAX_LIVE_QUERIES,
    progress: ProgressCb = None,
) -> str:
    """One live multi-facet search; hard-abort if it admits no live search."""
    facets = _build_query_list(
        search_terms, original_query, max_queries=max(max_queries, 6)
    )
    focus = entity_focus_block(original_query or " ".join(search_terms[:3]))
    facet_block = "\n".join(f"- {f}" for f in facets) if facets else f"- {original_query}"

    if progress:
        progress("web search (live)… this can take 30–90s")
    logger.info("Web search: 1 live call, %d facet hints", len(facets))

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"{focus}\n"
                f"Full research topic:\n"
                f"{original_query or (facets[0] if facets else '')}\n\n"
                f"Run several live searches for these facets (same entity only):\n"
                f"{facet_block}\n\n"
                "Merge results into one structured dump. List unrelated hits under EXCLUDED. "
                "Include source URLs for every claim."
            ),
        },
    ]
    resp = run_role_raw(
        "deep_research",
        "web_search",
        messages=messages,
        router_instance=router_instance,
    )
    body = (resp.content or "").strip()
    raise_if_no_live_search(body)
    if not body:
        raise NoLiveSearchError(
            "La búsqueda en vivo no devolvió contenido utilizable."
        )
    if progress:
        progress(f"web search done ({len(body)} chars)")
    return body
