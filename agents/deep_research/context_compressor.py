"""
Context Compressor agent for System B (Deep Research).

Provider/model/fallback from config/model_router.yaml.
"""

from __future__ import annotations

from typing import Optional

from core.agent_runtime import run_structured_agent
from schemas.deep_research import CondensedTrends

SYSTEM_PROMPT = """You are an expert information synthesis and context compression agent.
Identify the core technologies, subtopics, and trends associated with the research query.
Generate a structured query list to guide search engines.

CRITICAL CONSTRAINTS on the "technologies" field:
- Return AT MOST 6 items.
- Each item MUST be a short search keyword or phrase of 1 to 4 words —
  like a real search-engine query (e.g. "multi-agent consensus protocols",
  "Raft algorithm Python", "ISO 25010 quality metrics").
- NEVER return a full sentence, a paraphrase of the research question, or
  any text longer than roughly 40 characters per item. If the research
  query is long or has multiple sub-objectives, break it down into several
  SHORT, separate keyword phrases instead of one long one.

You MUST output your response strictly as a JSON object matching this schema:
{
  "technologies": ["Search term 1", "Search term 2", "Search term 3"],
  "rationale": "Brief explanation of why these search terms were prioritized."
}
Only return raw JSON. Do not wrap in markdown code blocks like ```json ... ```.
"""


def run_context_compressor(
    query: str,
    router_instance=None,
    fallback_override: Optional[dict[str, str]] = None,
) -> CondensedTrends:
    """Extract short search terms from the research query."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Extract search targets for: {query}"},
    ]
    trends = run_structured_agent(
        "deep_research",
        "context_compressor",
        messages=messages,
        schema=CondensedTrends,
        router_instance=router_instance,
        fallback_override=fallback_override,
    )

    # Defensive normalization — never trust the model alone.
    trimmed: list[str] = []
    for term in trends.technologies[:6]:
        term = term.strip()
        if len(term) > 60:
            term = " ".join(term.split()[:6])
        if term:
            trimmed.append(term)
    trends.technologies = trimmed
    return trends
