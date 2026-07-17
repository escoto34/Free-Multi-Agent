"""
Shared guards for live web-search verification and URL extraction.

Single source of truth for markers that mean "the model admitted it did not
search live" — used by both web_search and grounding so the lists cannot drift.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

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


# Contact / brand tokens that must appear literally in verified corpus
_EMAIL_RE = re.compile(
    r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"
)
# Phones: +504 …, (504) …, or long digit runs with separators
_PHONE_RE = re.compile(
    r"(?:\+\s?504[\s\-]?)?(?:\(?\d{2,4}\)?[\s\-.]?){2,5}\d{2,4}"
)
_WAYBACK_RE = re.compile(
    r"https?://web\.archive\.org/[^\s\)\]\"'>,;]+",
    re.IGNORECASE,
)
_HEX_COLOR_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")


def extract_emails(text: str) -> list[str]:
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for m in _EMAIL_RE.findall(text):
        key = m.lower()
        if key not in seen:
            seen.add(key)
            out.append(m)
    return out


def extract_phones(text: str) -> list[str]:
    """Heuristic phone spans (may over-match; used only for scrubbing)."""
    if not text:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for m in _PHONE_RE.finditer(text):
        span = m.group(0).strip()
        # Skip coordinate-like tokens (decimal degrees)
        if "°" in span or re.search(r"\d+\.\d+", span):
            continue
        digits = re.sub(r"\D", "", span)
        # Require enough digits for a real phone; skip years like 2022 / 20222023
        if len(digits) < 8:
            continue
        if re.fullmatch(r"20\d{2}", digits) or re.fullmatch(r"20\d{6}", digits):
            continue
        # Prefer spans that look intentional (+country or many separators)
        if "+" not in span and not re.search(r"[\s\-().]", span):
            if len(digits) < 10:
                continue
        key = digits
        if key in seen:
            continue
        seen.add(key)
        out.append(span)
    return out


def extract_wayback_urls(text: str) -> list[str]:
    return extract_urls(" ".join(_WAYBACK_RE.findall(text or "")))


def _corpus_contains(token: str, corpus_lower: str) -> bool:
    t = (token or "").strip().lower()
    if not t:
        return True
    if t in corpus_lower:
        return True
    # phones: compare digit sequence
    digits = re.sub(r"\D", "", t)
    if len(digits) >= 8 and digits in re.sub(r"\D", "", corpus_lower):
        return True
    return False


def scrub_ungrounded_claims(
    content: str,
    corpus: str,
    *,
    sources: Optional[list[str]] = None,
) -> tuple[str, list[str], list[str]]:
    """Remove or flag contact/archive facts that never appear in *corpus*.

    Returns ``(new_content, new_sources, audit_notes)``.
    """
    corpus = corpus or ""
    corpus_l = corpus.lower()
    notes: list[str] = []
    text = content or ""

    for email in extract_emails(text):
        if not _corpus_contains(email, corpus_l):
            notes.append(f"Removed unverified email: {email}")
            text = text.replace(email, "[email not found in verified sources]")

    for phone in extract_phones(text):
        if not _corpus_contains(phone, corpus_l):
            notes.append(f"Removed unverified phone: {phone}")
            text = text.replace(phone, "[phone not found in verified sources]")

    for wb in _WAYBACK_RE.findall(text):
        if not _corpus_contains(wb, corpus_l):
            notes.append(f"Removed invented archive URL: {wb}")
            text = text.replace(wb, "[archive URL not found in verified sources]")

    for color in _HEX_COLOR_RE.findall(text):
        if not _corpus_contains(color, corpus_l):
            notes.append(f"Removed unverified hex color: {color}")
            text = text.replace(color, "[color not found in verified sources]")

    # Drop source list entries that never appeared in the live/primary corpus
    new_sources: list[str] = []
    if sources is not None:
        for src in sources:
            s = (src or "").strip()
            if not s:
                continue
            if _corpus_contains(s, corpus_l) or any(
                s.lower().rstrip("/") in u or u in s.lower()
                for u in extract_url_set(corpus)
            ):
                new_sources.append(s)
            else:
                notes.append(f"Dropped source not present in search/primary dump: {s}")
    else:
        new_sources = []

    if notes:
        audit = (
            "\n\n## Verification audit (automatic)\n"
            "The following claims were stripped or flagged because they did not "
            "appear in fetched primary pages or the live search dump:\n"
            + "\n".join(f"- {n}" for n in notes)
        )
        if "## Verification audit" not in text:
            text = text.rstrip() + audit

    return text, new_sources, notes
