"""
Grounding agent using PydanticAI definition.
Performs native grounding and citation extraction using Cohere's documents parameter.

DESIGN NOTE (fix for persistent HTTP 422 NO_VALID_RESPONSE_GENERATED):
Previously this module asked the model to BOTH use Cohere's native
`documents` grounding AND self-format a full JSON object (including a
"sources" list it had to invent itself). Those two things fight each other:
`documents` triggers Cohere's own internal citation mechanism, and asking
the model to simultaneously wrap everything in a hand-rolled JSON schema
appears to be what was causing Cohere to reject the generation outright.

The fix: ask the model for a plain, well-cited *text* report (letting
`documents`/citations work natively), then build the `GroundedReport`
Pydantic object ourselves in Python from (a) the returned text and (b) the
real citation data in the raw Cohere response — instead of asking the model
to author the JSON wrapper itself. This removes an entire class of
"model produced invalid/conflicting JSON" failures.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from pydantic_ai import Agent

from core.router import call_agent
from schemas.deep_research import GroundedReport

SYSTEM_PROMPT = """You are a precision grounding and verification assistant.
Your job is to read the provided search documents and write a detailed,
well-organized report that answers the user's query, citing the documents
naturally as you go (e.g. "according to [source]..."). Write in clear
prose/Markdown. Do NOT invent facts that are not supported by the provided
documents — if the documents don't cover something the query asks for,
say so explicitly instead of guessing.
"""

# Official PydanticAI Agent definition
grounding_agent = Agent(
    "test",
    output_type=GroundedReport,
    system_prompt=SYSTEM_PROMPT,
)

_URL_PATTERN = re.compile(r"https?://[^\s\)\]\"']+")


def _extract_sources_from_citations(raw_response: Any) -> list[str]:
    """Best-effort extraction of source URLs from Cohere's native citations.

    Cohere ClientV2 populates ``response.message.citations`` when
    ``documents`` is used. The exact shape can vary by SDK version, so this
    is defensive: it tries a few reasonable attribute paths and falls back
    to an empty list rather than raising.
    """
    sources: list[str] = []
    try:
        message = getattr(raw_response, "message", None)
        citations = getattr(message, "citations", None) if message else None
        if citations:
            for citation in citations:
                # citation.sources is typically a list of objects with an
                # "id" or document reference; try a few common shapes.
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
        # Never let citation-extraction quirks break the pipeline —
        # we still have the fallback below.
        pass
    return sources


def _extract_sources_from_search_text(search_results: str) -> list[str]:
    """Fallback: pull raw URLs directly out of the search-results text.

    Used when native citation extraction above doesn't yield anything —
    still grounded in real data, since search_results itself already came
    from a real web search, not from the model's own generation.
    """
    return list(dict.fromkeys(_URL_PATTERN.findall(search_results)))[:10]


def run_grounding(
    query: str,
    search_results: str,
    router_instance=None,
) -> GroundedReport:
    """Run the Grounding step to produce a grounded report using Cohere's native grounding.

    Injects search_results into the `documents` parameter. The model is
    asked for plain cited prose (not a self-authored JSON wrapper); the
    GroundedReport object is constructed in Python afterwards.

    Validates that search_results is not empty, and hard-aborts if the
    search results self-admit that no real live search was performed.
    """
    if not search_results or not search_results.strip():
        raise ValueError(
            "Fallo en Grounding: Los resultados de búsqueda web están vacíos. "
            "No se puede realizar la verificación de datos (grounding) sin documentos de origen."
        )

    forbidden_phrases = [
        "no live web-search",
        "no live web search",
        "no se realizó búsqueda",
        "no se realizo busqueda",
        "based on my training data",
        "sin acceso a internet en tiempo real",
        "no pude verificar en línea",
        "no pude verificar en linea",
        "no internet access",
        "knowledge cutoff",
        "without real-time",
        "without internet",
        "search was not performed",
    ]
    search_results_lower = search_results.lower()
    for phrase in forbidden_phrases:
        if phrase in search_results_lower:
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

    caller = router_instance or call_agent
    call_kwargs = dict(
        provider="cohere",
        model="command-a-plus-05-2026",
        messages=messages,
        documents=documents,
        max_tokens=4096,
    )
    if hasattr(caller, "call_agent"):
        resp = caller.call_agent(**call_kwargs)
    else:
        resp = caller(**call_kwargs)

    content_text = resp.content.strip()

    sources = _extract_sources_from_citations(resp.raw_response)
    if not sources:
        sources = _extract_sources_from_search_text(search_results)

    # Constructed directly in Python — never depends on the model producing
    # valid JSON, so a malformed/partial model response can no longer crash
    # this step with a Pydantic validation error.
    return GroundedReport(content=content_text, sources=sources)
