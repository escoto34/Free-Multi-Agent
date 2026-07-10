"""
Shared guards for live web-search verification and URL extraction.

Single source of truth for markers that mean "the model admitted it did not
search live" — used by both web_search and grounding so the lists cannot drift.
"""

from __future__ import annotations

import re
from typing import Iterable

_URL_PATTERN = re.compile(r"https?://[^\s\)\]\"'>,;]+")

# Phrases (lowercase) that indicate no real live search was performed.
# Both exact multi-word admissions and shorter stems used by grounding.
NO_LIVE_SEARCH_MARKERS: tuple[str, ...] = (
    "no live web-search was performed",
    "no live web search was performed",
    "no live search was performed",
    "no live web-search",
    "no live web search",
    "based on my training data",
    "sin acceso a internet en tiempo real",
    "no se realizó ninguna búsqueda",
    "no se realizó una búsqueda",
    "no se realizó búsqueda",
    "no se realizo busqueda",
    "no pude verificar en línea",
    "no pude verificar en linea",
    "sin realizar una búsqueda en vivo",
    "no internet access",
    "knowledge cutoff",
    "without real-time",
    "without internet",
    "search was not performed",
)


class NoLiveSearchError(Exception):
    """Raised when search output admits it did not perform a live search."""


def find_no_live_search_marker(text: str) -> str | None:
    """Return the first matching marker in *text*, or None if clean."""
    if not text:
        return None
    lowered = text.lower()
    for marker in NO_LIVE_SEARCH_MARKERS:
        if marker in lowered:
            return marker
    return None


def raise_if_no_live_search(result_text: str) -> None:
    """Raise ``NoLiveSearchError`` if the result admits it wasn't a real search."""
    marker = find_no_live_search_marker(result_text)
    if marker is None:
        return
    raise NoLiveSearchError(
        "El paso de búsqueda no devolvió resultados verificados en "
        f"vivo (marcador detectado: {marker!r}). Abortando para "
        "evitar generar un reporte no fundamentado."
    )


def extract_urls(text: str, *, limit: int | None = None) -> list[str]:
    """Extract http(s) URLs from *text*, de-duplicated, order preserved."""
    if not text:
        return []
    raw = _URL_PATTERN.findall(text)
    cleaned: list[str] = []
    seen: set[str] = set()
    for url in raw:
        while url and url[-1] in (".", ",", ";", ":", "?", "!", ")", "]"):
            url = url[:-1]
        if not url:
            continue
        key = url.lower().rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(url)
        if limit is not None and len(cleaned) >= limit:
            break
    return cleaned


def extract_url_set(text: str) -> set[str]:
    """Lowercased, slash-stripped URL set for cross-referencing citations."""
    return {u.lower().strip("/") for u in extract_urls(text)}
