"""
Web Search agent for System B (Deep Research).

Provider/model from config/model_router.yaml (typically groq/compound-mini).
"""

from __future__ import annotations

from core.agent_runtime import run_role_raw
from core.search_guards import NoLiveSearchError, raise_if_no_live_search

SYSTEM_PROMPT = """You are a web search helper. Your job is to run search queries on the user topic and return a comprehensive compilation of the search results, including facts, news, URLs, and contextual information.
"""

MAX_SEARCH_TERMS: int = 6
MAX_QUERY_CHARS: int = 150

# Re-export for graphs/tests that import from this module.
__all__ = [
    "NoLiveSearchError",
    "MAX_SEARCH_TERMS",
    "MAX_QUERY_CHARS",
    "raise_if_no_live_search",
    "run_web_search",
    "_build_safe_query",
]


def _build_safe_query(search_terms: list[str]) -> str:
    """Build a short, bounded query string from a list of search terms."""
    normalized: list[str] = []
    for term in search_terms:
        term = term.strip()
        if not term:
            continue
        if len(term) > 40:
            normalized.extend(term.split()[:6])
        else:
            normalized.append(term)

    capped_terms = normalized[:MAX_SEARCH_TERMS]
    query = " ".join(capped_terms)
    return query[:MAX_QUERY_CHARS]


def run_web_search(search_terms: list[str], router_instance=None) -> str:
    """Run web search; hard-abort if the model admits no live search."""
    query = _build_safe_query(search_terms)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Search terms: {query}"},
    ]
    resp = run_role_raw(
        "deep_research",
        "web_search",
        messages=messages,
        router_instance=router_instance,
    )
    raise_if_no_live_search(resp.content)
    return resp.content
