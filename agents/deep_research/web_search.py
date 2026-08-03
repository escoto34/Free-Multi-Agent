"""
Web Search agent for System B (Deep Research).

Provider/model from config/model_router.yaml (typically groq/compound-mini).
The deep_research.web_search role backs ONE bounded LLM call for query
expansion (turn a vague topic into concrete DuckDuckGo facets) via
:func:`expand_query_facets`; that call is optional — on quota/network failure
the heuristic facet builder is used unchanged.

1. Fetches user-provided official URLs (PRIMARY SOURCES) via HTTP.
2. Expands the topic into concrete facets, then one live multi-facet search next.
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
from agents.deep_research.contracts import SourceResultStatus
from agents.deep_research.research_types import (
    ResearchProfile,
    classify_research,
    search_facet_hints,
)
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
from core.agent_config import get_agent_config
from core.router import call_agent, QuotaExhaustedError

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
    "expand_query_facets",
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


# The deep_research.web_search role (groq/compound-mini, ~250 RPD) is wired here
# for query expansion: one bounded LLM call that turns a vague topic into more
# concrete DDG facets than the heuristic builder alone. It is an optimization —
# if quota/key/parse fails we fall back to the heuristic facets unchanged.
_QUERY_EXPANSION_SYSTEM = (
    "You are a web-search query planner. Given ONE vague research topic, emit "
    "up to {max_facets} concise DuckDuckGo search queries that surface concrete, "
    "factual results (official site, news, reviews, contact, map listing). "
    "Rules: reply with ONLY the queries, one per line; no numbering, bullets, "
    "quotes or commentary; lowercase; each under 100 characters; add a "
    "location qualifier when the topic implies one; never repeat the same "
    "keywords across lines."
)
_QUERY_LINE_RE = re.compile(r"\A[\s\d\-.•]*\s?(.+?)\s*\Z")


def _parse_expanded_facets(
    raw: str,
    *,
    existing: Optional[list[str]] = None,
    max_facets: int = 6,
) -> list[str]:
    """Parse a free-form LLM query-expansion reply into a bounded facet list."""
    seen: set[str] = set()
    existing_keys = {q.casefold() for q in (existing or [])}
    out: list[str] = []
    for line in (raw or "").splitlines():
        m = _QUERY_LINE_RE.match(line or "")
        q = (m.group(1) if m else line).strip()
        if not q or len(q) < 4 or len(q) > MAX_QUERY_CHARS:
            continue
        key = q.casefold()
        if key in seen or key in existing_keys:
            continue
        seen.add(key)
        out.append(q)
        if len(out) >= max_facets:
            break
    return out


def expand_query_facets(
    topic: str,
    *,
    existing: Optional[list[str]] = None,
    max_facets: int = 6,
) -> list[str]:
    """One bounded deep_research.web_search call -> better facets.

    Never raises and never blocks the pipeline: on any LLM failure (empty
    completion, quota exhausted, network, unparseable reply) it returns ``[]``
    so the html heuristic facets are used unchanged.
    """
    topic = (topic or "").strip()
    if not topic:
        return []
    try:
        cfg = get_agent_config("deep_research", "web_search")
        resp = call_agent(
            provider=cfg["provider"],
            model=cfg["model"],
            messages=[
                {
                    "role": "system",
                    "content": _QUERY_EXPANSION_SYSTEM.format(max_facets=max_facets),
                },
                {"role": "user", "content": topic},
            ],
            fallback=cfg.get("fallback"),
            max_retries=1,
        )
    except Exception as exc:
        logger.warning(
            "web_search query expansion skipped (%s) — using heuristic facets",
            type(exc).__name__ if not isinstance(exc, QuotaExhaustedError) else "quota",
        )
        return []
    return _parse_expanded_facets(
        resp.content or "", existing=existing, max_facets=max_facets
    )


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

    # WAVE-11B: the web_search role is wired for query expansion — one bounded
    # call that turns the vague topic into more concrete facets. It is optional:
    # on any LLM failure the heuristic facets below are used unchanged.
    if original_query:
        expanded = expand_query_facets(original_query, existing=facets, max_facets=6)
        if expanded:
            facets = list(dict.fromkeys([*expanded, *facets]))[:MAX_FACET_HINTS]

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
