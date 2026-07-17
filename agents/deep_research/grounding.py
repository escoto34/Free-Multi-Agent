"""
Grounding agent for System B (Deep Research).

Plain cited prose from the model; GroundedReport built in Python.
Provider/model from config/model_router.yaml.
"""

from __future__ import annotations

from typing import Any

from agents.deep_research.entity_focus import entity_focus_block
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

Documents may include a "PRIMARY SOURCES" block (HTTP-fetched official pages
named by the user). Those are highest-trust evidence.

Depth requirements (use Markdown headings):
1. Identity — official/trade names, spelling variants, what is confirmed vs uncertain
2. Locations & contact — ONLY addresses/phones/emails that appear VERBATIM in documents
3. Online presence — website and social profiles ONLY if clearly the same entity
4. Brand / visual identity — logo, colors, fonts ONLY if present in documents (e.g. CSS,
   page text, asset URLs). Never invent teal palettes or Montserrat/Open Sans.
5. Services & specialty — specific treatments if mentioned
6. Reputation — review scores only if present
7. People & history — staff names if present; founding years ONLY if dated in sources
8. Unverified or unrelated hits — anything that might be a different business
9. Information gaps — what was asked but NOT found (including failed primary fetches)

STRICT RULES:
- Cite sources with URLs that appear in the documents.
- Do NOT invent facts. Prefer "not found in verified sources" over guesses.
- Do NOT invent web.archive.org / Wayback links or claim the site existed in 2022/2023
  unless an archive URL is present in the documents with that year.
- Do NOT invent email, phone, WhatsApp, or GPS coordinates.
- Do NOT invent brand colors (#hex), typography, or logo geometry.
- Do NOT merge unrelated clinics or social accounts into the main profile.
- If PRIMARY FETCH FAILED for the official domain, state that clearly.
- Keep maximum useful detail for redesigning a website, but only evidenced detail.
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

    focus = entity_focus_block(query)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"{focus}\n"
                f"Write a verified, detailed, well-cited report answering:\n{query}\n\n"
                "Use ONLY the search documents (PRIMARY SOURCES + live dump). "
                "Separate unrelated businesses clearly. "
                "Any contact or brand detail not literally in the documents goes under Gaps."
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

    content = (resp.content or "").strip()
    content, sources, _notes = scrub_ungrounded_claims(
        content, search_results, sources=sources
    )
    return GroundedReport(content=content, sources=sources)
