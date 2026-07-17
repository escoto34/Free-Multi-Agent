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
    collect_outbound_from_sources,
    extract_user_domains,
    fetch_outbound_presence_pages,
    fetch_user_primary_sources,
    format_linked_presence_fetch_block,
    format_outbound_presence_block,
    format_primary_source_block,
    outbound_presence_search_facets,
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
- The host may also list OUTBOUND PRESENCE channels discovered as real
  buttons/links on that site (WhatsApp wa.me phones, Instagram/Facebook/
  LinkedIn/TikTok/YouTube/X profile URLs, mailto, tel).
- The host may attach LINKED PRESENCE FETCHES of those social profile pages.
- Your job is NOT only the official page. You MUST also search the open web
  for related, third-party evidence about the SAME subject, AND for public
  content/posts on any social profile URLs the host discovered on the site.

In THIS single response, run MULTIPLE distinct live searches (several tool
calls) covering different facets, then merge the findings.

Required coverage (same subject only) — adapt facets to the topic:
A) Official digital presence (site:domain, bare domain) when a domain is known
B) Third-party listings / maps / business profiles / directories when relevant
C) Social or professional profiles clearly matching the subject
D) When OUTBOUND PRESENCE lists Instagram/Facebook/etc. URLs or handles:
   live-search those EXACT profile URLs and recent public posts / reels /
   about-bio content for the SAME handle (do not swap a different account)
E) Reviews / ratings / reputation when relevant
F) News, press, or professional mentions
G) Named people or related entities only if the user mentioned them
H) Brand / visual assets only if the user asked and real pages show them

Rules:
1. Search the EXACT subject the user named. Do not substitute a different
   organization, person, or brand with a similar name or the same place.
2. Do NOT stop after the official website. Always attempt open-web queries.
3. Phone numbers encoded in WhatsApp (wa.me / api.whatsapp.com) links on the
   official page ARE valid contact evidence — report them as WhatsApp numbers.
4. For every fact, include the source URL that actually returned it.
5. NEVER invent:
   - archive.org / Wayback snapshots or historical existence claims
   - emails, phone numbers, messaging handles, or coordinates
   - brand colors (#hex), font names, logo descriptions
   - social posts, captions, or follower counts you did not retrieve
   - any URL you did not actually retrieve via search tools
   unless a live result or the PRIMARY/OUTBOUND/LINKED blocks contain them.
6. If a result is a DIFFERENT entity, mark it as:
   EXCLUDED (unrelated): <name> — <why> — <url>
   and do NOT fold its details into the main subject.
7. Return a structured dump with sections:
   - Official website (live notes; host may also attach a fetch)
   - Contact from official buttons (WhatsApp phones, mailto, tel)
   - Social profiles & posts (handles found on site + what live search returned)
   - Third-party web findings (with URLs)
   - Confirmed facts (with URLs)
   - Locations (only strings present in sources)
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
MAX_FACET_HINTS: int = 22

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

    # Follow WhatsApp / Instagram / other channels linked from the official site
    outbound = collect_outbound_from_sources(primary)
    outbound_block = format_outbound_presence_block(outbound)
    social_facets = outbound_presence_search_facets(outbound, max_facets=10)
    if social_facets:
        # Prepend so live search prioritizes exact profile URLs / posts
        facets = list(dict.fromkeys([*social_facets, *facets]))[:MAX_FACET_HINTS]
        facet_block = "\n".join(f"- {f}" for f in facets) if facets else facet_block

    if progress and outbound:
        kinds = sorted({o.kind for o in outbound})
        progress(f"outbound channels on official page: {', '.join(kinds)}")

    if progress and any(o.kind not in ("whatsapp", "email", "phone", "maps") for o in outbound):
        progress("fetching linked social profile page(s)…")
    linked = fetch_outbound_presence_pages(outbound, max_fetch=4)
    linked_block = format_linked_presence_fetch_block(linked)
    linked_ok = sum(1 for L in linked if L.ok)
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

    if outbound:
        social_hint = (
            "\nOUTBOUND PRESENCE discovered on the official page (buttons/schema):\n"
            + "\n".join(
                f"- {o.kind}: {o.url}"
                + (f" handle=@{o.handle}" if o.handle else "")
                + (f" phone_digits={o.phone_digits}" if o.phone_digits else "")
                for o in outbound[:12]
            )
            + "\nYou MUST live-search each social profile URL/handle above and "
            "report public posts/bio only when tools return them. "
            "WhatsApp phone digits from wa.me links are already valid contact evidence.\n"
        )
    else:
        social_hint = ""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"{focus}\n"
                f"{profile_block}\n"
                f"Full research topic:\n"
                f"{original_query or (facets[0] if facets else '')}\n"
                f"{domain_hint}"
                f"{social_hint}\n"
                f"Run several live searches for these facets (same subject only).\n"
                f"Bias coverage toward the active research profile "
                f"({profile.label()}).\n"
                f"Include official-site (if any), outbound social profiles/posts, "
                f"and third-party / open-web facets:\n"
                f"{facet_block}\n\n"
                "Merge into one structured dump with dedicated sections for "
                "'Contact from official buttons', 'Social profiles & posts', and "
                "'Third-party web findings', with real source URLs. "
                "List unrelated hits under EXCLUDED. "
                "If you cannot verify contact or posts, list them under "
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

    extras = []
    if outbound_block:
        extras.append(outbound_block)
    if linked_block:
        extras.append(linked_block)
    extras_joined = ("\n\n".join(extras) + "\n\n") if extras else ""

    merged = (
        f"{primary_block}\n\n"
        f"{extras_joined}"
        "=== LIVE WEB SEARCH DUMP (third-party + open web; must be used) ===\n"
        f"{body}\n"
        "=== END LIVE DUMP ==="
    )
    return merged
