"""
Shared guards for live web-search verification and URL extraction.

Single source of truth for markers that mean "the model admitted it did not
search live" — used by both web_search and grounding so the lists cannot drift.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

_URL_PATTERN = re.compile(r"https?://[^\s\)\]\"'>,;]+")


def _url_host_plausible(url: str) -> bool:
    """Drop abbreviation false-positives (https://e.g) and empty hosts."""
    try:
        from urllib.parse import urlparse

        host = (urlparse(url).hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        if not host or "." not in host:
            return False
        # Single-letter TLD → e.g / i.e / u.s
        tld = host.rsplit(".", 1)[-1]
        if not tld.isalpha() or len(tld) < 2:
            return False
        if host in {"e.g", "i.e", "u.s", "u.k", "a.m", "p.m"}:
            return False
        # Vocabulary hosts are fine in corpus but poor citations — still keep
        # for verification matching; filtering for *listed sources* is separate.
        return True
    except Exception:
        return False


def extract_urls(text: str, *, limit: int | None = None) -> list[str]:
    """Extract http(s) URLs from *text*, de-duplicated, order preserved."""
    if not text:
        return []
    raw = _URL_PATTERN.findall(text)
    cleaned: list[str] = []
    seen: set[str] = set()
    for url in raw:
        # Markdown/model debris: trailing ` from ``url`` fences, brackets, etc.
        while url and url[-1] in (".", ",", ";", ":", "?", "!", ")", "]", "}", "'", '"', "`", "»"):
            url = url[:-1]
        while url and url[0] in ("'", '"', "`", "(", "[", "{", "«"):
            url = url[1:]
        if not url:
            continue
        if not _url_host_plausible(url):
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


def normalize_source_url(url: str) -> str:
    """Lowercase, strip trailing slash/punctuation for comparison."""
    u = (url or "").strip()
    while u and u[0] in "'\"`(«[{":
        u = u[1:]
    while u and u[-1] in ".,);]'\"»`":
        u = u[:-1]
    return u.lower().rstrip("/")


def source_url_is_verified(source: str, corpus: str) -> bool:
    """True only if *source* matches a URL that actually appears in *corpus*.

    Prevents invented citations. Does **not** accept host-only or scheme-only
    matches (e.g. bare ``https:`` appearing in every corpus).
    Also rejects abbreviation false-positives like ``https://e.g``.
    """
    s = normalize_source_url(source)
    if not s:
        return False
    # Always reject abbreviation / single-letter-TLD junk even if present in text
    check = s if "://" in s else f"https://{s}"
    if not _url_host_plausible(check):
        return False
    if "://" not in s:
        # Bare domain as a "source" only if it appears as a URL host in corpus
        if "." not in s:
            return False
        hosts = set()
        for u in extract_urls(corpus or ""):
            m = re.match(r"https?://([^/]+)", u.lower())
            if m:
                h = m.group(1)
                if h.startswith("www."):
                    h = h[4:]
                hosts.add(h)
        return s.lstrip("www.") in hosts or s in hosts

    corpus_urls = extract_url_set(corpus or "")
    if s in corpus_urls:
        return True
    # Allow trailing-path variants only when a corpus URL is a prefix of source
    # or source is a prefix of a corpus URL (same resource family).
    for u in corpus_urls:
        if s == u:
            return True
        # same origin + one is prefix of the other
        if s.startswith(u + "/") or u.startswith(s + "/"):
            return True
        # strip www.
        s2 = s.replace("://www.", "://", 1)
        u2 = u.replace("://www.", "://", 1)
        if s2 == u2 or s2.startswith(u2 + "/") or u2.startswith(s2 + "/"):
            return True
    return False


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

    # Drop source list entries that never appeared as real URLs in the corpus.
    # Normalize markdown backticks first so ``https://wa.me/…` is not dropped
    # when the clean URL is in the primary dump.
    new_sources: list[str] = []
    if sources is not None:
        for src in sources:
            s = (src or "").strip()
            while s and s[0] in "'\"`(«[{":
                s = s[1:]
            while s and s[-1] in ".,);]'\"»`":
                s = s[:-1]
            if not s:
                continue
            if source_url_is_verified(s, corpus):
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


def verify_cited_urls(
    content: str,
    sources: list[str],
    *,
    max_verify: int = 8,
    timeout: float = 6.0,
) -> tuple[str, list[str], list[str]]:
    """HTTP-verify every cited URL in content and source list.

    Drops URLs that return non-200 or empty body. Returns
    ``(content, verified_sources, audit_notes)``.
    """
    from agents.deep_research.source_fetch import fetch_url

    all_urls = list(extract_urls(content, limit=max_verify * 2))
    url_set: set[str] = set()
    for u in all_urls:
        norm = u.lower().rstrip("/")
        if norm not in url_set:
            url_set.add(norm)
    for s in sources:
        norm = s.lower().rstrip("/")
        if norm not in url_set:
            url_set.add(norm)
            all_urls.append(s)

    to_check = all_urls[:max_verify]
    verified: set[str] = set()
    notes: list[str] = []

    for url in to_check:
        if not url.startswith(("http://", "https://")):
            continue
        page = fetch_url(url, timeout=timeout, max_chars=2000)
        if page.ok and page.text and len(page.text.strip()) > 50:
            verified.add(url.lower().rstrip("/"))
        else:
            reason = page.error or f"HTTP {page.status}" if page.status else "no content"
            notes.append(f"Cited URL failed verification: {url} ({reason})")

    verified_sources: list[str] = []
    for s in sources:
        if s.lower().rstrip("/") in verified or s.lower().rstrip("/") in {
            v.lower().rstrip("/") for v in verified
        }:
            verified_sources.append(s)
        else:
            notes.append(f"Dropped source (unreachable): {s}")

    if notes:
        audit = (
            "\n\n## URL verification audit (automatic HTTP check)\n"
            + "\n".join(f"- {n}" for n in notes)
        )
        if "## URL verification audit" not in content:
            content = content.rstrip() + audit

    return content, verified_sources, notes
