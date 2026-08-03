"""
Web Search agent for System B (Deep Research).

Provider/model from config/model_router.yaml (typically groq/compound-mini).

1. Fetches user-provided official URLs (PRIMARY SOURCES) via HTTP.
2. One live compound multi-facet search — official site *and* third-party web.
3. Merges primary + live dump for grounding.

Domain-agnostic: works for any research subject (business, person, product, topic).
"""

from __future__ import annotations

import logging
import re
from typing import Callable, Optional

from agents.deep_research.entity_focus import (
    extract_entity_anchors,
    extract_location_phrases,
    extract_name_variants,
)
from agents.deep_research.research_types import (
    ResearchProfile,
    classify_research,
    search_facet_hints,
)
from agents.deep_research.contracts import SourceResultStatus
from agents.deep_research.source_fetch import (
    collect_outbound_from_sources,
    extract_user_domains,
    fetch_outbound_presence_pages,
    fetch_search_documents,
    fetch_user_primary_sources,
    format_linked_presence_fetch_block,
    format_outbound_presence_block,
    format_primary_source_block,
    outbound_presence_search_facets,
)

logger = logging.getLogger(__name__)

ProgressCb = Optional[Callable[[str], None]]

MAX_SEARCH_TERMS: int = 8
MAX_QUERY_CHARS: int = 150
MAX_LIVE_QUERIES: int = 1
# Keep facet list short: long prompts slow the live-search model and dilute tool use.
MAX_FACET_HINTS: int = 12

__all__ = [
    "MAX_SEARCH_TERMS",
    "MAX_QUERY_CHARS",
    "MAX_LIVE_QUERIES",
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


def _related_web_facets(original_query: str, variants: list[str]) -> list[str]:
    """Generic third-party / open-web facet strings (beyond site:domain)."""
    facets: list[str] = []
    main = variants[0] if variants else ""
    locs = extract_location_phrases(original_query or "")
    loc = " ".join(locs[:2]).strip()

    if not main:
        # Fall back to a short slice of the topic
        main = " ".join((original_query or "").split()[:6]).strip()
    if not main:
        return facets

    if loc:
        facets.append(f"{main} {loc}")
        facets.append(f'"{main}" {loc}')
        facets.append(f"{main} {loc} contact OR reviews")
    else:
        facets.append(f'"{main}"')
        facets.append(f"{main} contact OR official")

    # Industry-agnostic open-web facets
    facets.extend(
        [
            f"{main} reviews OR ratings",
            f"{main} news OR press OR media",
            f"{main} LinkedIn OR Facebook OR Instagram OR profile",
            f"{main} directory OR listing OR map",
        ]
    )

    if re.search(
        r"\b(marca|brand|logo|identidad|visual\s+identity|"
        r"imagen\s+de\s+marca|branding)\b",
        original_query or "",
        re.I,
    ):
        facets.append(f"{main} logo brand identity" + (f" {loc}" if loc else ""))

    return facets


def _build_query_list(
    search_terms: list[str],
    original_query: str = "",
    *,
    max_queries: int = MAX_LIVE_QUERIES,
    profile: Optional[ResearchProfile] = None,
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

    variants = extract_name_variants(original_query or "")
    main = variants[0] if variants else ""
    prof = profile or classify_research(original_query or "")

    # 1) Official domains when the user named one
    for d in extract_user_domains(original_query or ""):
        _add(d)
        _add(f"site:{d}")

    # 2) Generic third-party / open-web facets
    for f in _related_web_facets(original_query or "", variants):
        _add(f)

    # 3) Typology-driven facets (purpose/depth/data/design)
    for f in search_facet_hints(prof, subject=main):
        _add(f)

    # 4) Entity anchors (name + location from the query)
    if original_query:
        for a in extract_entity_anchors(original_query, max_anchors=6):
            _add(a)

    # 5) Compressor / LLM keywords last
    for term in search_terms or []:
        _add(term)

    limit = max(MAX_FACET_HINTS, max_queries, 8)
    return queries[:limit]


def run_web_search(
    search_terms: list[str],
    *,
    original_query: str = "",
    max_queries: int = MAX_LIVE_QUERIES,
    progress: ProgressCb = None,
    research_profile: Optional[ResearchProfile] = None,
) -> str:
    """Primary URL fetch + one live multi-facet search; hard-abort if no live search."""
    profile = research_profile or classify_research(original_query or "")
    facets = _build_query_list(
        search_terms,
        original_query,
        max_queries=max(max_queries, 6),
        profile=profile,
    )

    if progress:
        progress("fetching user-provided official page(s)…")
    primary = fetch_user_primary_sources(original_query or "", max_urls=3)
    primary_block = format_primary_source_block(primary)
    ok_count = sum(
        1 for p in primary if p.status is SourceResultStatus.SUCCESS
    )
    fail_count = sum(
        1 for p in primary if p.status is not SourceResultStatus.SUCCESS and p.url
    )
    logger.info(
        "Primary sources: %d ok, %d failed, domains=%s",
        ok_count,
        fail_count,
        extract_user_domains(original_query or ""),
    )
    if progress:
        progress(f"primary sources: {ok_count} ok / {fail_count} failed")

    # Follow WhatsApp / Instagram / other channels linked from the official site
    outbound = collect_outbound_from_sources(primary)
    outbound_block = format_outbound_presence_block(outbound)
    social_facets = outbound_presence_search_facets(outbound, max_facets=6)
    if social_facets:
        # Prepend so live search prioritizes exact profile URLs / posts
        facets = list(dict.fromkeys([*social_facets, *facets]))[:MAX_FACET_HINTS]

    if progress and outbound:
        kinds = sorted({o.kind for o in outbound})
        progress(f"outbound channels on official page: {', '.join(kinds)}")

    # Linked social HTTP fetches: max 2, short timeout, parallel (login walls often empty)
    if progress and any(o.kind not in ("whatsapp", "email", "phone", "maps") for o in outbound):
        progress("fetching linked social profile page(s)…")
    linked = fetch_outbound_presence_pages(outbound, max_fetch=2, timeout=8.0)
    linked_block = format_linked_presence_fetch_block(linked)
    linked_ok = sum(
        1 for L in linked if L.status is SourceResultStatus.SUCCESS
    )
    if linked:
        logger.info(
            "Linked presence fetches: %d ok / %d total; outbound=%d",
            linked_ok,
            len(linked),
            len(outbound),
        )
        if progress:
            progress(f"linked social fetches: {linked_ok}/{len(linked)} ok")

    if progress:
        progress("real web search (DuckDuckGo + page fetches)…")
    logger.info("Real web search: %d facet queries", len(facets))

    real_search = fetch_search_documents(
        facets,
        max_results_per_query=5,
        max_fetches=8,
        timeout=12.0,
        max_chars=8000,
    )
    if not real_search or not real_search.strip():
        logger.warning("Real web search returned no results for any facet")
        real_search = (
            "=== REAL WEB SEARCH RESULTS ===\n"
            "(automated search returned no results for the given queries)\n"
            "=== END REAL SEARCH ==="
        )

    if progress:
        progress(f"real web search done ({len(real_search)} chars)")

    extras = []
    if outbound_block:
        extras.append(outbound_block)
    if linked_block:
        extras.append(linked_block)
    extras_joined = ("\n\n".join(extras) + "\n\n") if extras else ""

    merged = (
        f"{primary_block}\n\n"
        f"{extras_joined}"
        f"{real_search}\n"
    )
    return merged
