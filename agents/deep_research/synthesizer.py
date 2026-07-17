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
from core.agent_config import get_agent_config
from core.agent_runtime import invoke_router, strip_fences
from core.search_guards import scrub_ungrounded_claims, source_url_is_verified
from schemas.deep_research import GroundedReport

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert investigative research writer.
Take grounded research notes and produce a single, cohesive, detailed report.
You must maintain citations and URLs from the sources.

STRICT RULES:
- Stay on the named subject only. Drop or quarantine facts about other companies.
- Do NOT invent contact data, social handles, reviews, archive years, hex colors,
  fonts, logos, or source URLs. If missing, keep the gap explicit.
- Do NOT add web.archive.org or directory links that were not already in the notes.
- Keep BOTH official-site findings and third-party web findings when present.
- Prefer official domain for brand/contact when it conflicts with weak directories,
  but do not drop third-party evidence that is clearly the same entity.
- Preserve depth: addresses, phones, service lists, review stats, and gaps already verified.
- Prefer structured Markdown with clear headings over a short blurb.
- Flag uncertain associations (e.g. social accounts not clearly the same brand).
- sources[] may only list URLs that already appear in the notes/content.
- Open with a short "Research framing" line stating purpose/depth/data/design used.
- Shape the report to that profile (basic vs applied; exploratory/descriptive/explanatory;
  quant/qual emphasis; experimental vs observational limits).

You MUST output your response strictly as a JSON object matching this schema:
{
  "content": "The final detailed report with inline citations and headings.",
  "sources": ["URL1", "URL2", "URL3"]
}

Only return raw JSON. Do not wrap in markdown code blocks like ```json ... ```.
"""


def extract_urls(text: str) -> set[str]:
    """Compatibility wrapper."""
    from core.search_guards import extract_url_set

    return extract_url_set(text)


def clean_and_parse_synthesizer_report(content: str) -> GroundedReport:
    """Clean markdown code blocks and parse content as GroundedReport."""
    return GroundedReport.model_validate_json(strip_fences(content))


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

    cfg = get_agent_config("deep_research", "synthesizer")

    def _call(msgs: list) -> GroundedReport:
        resp = invoke_router(
            router_instance,
            provider=cfg["provider"],
            model=cfg["model"],
            messages=msgs,
            fallback=cfg.get("fallback"),
            max_tokens=8192,
        )
        return clean_and_parse_synthesizer_report(resp.content)

    try:
        final_report = _call(messages)
    except Exception as exc:
        if isinstance(exc, (json.JSONDecodeError, ValidationError, ValueError)):
            retry_messages = messages + [
                {
                    "role": "user",
                    "content": (
                        "Tu respuesta anterior no era un JSON válido o estaba incompleta/truncada. "
                        "Por favor, responde ÚNICAMENTE con un objeto JSON válido que cumpla exactamente "
                        "con el esquema Pydantic requerido, sin texto conversacional ni bloques de código de markdown."
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

    return GroundedReport(content=content, sources=sources)
