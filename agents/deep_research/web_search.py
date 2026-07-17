"""
Web Search agent for System B (Deep Research).

Provider/model from config/model_router.yaml (typically groq/compound-mini).

1. Fetches user-provided official URLs (PRIMARY SOURCES) via HTTP.
2. One live compound multi-facet search (entity-anchored).
3. Merges primary + live dump for grounding.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from agents.deep_research.entity_focus import entity_focus_block, extract_entity_anchors
from agents.deep_research.source_fetch import (
    extract_user_domains,
    fetch_user_primary_sources,
    format_primary_source_block,
)
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
2. If the user named an official website/domain, you MUST search it first
   (site:domain and the bare domain). Treat it as the primary digital property.
3. Collect concrete facts ONLY from live results: legal/trade names, addresses,
   phones, emails, website, social profiles that clearly belong to the subject,
   services, hours, staff/doctors if named, reviews, ownership/history,
   accreditations, news, directories.
4. For every fact, include the source URL that actually returned it.
5. NEVER invent:
   - Wayback Machine / web.archive.org snapshots or "archives from 20XX"
   - emails, phone numbers, WhatsApp, or GPS coordinates
   - brand colors (#hex), font names, logo descriptions
   unless a live result or the PRIMARY SOURCES block contains them.
6. If a result is a DIFFERENT organization, mark it as:
   EXCLUDED (unrelated): <name> — <why> — <url>
   and do NOT fold its contact details into the main subject.
7. Prefer primary sources: official website, Google Business / Maps, Facebook
   page whose title matches the entity, government or professional registries.
8. For brand-identity requests: report only logo/colors/type found on real pages
   or assets; otherwise list as gaps.
9. Return a structured dump with sections:
   - Confirmed facts (with URLs)
   - Contact & locations (only strings present in sources)
   - Official website findings
   - Brand / visual identity (only if evidenced)
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

    # Official domains first
    for d in extract_user_domains(original_query or ""):
        _add(d)
        _add(f"site:{d}")
        _add(f"{d} contacto OR contact OR teléfono OR email")

    if original_query:
        for a in extract_entity_anchors(original_query, max_anchors=5):
            _add(a)
        anchors = extract_entity_anchors(original_query, max_anchors=2)
        if anchors:
            _add(anchors[0])
        else:
            _add(original_query)

    for term in search_terms or []:
        _add(term)

    return queries[: max(8, max_queries)]


def run_web_search(
    search_terms: list[str],
    router_instance=None,
    *,
    original_query: str = "",
    max_queries: int = MAX_LIVE_QUERIES,
    progress: ProgressCb = None,
) -> str:
    """Primary URL fetch + one live multi-facet search; hard-abort if no live search."""
    facets = _build_query_list(
        search_terms, original_query, max_queries=max(max_queries, 6)
    )
    focus = entity_focus_block(original_query or " ".join(search_terms[:3]))
    facet_block = "\n".join(f"- {f}" for f in facets) if facets else f"- {original_query}"

    # --- Primary sources (user-provided domains/URLs) ---
    if progress:
        progress("fetching user-provided official page(s)…")
    primary = fetch_user_primary_sources(original_query or "", max_urls=3)
    primary_block = format_primary_source_block(primary)
    ok_count = sum(1 for p in primary if p.ok)
    fail_count = sum(1 for p in primary if not p.ok and p.url)
    logger.info(
        "Primary sources: %d ok, %d failed, domains=%s",
        ok_count,
        fail_count,
        extract_user_domains(original_query or ""),
    )
    if progress:
        progress(f"primary sources: {ok_count} ok / {fail_count} failed")

    if progress:
        progress("web search (live)… this can take 30–90s")
    logger.info("Web search: 1 live call, %d facet hints", len(facets))

    domain_hint = ""
    domains = extract_user_domains(original_query or "")
    if domains:
        domain_hint = (
            "\nMANDATORY: First search the official domain(s): "
            + ", ".join(domains)
            + ". Use site: queries. Quote any contact/brand strings found there.\n"
        )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"{focus}\n"
                f"Full research topic:\n"
                f"{original_query or (facets[0] if facets else '')}\n"
                f"{domain_hint}\n"
                f"Run several live searches for these facets (same entity only):\n"
                f"{facet_block}\n\n"
                "Merge results into one structured dump. List unrelated hits under EXCLUDED. "
                "Include source URLs for every claim. "
                "If you cannot find a phone/email/color, list it under Gaps — do not invent."
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

    # Primary evidence always precedes the model dump for grounding
    merged = f"{primary_block}\n\n=== LIVE WEB SEARCH DUMP ===\n{body}\n=== END LIVE DUMP ==="
    return merged
