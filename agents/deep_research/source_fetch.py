"""
Fetch user-provided primary URLs for System B (Deep Research).

When a topic names an official website (e.g. credentalhn.com), MultiAgent
fetches it *before* grounding so models cannot invent archive pages or
contact data that never appeared in live sources.
"""

from __future__ import annotations

import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Iterable, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Bare domains and full URLs in free text
_URL_RE = re.compile(
    r"(?:https?://)?"
    r"(?:www\.)?"
    r"([a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)+)"
    r"(?:/[^\s\]\)\"'>,;]*)?",
    re.IGNORECASE,
)
_EXPLICIT_URL_RE = re.compile(r"https?://[^\s\)\]\"'>,;]+", re.IGNORECASE)

# Domains that are never "the subject's website" even if they appear nearby
_SKIP_HOST_SUFFIXES = (
    "google.com",
    "google.hn",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "linkedin.com",
    "wikipedia.org",
    "archive.org",
    "web.archive.org",
    "paginasamarillas.hn",
    "github.com",
    "openrouter.ai",
    "groq.com",
)

_DEFAULT_UA = (
    "MultiAgent-research/1.0 (+local free-tier research; factual source fetch)"
)


@dataclass
class FetchedSource:
    url: str
    ok: bool
    status: Optional[int]
    text: str
    error: str = ""


class _HTMLToText(HTMLParser):
    """Minimal HTML → visible text (scripts/styles dropped)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[no-untyped-def]
        t = tag.lower()
        if t in ("script", "style", "noscript", "svg"):
            self._skip += 1
        if t in ("br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"):
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in ("script", "style", "noscript", "svg") and self._skip:
            self._skip -= 1
        if t in ("p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"):
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if data and data.strip():
            self._chunks.append(data)

    def text(self) -> str:
        raw = "".join(self._chunks)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def _host_of(url_or_host: str) -> str:
    s = (url_or_host or "").strip().lower()
    if "://" not in s:
        s = "https://" + s
    try:
        host = urlparse(s).hostname or ""
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _is_skippable_host(host: str) -> bool:
    h = (host or "").lower()
    if not h or "." not in h:
        return True
    for suf in _SKIP_HOST_SUFFIXES:
        if h == suf or h.endswith("." + suf):
            return True
    # common TLDs only — drop pure words without TLD already handled
    return False


def normalize_url(raw: str) -> str:
    """Turn a bare domain or partial URL into https://…"""
    s = (raw or "").strip().rstrip(".,);]")
    if not s:
        return ""
    if not s.lower().startswith(("http://", "https://")):
        s = "https://" + s.lstrip("/")
    # drop trailing junk path fragments from punctuation
    while s and s[-1] in ".,);]'\"«»":
        s = s[:-1]
    return s


def extract_user_urls(text: str, *, max_urls: int = 8) -> list[str]:
    """Extract likely subject websites from a research prompt (not social/search)."""
    if not text:
        return []

    found: list[str] = []
    seen: set[str] = set()

    def _add(candidate: str) -> None:
        url = normalize_url(candidate)
        if not url:
            return
        host = _host_of(url)
        if _is_skippable_host(host):
            return
        key = host + urlparse(url).path.rstrip("/").lower()
        if key in seen:
            return
        seen.add(key)
        # Prefer origin homepage once per host
        origin = f"https://{host}"
        if origin not in {normalize_url(u) for u in found}:
            # If only path variants, still keep first full URL if richer
            pass
        found.append(url if urlparse(url).path not in ("", "/") else origin)
        # Always ensure bare origin is present for site:
        if origin not in found and host:
            # Will dedupe below
            pass

    for m in _EXPLICIT_URL_RE.finditer(text):
        _add(m.group(0))

    # Bare domains (credentalhn.com) — require a known TLD shape
    for m in _URL_RE.finditer(text):
        full = m.group(0)
        host = m.group(1)
        if _is_skippable_host(host):
            continue
        # Prefer explicit https match above; bare domain OK
        _add(full if full.lower().startswith("http") else host)

    # Prefer unique hosts: homepage first, then other paths
    by_host: dict[str, list[str]] = {}
    for u in found:
        h = _host_of(u)
        by_host.setdefault(h, []).append(u)

    ordered: list[str] = []
    for host, urls in by_host.items():
        home = f"https://{host}"
        ordered.append(home)
        for u in urls:
            nu = normalize_url(u)
            if nu.rstrip("/") != home and nu not in ordered:
                ordered.append(nu)
        if len(ordered) >= max_urls:
            break
    return ordered[:max_urls]


