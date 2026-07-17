"""
Grounding agent for System B (Deep Research).

Plain cited prose from the model; GroundedReport built in Python.
Provider/model from config/model_router.yaml.
"""

from __future__ import annotations

from typing import Any

from agents.deep_research.entity_focus import entity_focus_block
from core.agent_runtime import run_role_raw
from core.search_guards import extract_urls, find_no_live_search_marker
from schemas.deep_research import GroundedReport

SYSTEM_PROMPT = """You are a precision grounding and verification assistant.
Your job is to read the provided search documents and write a DETAILED,
well-organized report that answers the user's query.

Depth requirements (use Markdown headings):
1. Identity — official/trade names, spelling variants, what is confirmed vs uncertain
2. Locations & contact — every address, phone, email, hours found (with source)
3. Online presence — website and social profiles ONLY if clearly the same entity
4. Services & specialty — specific treatments, equipment, languages if mentioned
5. Reputation — review scores, approximate counts, recurring praise/complaints
6. People & history — owners, dentists, founding year if present; else state gap
7. Accreditations / legal — registries, professional boards if any
8. Unverified or unrelated hits — anything that might be a different business
9. Information gaps — what the user asked for that sources do not cover

Rules:
- Cite sources naturally with URLs.
- Do NOT invent facts. Prefer "not found in sources" over guesses.
- Do NOT merge unrelated clinics or social accounts into the main profile.
- Keep maximum useful detail; do not collapse into a thin marketing blurb.
- If two sources disagree, report both sides.
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
                "Use only the search documents. Separate unrelated businesses clearly."
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

    return GroundedReport(content=resp.content.strip(), sources=sources)
