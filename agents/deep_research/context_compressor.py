"""
Context Compressor agent for System B (Deep Research).

Provider/model/fallback from config/model_router.yaml.

Produces:
  - entity-anchored search terms
  - research typology profile (purpose / depth / data / design)
"""

from __future__ import annotations

from typing import Optional

from agents.deep_research.entity_focus import extract_entity_anchors, merge_search_terms
from agents.deep_research.research_types import (
    classify_research,
    merge_profiles,
    profile_from_mapping,
)
from core.agent_runtime import run_structured_agent
from core.difficulty_scorer import SAFETY_HARD_RE
from schemas.deep_research import CondensedTrends

SYSTEM_PROMPT = """You are an expert research-design and context compression agent.
From the user's topic you must:
0) Run the SAFETY GATE (see below).
1) Produce focused search-engine phrases.
2) Classify the research using a standard typology (not industry-specific).

## SAFETY GATE (do this FIRST)
Assess the user research query. Flag it as unsafe if it clearly falls into one
of these categories:
- Hate speech, harassment, or discrimination against protected groups
- Personal information extraction (PII, doxxing)
- Instructions for weapons, drugs, or illegal activities
- Sexual content involving minors or non-consensual themes
- Malicious code generation or hacking instructions
- Propaganda or disinformation campaigns
Normal factual/business research is safe. Only flag the categories above.
If unsafe, set "is_safe": false and list your reasons in "safety_reasons".
Otherwise set "is_safe": true and leave "safety_reasons" empty.

## Research typology (choose the best fit)

### Purpose
- basic: expand theory/knowledge without an immediate practical deliverable.
- applied: use knowledge to solve or support a practical problem/decision.

### Depth
- exploratory: little-known topic; map terrain; prepare future hypotheses.
- descriptive: characterize who/what/where/when/how-it-is (not forced why).
- explanatory: seek causes, mechanisms, consequences between variables.

### Data approach
- quantitative: numbers, rates, surveys, statistics (when the topic asks for them).
- qualitative: meanings, discourses, practices, perceptions (sourced only).
- mixed: both when appropriate.

### Design
- experimental: controlled manipulation / trials / A/B if the topic is about that.
- non_experimental: observe phenomena as they appear (most open-web research).

## CRITICAL CONSTRAINTS on "technologies" (search terms)
- Return AT MOST 8 items.
- EACH term MUST include the exact subject name (or a clear spelling variant)
  plus one facet when possible.
- Prefer precise queries over bare generics. NEVER emit generic-only phrases
  like "reviews", "companies", or "news" alone.
- Each item should be a search-engine style phrase (about 2–8 words).
- Cover facets suited to the chosen typology (e.g. theory/literature for basic;
  practical case/contact for applied descriptive; causes/impact for explanatory).

You MUST output your response strictly as a JSON object matching this schema:
{
  "technologies": ["Search term 1", "Search term 2"],
  "rationale": "Why these search terms were prioritized.",
  "purpose": "basic|applied",
  "depth": "exploratory|descriptive|explanatory",
  "data_approach": "quantitative|qualitative|mixed",
  "design": "experimental|non_experimental",
  "profile_rationale": "Why this research profile fits the user topic.",
  "is_safe": true,
  "safety_reasons": []
}
Only return raw JSON. Do not wrap in markdown code blocks.
"""


def run_context_compressor(
    query: str,
    router_instance=None,
    fallback_override: Optional[dict[str, str]] = None,
    assessment=None,
    selection_out=None,
    **runtime_kwargs,
) -> CondensedTrends:
    """Extract search terms + research profile from the research query."""
    heuristic = classify_research(query)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Classify the research profile and extract search targets for:\n{query}\n\n"
                f"Heuristic draft (you may refine): {heuristic.label()}"
            ),
        },
    ]
    trends = run_structured_agent(
        "deep_research",
        "context_compressor",
        messages=messages,
        schema=CondensedTrends,
        router_instance=router_instance,
        fallback_override=fallback_override,
        assessment=assessment,
        selection_out=selection_out,
        task_text=query,
        **runtime_kwargs,
    )

    # Defensive normalization — never trust the model alone.
    trimmed: list[str] = []
    for term in trends.technologies[:8]:
        term = term.strip()
        if len(term) > 100:
            term = " ".join(term.split()[:10])
        if term:
            trimmed.append(term)

    anchors = extract_entity_anchors(query, max_anchors=6)
    trends.technologies = merge_search_terms(anchors, trimmed, max_terms=8)
    if not trends.technologies:
        trends.technologies = anchors[:4] or [query[:150]]
    if not (trends.rationale or "").strip():
        trends.rationale = "Entity-anchored search terms from the research topic."

    llm_profile = profile_from_mapping(
        {
            "purpose": trends.purpose,
            "depth": trends.depth,
            "data_approach": trends.data_approach,
            "design": trends.design,
            "profile_rationale": trends.profile_rationale or trends.rationale,
        }
    )
    # Prefer valid LLM labels; fall back to heuristic rationale when empty
    final = merge_profiles(heuristic, llm_profile)
    trends.purpose = final.purpose
    trends.depth = final.depth
    trends.data_approach = final.data_approach
    trends.design = final.design
    trends.profile_rationale = (
        (final.rationale or heuristic.rationale or trends.profile_rationale or "").strip()
    )

    # WAVE-18 safety gate (the dedicated safety_filter role was removed):
    # the LLM classification is the primary gate; the host-side regex is a
    # conservative hard pre-gate — on a hard signal the topic is unsafe even
    # if the model said safe.
    if trends.is_safe and SAFETY_HARD_RE.search(query):
        reasons = list(trends.safety_reasons or [])
        reasons.append("Host safety pre-gate flagged the topic (hard keyword).")
        trends.is_safe = False
        trends.safety_reasons = reasons
    return trends