def extract_user_domains(text: str) -> list[str]:
    """Unique hostnames from user-provided URLs/domains."""
    hosts: list[str] = []
    seen: set[str] = set()
    for u in extract_user_urls(text):
        h = _host_of(u)
        if h and h not in seen:
            seen.add(h)
            hosts.append(h)
    return hosts


def html_to_text(html: str, *, max_chars: int = 12000) -> str:
    parser = _HTMLToText()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:
        # Fallback: crude strip
        plain = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html or "")
        plain = re.sub(r"(?s)<[^>]+>", " ", plain)
        return re.sub(r"\s+", " ", plain).strip()[:max_chars]
    return parser.text()[:max_chars]


def fetch_url(
    url: str,
    *,
    timeout: float = 18.0,
    max_chars: int = 12000,
    user_agent: str = _DEFAULT_UA,
) -> FetchedSource:
    """HTTP GET + text extraction. Never raises — returns ok=False on failure."""
    url = normalize_url(url)
    if not url:
        return FetchedSource(url="", ok=False, status=None, text="", error="empty url")
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
                "Accept-Language": "es-HN,es;q=0.9,en;q=0.8",
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            ctype = (resp.headers.get("Content-Type") or "").lower()
            raw = resp.read(max_chars * 3)
        if "html" in ctype or raw.lstrip()[:1] == b"<" or b"<!DOCTYPE" in raw[:200].upper():
            text = html_to_text(raw.decode("utf-8", errors="replace"), max_chars=max_chars)
        else:
            text = raw.decode("utf-8", errors="replace")[:max_chars]
        if not text.strip():
            return FetchedSource(
                url=url,
                ok=False,
                status=int(status) if status else None,
                text="",
                error="empty body after extract",
            )
        return FetchedSource(
            url=url,
            ok=True,
            status=int(status) if status else 200,
            text=text,
            error="",
        )
    except urllib.error.HTTPError as exc:
        logger.info("Primary fetch HTTP %s for %s", exc.code, url)
        return FetchedSource(
            url=url, ok=False, status=exc.code, text="", error=str(exc.reason or exc)
        )
    except Exception as exc:
        logger.info("Primary fetch failed for %s: %s", url, exc)
        return FetchedSource(url=url, ok=False, status=None, text="", error=str(exc))


def fetch_user_primary_sources(
    query: str,
    *,
    max_urls: int = 3,
    timeout: float = 18.0,
    max_chars: int = 12000,
) -> list[FetchedSource]:
    """Fetch up to *max_urls* user-named sites (homepage first per host)."""
    urls = extract_user_urls(query, max_urls=max_urls * 2)
    # Deduplicate by host, keep homepage + maybe one path
    selected: list[str] = []
    hosts_done: set[str] = set()
    for u in urls:
        h = _host_of(u)
        if h in hosts_done:
            continue
        hosts_done.add(h)
        selected.append(f"https://{h}")
        if len(selected) >= max_urls:
            break
    return [
        fetch_url(u, timeout=timeout, max_chars=max_chars) for u in selected
    ]


def format_primary_source_block(sources: Iterable[FetchedSource]) -> str:
    """Markdown/text block injected at the top of search_results."""
    parts: list[str] = [
        "=== PRIMARY SOURCES (fetched by MultiAgent from URLs/domains in the user topic) ===",
        "These are the ONLY allowed grounds for claims about the official website.",
        "Do NOT invent Wayback/archive snapshots, emails, phones, colors, or logos "
        "that do not appear in these bodies or in the live search dump below.",
        "",
    ]
    any_src = False
    for src in sources:
        any_src = True
        if src.ok:
            parts.append(f"--- PRIMARY OK | URL: {src.url} | HTTP {src.status} ---")
            parts.append(src.text)
            parts.append(f"--- END PRIMARY {src.url} ---")
        else:
            parts.append(
                f"--- PRIMARY FETCH FAILED | URL: {src.url} | "
                f"status={src.status} error={src.error} ---"
            )
            parts.append(
                "The site could not be retrieved in this run. "
                "State that the official page was not fetched successfully. "
                "Do NOT invent historical archive content for this domain."
            )
            parts.append(f"--- END PRIMARY FAIL {src.url} ---")
        parts.append("")
    if not any_src:
        parts.append("(No user-provided domain/URL detected in the topic.)")
    parts.append("=== END PRIMARY SOURCES ===")
    return "\n".join(parts)
