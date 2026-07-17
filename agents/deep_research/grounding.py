"""
Grounding agent for System B (Deep Research).

Plain cited prose from the model; GroundedReport built in Python.
Provider/model from config/model_router.yaml.
"""

from __future__ import annotations

from typing import Any, Optional

from agents.deep_research.entity_focus import entity_focus_block
from agents.deep_research.research_types import (
    ResearchProfile,
    classify_research,
    report_outline_hints,
    research_profile_block,
)
from core.agent_runtime import run_role_raw
from core.search_guards import (
    extract_urls,
    find_no_live_search_marker,
    scrub_ungrounded_claims,
)
from schemas.deep_research import GroundedReport

SYSTEM_PROMPT = """You are a precision grounding and verification assistant.
Your job is to read the provided search documents and write a DETAILED,
well-organized report that answers the user's query.

Documents may have several parts:
1) PRIMARY SOURCES — HTTP-fetched official pages the user named (highest trust).
2) OUTBOUND PRESENCE — WhatsApp phones / social handles decoded from real
   buttons and schema on those pages (valid contact evidence).
3) LINKED PRESENCE FETCHES — HTTP attempts on social profile pages discovered
   on the official site (may be partial/login-walled).
4) LIVE WEB SEARCH DUMP — open-web / third-party results (Maps, social posts,
   directories, news, reviews). Integrate all parts; do not write a report that
   only paraphrases the official homepage if other blocks have findings.

Depth requirements (use Markdown headings; skip sections that do not apply):
1. Identity — names, spelling variants, confirmed vs uncertain
2. Official website findings — from PRIMARY SOURCES (+ live notes about the domain)
3. Contact from official buttons — WhatsApp (wa.me) phones, mailto, tel
4. Social profiles & posts — handles/URLs found on site + live/linked findings
5. Third-party web findings — listings, maps, news, reviews (with URLs)
6. Locations — ONLY strings that appear VERBATIM in documents
7. Brand / visual identity — only if present in documents and relevant to the query
8. Offerings / products / services — if mentioned
9. Reputation — scores only if present
10. People & history — only if present; years ONLY if dated in sources
11. Unverified or unrelated hits
12. Information gaps — including "no posts retrieved" when social fetch/search thin

PRIMARY SOURCES may include a "STRUCTURED EXTRACTS" block (JSON-LD, meta/og,
CSS hex colors, contact/social hrefs, logo/image URLs) parsed literally from
the HTML. Prefer STRUCTURED EXTRACTS + OUTBOUND PRESENCE for brand colors,
logos, WhatsApp phones, and social profile URLs — still do not invent beyond
what those blocks list.

STRICT RULES:
- Cite only URLs that appear in the documents (copy them exactly).
- Do NOT invent facts, emails, phones, archive years, hex colors, fonts, logos,
  or citation URLs.
- Do NOT invent web.archive.org links.
- Do NOT merge unrelated entities or social accounts into the main subject.
- If PRIMARY FETCH FAILED, state that clearly.
- If LIVE DUMP is thin, say what open-web facets were missing — do not invent hits.
- Keep maximum useful detail, but only evidenced detail.
- Adapt emphasis to the RESEARCH PROFILE (purpose/depth/data/design) without inventing.
  For applied website/brand rebuilds, emphasize Brand/visual + contact + offerings.
"""


def _extract_sources_from_citations(raw_response: Any) -> list[str]:
    """Best-effort extraction of source URLs from Cohere's native citations."""
    sources: list[str] = []
    try:
        message = getattr(raw_response, "message", None)
        citations = getattr(message, "citations", None) if message else None
        if citations:
            for citation in citations:
                sub_sources = getattr(citation, "sources", None) or []
                for src in sub_sources:
                    doc = getattr(src, "document", None)
                    if doc:
                        url = (
                            doc.get("url")
                            if isinstance(doc, dict)
                            else getattr(doc, "url", None)
                        )
                        if url:
                            sources.append(url)
    except Exception:
        pass
    return sources


def run_grounding(
    query: str,
    search_results: str,
    router_instance=None,
    *,
    research_profile: Optional[ResearchProfile] = None,
) -> GroundedReport:
    """Ground the query against search_results; return prose + sources."""
    if not search_results or not search_results.strip():
        raise ValueError(
            "Fallo en Grounding: Los resultados de búsqueda web están vacíos. "
            "No se puede realizar la verificación de datos (grounding) sin documentos de origen."
        )

    marker = find_no_live_search_marker(search_results)
    if marker is not None:
        raise ValueError(
            "El paso de búsqueda no devolvió resultados verificados en vivo — "
            "abortando para evitar generar un reporte no fundamentado"
        )

    profile = research_profile or classify_research(query)
    focus = entity_focus_block(query)
    profile_block = research_profile_block(profile)
    outline = report_outline_hints(profile)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"{focus}\n"
                f"{profile_block}\n"
                f"{outline}\n"
                f"Write a verified, detailed, well-cited report answering:\n{query}\n\n"
                "Use ONLY the search documents. Cover BOTH when present:\n"
                "- PRIMARY SOURCES (official site fetch)\n"
                "- LIVE WEB SEARCH DUMP (third-party / open web)\n"
                "Structure the report for the active research profile "
                f"({profile.label()}). "
                "Separate unrelated entities clearly. "
                "Any contact detail or citation URL not literally in the "
                "documents goes under Gaps / is omitted."
            ),
        },
    ]
    documents = [{"data": {"text": search_results}}]

    resp = run_role_raw(
        "deep_research",
        "grounding",
        messages=messages,
        router_instance=router_instance,
        documents=documents,
        max_tokens=8192,
    )

    sources = _extract_sources_from_citations(resp.raw_response)
    if not sources:
        sources = extract_urls(search_results, limit=20)

    # Drop abbreviation junk (https://e.g) and non-source vocabulary hosts
    try:
        from agents.deep_research.source_fetch import is_plausible_source_url

        sources = [s for s in sources if is_plausible_source_url(s)]
    except Exception:
        sources = [s for s in sources if "://" in (s or "") and not s.lower().rstrip("/").endswith(("e.g", "i.e", "u.s"))]

    content = (resp.content or "").strip()
    content, sources, _notes = scrub_ungrounded_claims(
        content, search_results, sources=sources
    )
    # Re-inject successful PRIMARY fetches the model may have denied or omitted
    try:
        from agents.deep_research.source_fetch import merge_host_verified_primary

        content, sources = merge_host_verified_primary(
            content, sources, search_results
        )
    except Exception:
        pass
    return GroundedReport(content=content, sources=sources)
