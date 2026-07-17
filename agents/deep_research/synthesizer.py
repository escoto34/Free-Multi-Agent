"""
Synthesizer agent for System B (Deep Research).

JSON GroundedReport output; retries once on validation errors.
Provider/model from config/model_router.yaml.
"""

from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from agents.deep_research.entity_focus import entity_focus_block
from core.agent_runtime import invoke_router, strip_fences
from core.agent_config import get_agent_config
from core.search_guards import extract_url_set
from schemas.deep_research import GroundedReport

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert investigative research writer.
Take grounded research notes and produce a single, cohesive, detailed report.
You must maintain citations and URLs from the sources.

STRICT RULES:
- Stay on the named subject only. Drop or quarantine facts about other companies.
- Do NOT invent contact data, social handles, or reviews.
- Preserve depth: keep addresses, phones, service lists, review stats, and gaps.
- Prefer structured Markdown with clear headings over a short blurb.
- Flag uncertain associations (e.g. social accounts not clearly the same brand).

You MUST output your response strictly as a JSON object matching this schema:
{
  "content": "The final detailed report with inline citations and headings.",
  "sources": ["URL1", "URL2", "URL3"]
}

Only return raw JSON. Do not wrap in markdown code blocks like ```json ... ```.
"""


def extract_urls(text: str) -> set[str]:
    """Compatibility wrapper — prefers shared ``extract_url_set``."""
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
) -> GroundedReport:
    """Compile the final publication-grade document; cross-check citations."""
    focus = entity_focus_block(query) if query else ""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"{focus}\n"
                f"Research topic: {query or '(see content)'}\n\n"
                f"Synthesize this report without merging unrelated entities:\n\n"
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

    if search_results:
        search_urls = extract_url_set(search_results)
        warning_msg = (
            " (⚠️ fuente no verificada en esta ejecución — revisar manualmente)"
        )
        for source in list(final_report.sources):
            source_clean = source.lower().strip("/")
            found = any(
                source_clean in s_url or s_url in source_clean for s_url in search_urls
            )
            if not found and warning_msg not in final_report.content:
                final_report.content = final_report.content.replace(
                    source, f"{source}{warning_msg}"
                )

    return final_report
