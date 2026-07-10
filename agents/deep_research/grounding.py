"""
Grounding agent for System B (Deep Research).

Plain cited prose from the model; GroundedReport built in Python.
Provider/model from config/model_router.yaml.
"""

from __future__ import annotations

from typing import Any

from core.agent_runtime import run_role_raw
from core.search_guards import extract_urls, find_no_live_search_marker
from schemas.deep_research import GroundedReport

SYSTEM_PROMPT = """You are a precision grounding and verification assistant.
Your job is to read the provided search documents and write a detailed,
well-organized report that answers the user's query, citing the documents
naturally as you go (e.g. "according to [source]..."). Write in clear
prose/Markdown. Do NOT invent facts that are not supported by the provided
documents — if the documents don't cover something the query asks for,
say so explicitly instead of guessing.
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

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Write a verified, well-cited report answering this query: {query}",
        },
    ]
    documents = [{"data": {"text": search_results}}]

    resp = run_role_raw(
        "deep_research",
        "grounding",
        messages=messages,
        router_instance=router_instance,
        documents=documents,
        max_tokens=4096,
    )

    sources = _extract_sources_from_citations(resp.raw_response)
    if not sources:
        sources = extract_urls(search_results, limit=10)

    return GroundedReport(content=resp.content.strip(), sources=sources)
