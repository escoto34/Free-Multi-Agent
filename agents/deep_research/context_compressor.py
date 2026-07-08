"""
Context Compressor agent using PydanticAI definition.
Extracts search parameters, trends, and keywords from a research topic.
"""

from __future__ import annotations

from typing import Optional

from pydantic_ai import Agent

from core.agent_config import get_agent_config
from core.router import call_agent
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

# Official PydanticAI Agent definition
context_compressor_agent = Agent(
    "test",
    output_type=CondensedTrends,
    system_prompt=SYSTEM_PROMPT,
)


def run_context_compressor(
    query: str,
    router_instance=None,
    fallback_override: Optional[dict[str, str]] = None,
) -> CondensedTrends:
    """Run the Context Compressor agent to identify trends and guide web search.

    Provider/model/fallback are read from config/model_router.yaml
    (``deep_research.context_compressor``) rather than hardcoded, so editing
    the YAML actually changes runtime behaviour.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Extract search targets for: {query}"},
    ]

    cfg = get_agent_config("deep_research", "context_compressor")
    fb = fallback_override or cfg.get("fallback")

    caller = router_instance or call_agent
    if hasattr(caller, "call_agent"):
        resp = caller.call_agent(
            provider=cfg["provider"],
            model=cfg["model"],
            messages=messages,
            fallback=fb,
        )
    else:
        resp = caller(
            provider=cfg["provider"],
            model=cfg["model"],
            messages=messages,
            fallback=fb,
        )
    content = resp.content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[-1]
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        content = content.strip()

    trends = CondensedTrends.model_validate_json(content)

    # Defensive normalization: even with the tightened prompt above, don't
    # trust the model to always obey. Cap count/length here too, so
    # web_search.py always receives short, bounded terms regardless of what
    # this specific call returned.
    trimmed_technologies = []
    for term in trends.technologies[:6]:
        term = term.strip()
        if len(term) > 60:
            term = " ".join(term.split()[:6])
        if term:
            trimmed_technologies.append(term)
    trends.technologies = trimmed_technologies

    return trends
