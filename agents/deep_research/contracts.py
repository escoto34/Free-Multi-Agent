"""
Shared contracts for search/fetch sources (WAVE-11A).

Replaces the boolean ``ok`` with an honest, reserved-name status taxonomy
(binding decision 5 — deliberately a *separate* type from WAVE-05's
``core.call_outcome.CallOutcome``, which models LLM-call failures). A
``NOT_APPLICABLE`` source is out-of-scope, not a failure, and must not count
against health metrics.

Also carries the versioned, decomposed ``score_result()`` used to rank search
hits so a ranking is inspectable/explainable instead of a single opaque number.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SourceResultStatus(StrEnum):
    """Honest per-source outcome used across the search/fetch chain."""

    SUCCESS = "success"
    EMPTY = "empty"
    TIMEOUT = "timeout"
    ERROR = "error"
    INVALID = "invalid"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXHAUSTED = "quota_exhausted"
    NOT_APPLICABLE = "not_applicable"


SUCCESS = SourceResultStatus.SUCCESS


@dataclass
class SearchResult:
    """One web hit returned by a search engine (e.g. DDG lite)."""

    url: str
    title: str
    snippet: str


# Bump whenever the ranking weights below change materially; it is part of any
# cached/recorded ranking so a stored score is never silently reinterpreted.
SCORING_VERSION = "search-v1"


def score_result(result: SearchResult) -> tuple[dict[str, float], float]:
    """Versioned decomposed score for a search hit.

    Returns ``(components, total)`` where each component is 0.0-1.0 and the
    total is a weighted sum, so a ranking is inspectable in CLI output.
    """
    components: dict[str, float] = {}

    url = (result.url or "").strip().lower()
    has_http = 1.0 if url.startswith(("http://", "https://")) else 0.0
    is_homepage = 1.0 if (url and url.count("/") <= 2) else 0.0

    title = (result.title or "").strip()
    title_len = len(title)
    if title_len >= 12:
        title_score = 1.0
    elif title_len >= 4:
        title_score = 0.6
    else:
        title_score = 0.2

    snippet = (result.snippet or "").strip()
    snippet_score = 1.0 if len(snippet) >= 60 else (0.5 if snippet else 0.1)

    components["transport"] = has_http
    components["homepage_bias"] = is_homepage
    components["title"] = title_score
    components["snippet"] = snippet_score

    total = (
        components["transport"]
        + components["homepage_bias"]
        + components["title"]
        + components["snippet"]
    ) / 4.0
    return components, round(total, 3)


def http_status_to_source_status(status: int, body: str = "") -> SourceResultStatus:
    """Map an HTTP status (plus optional body) to a SourceResultStatus.

    Deliberately separate from ``call_outcome.classify_http_status`` — this is
    the source/HTTP taxonomy, not the LLM-call one.
    """
    if status in (429, 402, 413, 409):
        lowered = (body or "").lower()
        if any(w in lowered for w in ("quota", "credit", "insufficient", "exhausted")):
            return SourceResultStatus.QUOTA_EXHAUSTED
        return SourceResultStatus.RATE_LIMITED
    if status in (408, 502, 503, 504):
        return SourceResultStatus.TIMEOUT
    if status == 422:
        return SourceResultStatus.INVALID
    if 200 <= status < 300:
        return SourceResultStatus.SUCCESS
    return SourceResultStatus.ERROR