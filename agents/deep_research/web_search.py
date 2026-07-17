"""
Web Search agent for System B (Deep Research).

Provider/model from config/model_router.yaml (typically groq/compound-mini).
Runs several entity-anchored live queries and concatenates results so the
report can go deeper without mixing unrelated businesses.
"""

from __future__ import annotations

from agents.deep_research.entity_focus import entity_focus_block, extract_entity_anchors
from core.agent_runtime import run_role_raw
from core.search_guards import NoLiveSearchError, raise_if_no_live_search

SYSTEM_PROMPT = """You are a live web-search research agent.
You MUST use live web search tools (not training memory alone).

Rules:
1. Search the EXACT subject the user named. Do not substitute a different clinic,
   hospital, or brand with a similar name or the same city.
2. Collect as many concrete facts as you can: legal/trade names, addresses,
   phones, emails, website, social profiles that clearly belong to the subject,
   services, hours, staff/doctors if named, reviews (with ratings/counts when
   available), ownership/history, accreditations, news, and directories.
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
MAX_LIVE_QUERIES: int = 4

# Re-export for graphs/tests that import from this module.
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
    """Distinct live-search queries: original topic first, then facets."""
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
        _add(original_query)
        for a in extract_entity_anchors(original_query, max_anchors=4):
            _add(a)

    for term in search_terms or []:
        _add(term)

    # If still only one very long blob, keep it; else cap count.
    return queries[: max(1, max_queries)]


def run_web_search(
    search_terms: list[str],
    router_instance=None,
    *,
    original_query: str = "",
    max_queries: int = MAX_LIVE_QUERIES,
) -> str:
    """Run multiple live searches; hard-abort if none look like real search."""
    queries = _build_query_list(
        search_terms, original_query, max_queries=max_queries
    )
    focus = entity_focus_block(original_query or " ".join(search_terms[:3]))
    parts: list[str] = []
    live_ok = 0

    for i, q in enumerate(queries, 1):
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"{focus}\n"
                    f"Full research topic:\n{original_query or q}\n\n"
                    f"Live-search query {i}/{len(queries)}:\n{q}\n\n"
                    "Return only material about this subject; list unrelated hits "
                    "under EXCLUDED. Include source URLs for every claim."
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
        if not body:
            continue
        # Per-query: if this slice admits no live search, skip it but keep others.
        try:
            raise_if_no_live_search(body)
            live_ok += 1
        except NoLiveSearchError:
            parts.append(
                f"===== SEARCH {i}/{len(queries)}: {q} =====\n"
                f"(skipped — model admitted no live search)\n{body[:500]}"
            )
            continue
        parts.append(f"===== SEARCH {i}/{len(queries)}: {q} =====\n{body}")

    if live_ok == 0:
        combined = "\n\n".join(parts) if parts else "(empty search)"
        raise_if_no_live_search(combined)
        raise NoLiveSearchError(
            "Ninguna de las búsquedas en vivo devolvió resultados verificados."
        )

    return "\n\n".join(parts)
