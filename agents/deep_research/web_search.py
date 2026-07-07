"""
Web Search agent using PydanticAI definition.
Queries the web using groq/compound-mini (Tavily-integrated) and returns raw search results.
"""

from __future__ import annotations

from pydantic_ai import Agent

from core.router import call_agent

SYSTEM_PROMPT = """You are a web search helper.
Your job is to run search queries on the user topic and return a comprehensive compilation of the search results, including facts, news, URLs, and contextual information.
"""

# Official PydanticAI Agent definition
web_search_agent = Agent(
    "test",
    output_type=str,
    system_prompt=SYSTEM_PROMPT,
)

# --- Guard configuration ----------------------------------------------------

# Groq's compound-mini rejects oversized requests with HTTP 413. Cap the
# number of search terms AND the total query length defensively, regardless
# of what upstream (context_compressor) hands us.
MAX_SEARCH_TERMS: int = 6
MAX_QUERY_CHARS: int = 150

# Phrases (case-insensitive substring match) that indicate the model answered
# from training knowledge instead of performing a real live search. If any of
# these appear in the raw result, the caller MUST treat the result as
# unverified — see raise_if_no_live_search() below.
_NO_LIVE_SEARCH_MARKERS: tuple[str, ...] = (
    "no live web-search was performed",
    "no live web search was performed",
    "no live search was performed",
    "based on my training data",
    "sin acceso a internet en tiempo real",
    "no se realizó ninguna búsqueda",
    "no se realizó una búsqueda",
    "no pude verificar en línea",
    "sin realizar una búsqueda en vivo",
)


class NoLiveSearchError(Exception):
    """Raised when the search step's own output admits it did not search live."""


def _build_safe_query(search_terms: list[str]) -> str:
    """Build a short, bounded query string from a list of search terms.

    Truncates the number of terms and the total character length so that
    an oversized upstream input (e.g. a full research prompt accidentally
    passed in as "terms") can never blow past compound-mini's request size
    limit and trigger a 413.
    """
    # Defensive: split any single oversized "term" into words if the caller
    # passed one giant string instead of a real list of short keywords.
    normalized: list[str] = []
    for term in search_terms:
        term = term.strip()
        if not term:
            continue
        if len(term) > 40:
            # Looks like a sentence/paragraph leaked in as a single "term" —
            # fall back to just the first few words of it.
            normalized.extend(term.split()[:6])
        else:
            normalized.append(term)

    capped_terms = normalized[:MAX_SEARCH_TERMS]
    query = " ".join(capped_terms)
    return query[:MAX_QUERY_CHARS]


def raise_if_no_live_search(result_text: str) -> None:
    """Raise ``NoLiveSearchError`` if the result admits it wasn't a real search.

    Call this immediately after ``run_web_search()`` and BEFORE passing the
    result into grounding/synthesis. This is the hard barrier that stops an
    honestly-labeled "I didn't actually search" response from silently
    flowing into a report that looks verified.
    """
    lowered = result_text.lower()
    for marker in _NO_LIVE_SEARCH_MARKERS:
        if marker in lowered:
            raise NoLiveSearchError(
                "El paso de búsqueda no devolvió resultados verificados en "
                f"vivo (marcador detectado: {marker!r}). Abortando para "
                "evitar generar un reporte no fundamentado."
            )


def run_web_search(search_terms: list[str], router_instance=None) -> str:
    """Run a web search using groq/compound-mini (Tavily-integrated).

    Returns the raw search compilation string.

    Raises:
        NoLiveSearchError: if the model's own output admits no real search
            was performed (see ``raise_if_no_live_search``).
    """
    query = _build_safe_query(search_terms)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Search terms: {query}"},
    ]
    caller = router_instance or call_agent
    if hasattr(caller, "call_agent"):
        resp = caller.call_agent(
            provider="groq",
            model="groq/compound-mini",
            messages=messages,
        )
    else:
        resp = caller(
            provider="groq",
            model="groq/compound-mini",
            messages=messages,
        )

    raise_if_no_live_search(resp.content)
    return resp.content
