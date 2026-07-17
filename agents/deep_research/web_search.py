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
    entity_focus_block,
    extract_entity_anchors,
    extract_location_phrases,
    extract_name_variants,
)
from agents.deep_research.research_types import (
    ResearchProfile,
    classify_research,
    research_profile_block,
    search_facet_hints,
)
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

IMPORTANT CONTEXT:
- The host app ALREADY HTTP-fetched any official site the user named.
  That content will be attached as PRIMARY SOURCES for grounding.
- Your job is NOT only the official page. You MUST also search the open web
  for related, third-party evidence about the SAME subject.

In THIS single response, run MULTIPLE distinct live searches (several tool
calls) covering different facets, then merge the findings.

Required coverage (same subject only) — adapt facets to the topic:
A) Official digital presence (site:domain, bare domain) when a domain is known
B) Third-party listings / maps / business profiles / directories when relevant
C) Social or professional profiles clearly matching the subject
D) Reviews / ratings / reputation when relevant
E) News, press, or professional mentions
F) Named people or related entities only if the user mentioned them
G) Brand / visual assets only if the user asked and real pages show them

Rules:
1. Search the EXACT subject the user named. Do not substitute a different
   organization, person, or brand with a similar name or the same place.
2. Do NOT stop after the official website. Always attempt open-web queries.
3. For every fact, include the source URL that actually returned it.
4. NEVER invent:
   - archive.org / Wayback snapshots or historical existence claims
   - emails, phone numbers, messaging handles, or coordinates
   - brand colors (#hex), font names, logo descriptions
   - any URL you did not actually retrieve via search tools
   unless a live result or the PRIMARY SOURCES block contains them.
5. If a result is a DIFFERENT entity, mark it as:
   EXCLUDED (unrelated): <name> — <why> — <url>
   and do NOT fold its details into the main subject.
6. Return a structured dump with sections:
   - Official website (live notes; host may also attach a fetch)
   - Third-party web findings (with URLs)
   - Confirmed facts (with URLs)
   - Contact & locations (only strings present in sources)
   - Brand / visual identity (only if evidenced and relevant)
   - Offerings / products / services (if relevant)
   - Reputation / reviews (if any)
   - History / people / ownership (if any)
   - EXCLUDED unrelated hits
   - Gaps (what you could not verify on the open web)
"""

MAX_SEARCH_TERMS: int = 8
MAX_QUERY_CHARS: int = 150
MAX_LIVE_QUERIES: int = 1
MAX_FACET_HINTS: int = 16

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
    router_instance=None,
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
    focus = entity_focus_block(original_query or " ".join(search_terms[:3]))
    profile_block = research_profile_block(profile)
    facet_block = "\n".join(f"- {f}" for f in facets) if facets else f"- {original_query}"

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
        progress("web search (live, multi-facet)… this can take 30–90s")
    logger.info("Web search: 1 live call, %d facet hints", len(facets))

    domains = extract_user_domains(original_query or "")
    if domains:
        domain_hint = (
            "\nOfficial domain(s) already fetched by the host: "
            + ", ".join(domains)
            + ".\n"
            "Still run site: searches if useful, BUT you MUST also search the open web "
            "for the same subject (listings, social, news, reviews as applicable).\n"
            "Do not limit your dump to the official homepage.\n"
        )
    else:
        domain_hint = (
            "\nNo official domain was named — rely fully on multi-facet live search.\n"
        )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"{focus}\n"
                f"{profile_block}\n"
                f"Full research topic:\n"
                f"{original_query or (facets[0] if facets else '')}\n"
                f"{domain_hint}\n"
                f"Run several live searches for these facets (same subject only).\n"
                f"Bias coverage toward the active research profile "
                f"({profile.label()}).\n"
                f"Include BOTH official-site (if any) and third-party / open-web facets:\n"
                f"{facet_block}\n\n"
                "Merge into one structured dump with a dedicated "
                "'Third-party web findings' section and real source URLs. "
                "List unrelated hits under EXCLUDED. "
                "If you cannot verify contact or other claimed details, list them under "
                "Gaps — do not invent. Never invent URLs you did not retrieve."
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

    merged = (
        f"{primary_block}\n\n"
        "=== LIVE WEB SEARCH DUMP (third-party + open web; must be used) ===\n"
        f"{body}\n"
        "=== END LIVE DUMP ==="
    )
    return merged
