"""
Synthesizer agent for System B (Deep Research).

JSON GroundedReport output; retries once on validation errors.
Provider/model from config/model_router.yaml.
"""

from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from typing import Optional

from agents.deep_research.entity_focus import entity_focus_block
from agents.deep_research.research_types import (
    ResearchProfile,
    classify_research,
    report_outline_hints,
    research_profile_block,
)
from core.agent_runtime import run_role_raw, strip_fences
from core.prompt_fragments import NO_INVENT_RULES, NO_JSON_CODEBLOCK
from core.search_guards import (
    extract_urls,
    scrub_ungrounded_claims,
    source_url_is_verified,
    verify_cited_urls,
)
from schemas.deep_research import GroundedReport

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an expert investigative research writer.\n"
    "Take grounded research notes and produce a single, cohesive, detailed report.\n"
    "You must maintain citations and URLs from the sources.\n"
    "\n"
    "STRICT RULES:\n"
    "- Stay on the named subject only. Drop or quarantine facts about other companies.\n"
    "- Keep BOTH official-site findings and third-party web findings when present.\n"
    "- Prefer official domain for brand/contact when it conflicts with weak directories.\n"
    "- Preserve depth: addresses, phones, service lists, review stats, and gaps already verified.\n"
    "- Prefer structured Markdown with clear headings over a short blurb.\n"
    "- Flag uncertain associations (e.g. social accounts not clearly the same brand).\n"
    '- sources[] may only list URLs that already appear in the notes/content.\n'
    '- Open with a short "Research framing" line stating purpose/depth/data/design used.\n'
    "\n"
    + NO_INVENT_RULES
    + "\n"
    + "You MUST output your response strictly as a JSON object matching this schema:\n"
    + '{\n'
    + '  "content": "The final detailed report with inline citations and headings.",\n'
    + '  "sources": ["URL1", "URL2", "URL3"]\n'
    + '}\n'
    + "\n"
    + NO_JSON_CODEBLOCK
)


def clean_and_parse_synthesizer_report(
    content: str,
    *,
    fallback_sources: Optional[list[str]] = None,
) -> GroundedReport:
    """Clean markdown code blocks and parse content as GroundedReport.

    Free-tier models often return ``{"content": "..."}`` without ``sources``.
    Recover rather than failing the polish step: pull URLs from content or
    use *fallback_sources* (grounded draft).
    """
    cleaned = strip_fences(content or "").strip()
    if not cleaned:
        raise ValueError("Synthesizer returned empty content")

    data: dict | None = None
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            data = parsed
    except (json.JSONDecodeError, TypeError, ValueError):
        data = None

    if data is None:
        # Model returned prose instead of JSON — accept as content body
        sources = list(fallback_sources or []) or extract_urls(cleaned)
        return GroundedReport(content=cleaned, sources=sources)

    body = data.get("content")
    if body is None and isinstance(data.get("report"), str):
        body = data["report"]
    if not isinstance(body, str) or not body.strip():
        # Last resort: whole JSON as non-report failure
        raise ValueError("Synthesizer JSON missing non-empty 'content' field")

    sources_raw = data.get("sources")
    sources: list[str] = []
    if isinstance(sources_raw, list):
        sources = [str(s).strip() for s in sources_raw if str(s).strip()]
    elif isinstance(sources_raw, str) and sources_raw.strip():
        sources = [sources_raw.strip()]

    if not sources:
        sources = extract_urls(body) or list(fallback_sources or [])

    return GroundedReport(content=body, sources=sources)


def run_synthesizer(
    grounded_report: GroundedReport,
    search_results: str = "",
    router_instance=None,
    *,
    query: str = "",
    research_profile: Optional[ResearchProfile] = None,
) -> GroundedReport:
    """Compile the final publication-grade document; cross-check citations."""
    focus = entity_focus_block(query) if query else ""
    profile = research_profile or classify_research(query or "")
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
                f"Research topic: {query or '(see content)'}\n"
                f"Active profile: {profile.label()}\n\n"
                f"Synthesize this report without inventing ungrounded facts:\n\n"
                f"Content:\n{grounded_report.content}\n\n"
                f"Sources:\n{grounded_report.sources}"
            ),
        },
    ]

    def _call(msgs: list) -> GroundedReport:
        # run_role_raw applies difficulty selection + reasoning_effort for
        # gpt-oss (min medium for synthesizer) without an extra quota call.
        resp = run_role_raw(
            "deep_research",
            "synthesizer",
            messages=msgs,
            router_instance=router_instance,
            max_tokens=8192,
        )
        return clean_and_parse_synthesizer_report(
            resp.content,
            fallback_sources=list(grounded_report.sources or []),
        )

    try:
        final_report = _call(messages)
    except Exception as exc:
        if isinstance(exc, (json.JSONDecodeError, ValidationError, ValueError, TypeError)):
            retry_messages = messages + [
                {
                    "role": "user",
                    "content": (
                        "Tu respuesta anterior no era un JSON válido o estaba incompleta/truncada. "
                        "Responde ÚNICAMENTE con un objeto JSON válido con las claves "
                        '"content" (string markdown) y "sources" (array de URLs). '
                        "Si no tienes URLs nuevas, usa las del borrador: "
                        f"{list(grounded_report.sources or [])[:12]}. "
                        "Sin texto conversacional ni bloques de código markdown."
                    ),
                }
            ]
            final_report = _call(retry_messages)
        else:
            raise

    # Corpus for scrubbing: primary fetch + live dump only (not model rewrites).
    # Including grounded prose can re-introduce invented URLs; prefer raw search.
    corpus = search_results or (grounded_report.content or "")

    content, sources, _notes = scrub_ungrounded_claims(
        final_report.content or "",
        corpus,
        sources=list(final_report.sources or []) or list(grounded_report.sources or []),
    )

    # Strict: every listed source must appear as a URL in the search corpus
    sources = [s for s in sources if source_url_is_verified(s, corpus)]
    try:
        from agents.deep_research.source_fetch import is_plausible_source_url

        sources = [s for s in sources if is_plausible_source_url(s)]
    except Exception:
        pass

    # Host-fetched PRIMARY pages stay even if the polish model dropped them
    try:
        from agents.deep_research.source_fetch import merge_host_verified_primary

        content, sources = merge_host_verified_primary(content, sources, corpus)
    except Exception:
        pass

    # HTTP-verify every cited URL
    content, sources, _url_notes = verify_cited_urls(
        content, sources, max_verify=8, timeout=6.0
    )
    if _url_notes:
        logger.info("Synthesizer URL verification dropped %d unreachable sources", len(_url_notes))

    return GroundedReport(content=content, sources=sources)
