"""
Fetch user-provided primary URLs for System B (Deep Research).

When a topic names an official website (bare domain or URL), MultiAgent
fetches it *before* grounding so models cannot invent archive pages or
contact data that never appeared in live sources.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Iterable, Optional
from urllib.parse import parse_qs, unquote, urljoin, urlparse

logger = logging.getLogger(__name__)

# Brand / contact signals stripped by plain html_to_text (style/script dropped)
_HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\b")
_JSON_LD_RE = re.compile(
    r'(?is)<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
)
_META_TAG_RE = re.compile(r"(?is)<meta\s+([^>]+)>")
_LINK_TAG_RE = re.compile(r"(?is)<link\s+([^>]+)>")
_ATTR_RE = re.compile(
    r"""(?is)([a-zA-Z_:][-a-zA-Z0-9_:.]*+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))"""
)
_A_HREF_RE = re.compile(r'(?is)<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>')
_IMG_SRC_RE = re.compile(
    r'(?is)<img\s+[^>]*src=["\']([^"\']+)["\'][^>]*(?:alt=["\']([^"\']*)["\'])?'
)
_IMG_ALT_RE = re.compile(
    r'(?is)<img\s+[^>]*alt=["\']([^"\']*)["\'][^>]*src=["\']([^"\']+)["\']'
)
_TITLE_RE = re.compile(r"(?is)<title[^>]*>(.*?)</title>")
_STYLE_BLOCK_RE = re.compile(r"(?is)<style[^>]*>(.*?)</style>")
_INLINE_STYLE_RE = re.compile(r'(?is)style=["\']([^"\']+)["\']')

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
    "schema.org",  # vocabulary in JSON-LD, not a subject site
    "w3.org",
    "example.com",
    "example.org",
    "example.net",
    "localhost",
)

# Bare "domains" that are Latin abbreviations or junk, not websites
_ABBREVIATION_HOSTS = frozenset(
    {
        "e.g",
        "i.e",
        "u.s",
        "u.k",
        "a.m",
        "p.m",
        "n.b",
        "p.s",
        "q.v",
        "cf.",
        "vs.",
        "etc",
        "ie",
        "eg",
    }
)

# Common multi-letter TLDs we accept for bare-domain extraction (not exhaustive)
_KNOWN_MULTI_TLDS = frozenset(
    {
        "com",
        "org",
        "net",
        "edu",
        "gov",
        "mil",
        "int",
        "info",
        "biz",
        "name",
        "pro",
        "io",
        "co",
        "ai",
        "app",
        "dev",
        "me",
        "tv",
        "cc",
        "xyz",
        "online",
        "site",
        "store",
        "shop",
        "blog",
        "tech",
        "health",
        "clinic",
        "dental",
        "hn",
        "mx",
        "gt",
        "sv",
        "ni",
        "cr",
        "pa",
        "us",
        "uk",
        "es",
        "de",
        "fr",
        "it",
        "br",
        "ar",
        "cl",
        "pe",
        "ec",
        "bo",
        "py",
        "uy",
        "ca",
        "au",
        "nz",
        "jp",
        "cn",
        "in",
        "ru",
        "pl",
        "nl",
        "se",
        "no",
        "fi",
        "dk",
        "ch",
        "at",
        "be",
        "pt",
        "ie",
        "za",
        "ph",
        "sg",
        "hk",
        "tw",
        "kr",
        "id",
        "th",
        "vn",
        "my",
        "ae",
        "sa",
        "il",
        "tr",
        "cz",
        "ro",
        "hu",
        "gr",
        "ua",
        "cat",
        "lat",
        "cloud",
        "page",
        "link",
        "live",
        "news",
        "media",
        "agency",
        "studio",
        "design",
        "digital",
        "solutions",
        "group",
        "company",
        "ltd",
        "llc",
    }
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
    # Social / messaging channels discovered on this page (not inventable)
    outbound: list["OutboundPresence"] = field(default_factory=list)


@dataclass
class OutboundPresence:
    """A contact or social channel found as a real href/schema on a page."""

    kind: str  # whatsapp | instagram | facebook | linkedin | tiktok | youtube | x | email | phone | maps | other
    url: str
    handle: str = ""
    phone_digits: str = ""
    email: str = ""
    source_page: str = ""
    note: str = ""


# Hosts we may follow after discovering them on an official page (not as primary subject sites)
_FOLLOWABLE_SOCIAL_HOSTS: tuple[tuple[str, str], ...] = (
    ("instagram.com", "instagram"),
    ("facebook.com", "facebook"),
    ("fb.com", "facebook"),
    ("fb.me", "facebook"),
    ("linkedin.com", "linkedin"),
    ("tiktok.com", "tiktok"),
    ("youtube.com", "youtube"),
    ("youtu.be", "youtube"),
    ("x.com", "x"),
    ("twitter.com", "x"),
    ("threads.net", "threads"),
    ("pinterest.com", "pinterest"),
)


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


def is_plausible_public_host(host: str) -> bool:
    """True if *host* looks like a real public website hostname.

    Rejects Latin abbreviations (e.g., i.e., U.S.), single-letter TLDs,
    IP-like junk, and other false positives from bare-domain regexes.
    """
    h = (host or "").strip().lower().rstrip(".")
    if h.startswith("www."):
        h = h[4:]
    if not h or "." not in h:
        return False
    if h in _ABBREVIATION_HOSTS:
        return False
    # Strip trailing abbreviation period forms already handled; also "e.g."
    if h.rstrip(".") in _ABBREVIATION_HOSTS:
        return False
    labels = h.split(".")
    if len(labels) < 2:
        return False
    tld = labels[-1]
    # TLD must be alphabetic and at least 2 chars (kills e.g / i.e / u.s)
    if not tld.isalpha() or len(tld) < 2:
        return False
    # Each label: alnum/hyphen, no empty
    for lab in labels:
        if not lab or lab.startswith("-") or lab.endswith("-"):
            return False
        if not re.fullmatch(r"[a-z0-9-]+", lab):
            return False
    # Bare two-label hosts need a known-ish TLD (still allow foo.co.uk via 3+ labels)
    if len(labels) == 2 and tld not in _KNOWN_MULTI_TLDS:
        # Allow any 2–24 letter TLD that is not a single common English word pair
        # like "or.the" — require tld length 2–24 and sld length >= 2
        if len(tld) > 24 or len(labels[0]) < 2:
            return False
        # Reject if sld is a single letter (a.com is rare; e.g already dead)
        # Already require sld via labels[0]
    # Reject pure numeric hosts
    if all(lab.isdigit() for lab in labels):
        return False
    return True


def _is_skippable_host(host: str) -> bool:
    h = (host or "").lower().rstrip(".")
    if h.startswith("www."):
        h = h[4:]
    if not h or "." not in h:
        return True
    if not is_plausible_public_host(h):
        return True
    for suf in _SKIP_HOST_SUFFIXES:
        if h == suf or h.endswith("." + suf):
            return True
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


def is_plausible_source_url(url: str) -> bool:
    """Whether a URL is worth listing as a research source (not e.g / schema.org)."""
    u = (url or "").strip()
    if not u:
        return False
    lower = u.lower()
    if lower.startswith(("mailto:", "tel:")):
        return True
    host = _host_of(u if "://" in u else "https://" + u)
    if not host:
        return False
    if not is_plausible_public_host(host):
        return False
    # Vocabulary / non-subject hosts never as primary sources
    for suf in ("schema.org", "w3.org", "example.com", "example.org", "example.net"):
        if host == suf or host.endswith("." + suf):
            return False
    return True


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
        if not is_plausible_public_host(host):
            return
        key = host + urlparse(url).path.rstrip("/").lower()
        if key in seen:
            return
        seen.add(key)
        origin = f"https://{host}"
        found.append(url if urlparse(url).path not in ("", "/") else origin)

    for m in _EXPLICIT_URL_RE.finditer(text):
        _add(m.group(0))

    # Bare domains (example.com) — require a plausible public host shape
    for m in _URL_RE.finditer(text):
        full = m.group(0)
        host = m.group(1)
        if _is_skippable_host(host) or not is_plausible_public_host(host):
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


def _parse_tag_attrs(attr_blob: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _ATTR_RE.finditer(attr_blob or ""):
        key = (m.group(1) or "").lower()
        val = m.group(2) if m.group(2) is not None else (
            m.group(3) if m.group(3) is not None else (m.group(4) or "")
        )
        out[key] = val
    return out


def _abs_url(base_url: str, href: str) -> str:
    href = (href or "").strip()
    if not href or href.startswith(("javascript:", "data:", "mailto:", "tel:")):
        return href
    try:
        return urljoin(base_url if base_url.endswith("/") else base_url + "/", href)
    except Exception:
        return href


def _looks_like_brand_asset(url: str, alt: str = "") -> bool:
    blob = f"{url} {alt}".lower()
    keys = (
        "logo",
        "brand",
        "favicon",
        "icon",
        "marca",
        "isotipo",
        "logotipo",
        "og-image",
        "apple-touch",
        "favicon",
    )
    return any(k in blob for k in keys)


def _format_phone_display(digits: str) -> str:
    """Display form; full digit string is always kept separately for scrub matching."""
    d = re.sub(r"\D", "", digits or "")
    if not d:
        return ""
    return f"+{d}"


def _clean_href(href: str) -> str:
    """Strip trailing punctuation / JSON debris commonly glued to URLs in extracts."""
    s = (href or "").strip()
    # Cut at first obvious junk char that never belongs in a profile/contact URL path
    for sep in ('"', "'", "`", "]", "}", ")", "<", ">", " ", "\n", "\t"):
        if sep in s:
            # Keep scheme://… only up to first junk (but allow query ? & =)
            # Only split on quote/bracket noise, not on ?&=
            if sep in ('"', "'", "`", "]", "}", ")", "<", ">"):
                s = s.split(sep, 1)[0]
    while s and s[-1] in ".,;:!?":
        s = s[:-1]
    return s.strip()


def classify_outbound_url(href: str, *, source_page: str = "") -> Optional[OutboundPresence]:
    """Classify a single href into a structured outbound presence channel."""
    raw = _clean_href(href)
    if not raw:
        return None

    lower = raw.lower()

    # mailto:
    if lower.startswith("mailto:"):
        addr = raw.split(":", 1)[1].split("?", 1)[0].strip()
        if "@" in addr:
            return OutboundPresence(
                kind="email",
                url=f"mailto:{addr}",
                email=addr,
                source_page=source_page,
                note="mailto: link on page",
            )
        return None

    # tel:
    if lower.startswith("tel:"):
        digits = re.sub(r"\D", "", raw.split(":", 1)[1])
        if len(digits) >= 7:
            return OutboundPresence(
                kind="phone",
                url=f"tel:+{digits}",
                phone_digits=digits,
                source_page=source_page,
                note="tel: link on page",
            )
        return None

    # WhatsApp button patterns (phone lives in the URL path / query)
    if "wa.me/" in lower or "api.whatsapp.com" in lower or "whatsapp.com/send" in lower:
        digits = ""
        try:
            parsed = urlparse(raw if "://" in raw else "https://" + raw.lstrip("/"))
            if "wa.me" in (parsed.netloc or "").lower():
                path_head = unquote(parsed.path or "").strip("/").split("/")[0]
                digits = re.sub(r"\D", "", path_head)
            qs = parse_qs(parsed.query or "")
            if qs.get("phone"):
                digits = re.sub(r"\D", "", qs["phone"][0])
        except Exception:
            digits = ""
        if not digits:
            runs = re.findall(r"\d{8,15}", raw)
            digits = runs[0] if runs else ""
        clean_url = f"https://wa.me/{digits}" if digits else (
            raw if raw.lower().startswith("http") else f"https://{raw.lstrip('/')}"
        )
        if len(digits) >= 8:
            return OutboundPresence(
                kind="whatsapp",
                url=clean_url,
                phone_digits=digits,
                source_page=source_page,
                note="WhatsApp button / messaging link on page",
            )
        return OutboundPresence(
            kind="whatsapp",
            url=clean_url,
            source_page=source_page,
            note="WhatsApp link without parseable phone",
        )

    # Social profiles
    try:
        parsed = urlparse(raw if "://" in raw else "https://" + raw.lstrip("/"))
    except Exception:
        return None
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = (parsed.path or "").strip("/")
    parts = [p for p in path.split("/") if p]

    for suf, kind in _FOLLOWABLE_SOCIAL_HOSTS:
        if host == suf or host.endswith("." + suf):
            handle = ""
            # Skip non-profile paths
            skip_first = {
                "p",
                "reel",
                "reels",
                "stories",
                "explore",
                "share",
                "watch",
                "channel",
                "c",
                "user",
                "in",
                "company",
                "posts",
                "status",
                "hashtag",
                "tag",
                "search",
                "accounts",
                "about",
                "privacy",
            }
            if parts:
                if kind == "linkedin":
                    # linkedin.com/in/handle or /company/handle
                    if len(parts) >= 2 and parts[0] in ("in", "company", "school"):
                        handle = parts[1]
                    elif parts[0] not in skip_first:
                        handle = parts[0]
                elif kind == "youtube":
                    if parts[0].startswith("@"):
                        handle = parts[0].lstrip("@")
                    elif parts[0] in ("c", "channel", "user") and len(parts) >= 2:
                        handle = parts[1]
                    elif parts[0] not in skip_first:
                        handle = parts[0].lstrip("@")
                else:
                    cand = parts[0].lstrip("@")
                    if cand.lower() not in skip_first and not cand.startswith("?"):
                        handle = cand
            profile_url = raw if raw.lower().startswith("http") else f"https://{raw.lstrip('/')}"
            # Canonical-ish profile URL when we have a handle
            if handle and kind == "instagram":
                profile_url = f"https://www.instagram.com/{handle}/"
            elif handle and kind == "facebook":
                profile_url = f"https://www.facebook.com/{handle}"
            elif handle and kind == "x":
                profile_url = f"https://x.com/{handle}"
            elif handle and kind == "tiktok":
                profile_url = f"https://www.tiktok.com/@{handle.lstrip('@')}"
            return OutboundPresence(
                kind=kind,
                url=profile_url,
                handle=handle.lstrip("@"),
                source_page=source_page,
                note=f"{kind} profile link on page",
            )

    if "maps.google" in lower or "goo.gl/maps" in lower or "g.page" in lower or "maps.app.goo.gl" in lower:
        return OutboundPresence(
            kind="maps",
            url=raw if raw.lower().startswith("http") else f"https://{raw.lstrip('/')}",
            source_page=source_page,
            note="Maps link on page",
        )

    return None


def extract_outbound_presence(
    html: str = "",
    *,
    base_url: str = "",
    text: str = "",
    max_links: int = 24,
) -> list[OutboundPresence]:
    """Collect social/messaging channels from HTML hrefs, JSON-LD sameAs, or plain text URLs.

    Domain-agnostic: only reports links literally present. Used to follow
    Instagram/Facebook/etc. after the official page is fetched, and to decode
    WhatsApp button phones into contact evidence for the corpus.
    """
    found: list[OutboundPresence] = []
    seen: set[str] = set()
    source_page = normalize_url(base_url) if base_url else ""

    def _add(href: str) -> None:
        if len(found) >= max_links:
            return
        op = classify_outbound_url(href, source_page=source_page)
        if not op:
            return
        key = f"{op.kind}|{op.url.lower().rstrip('/')}|{op.phone_digits}|{op.email.lower()}"
        if key in seen:
            return
        seen.add(key)
        found.append(op)

    # From anchor hrefs
    for m in _A_HREF_RE.finditer(html or ""):
        href = (m.group(1) or "").strip()
        if not href:
            continue
        if href.lower().startswith(("http://", "https://", "mailto:", "tel:")):
            _add(href)
        elif base_url and not href.startswith(("#", "javascript:")):
            _add(_abs_url(base_url, href))

    # JSON-LD sameAs / url / telephone / email
    for m in _JSON_LD_RE.finditer(html or ""):
        raw_json = (m.group(1) or "").strip()
        if not raw_json:
            continue
        try:
            data = json.loads(raw_json)
        except Exception:
            continue
        stack = [data]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                for k, v in cur.items():
                    kl = str(k).lower()
                    if kl in ("sameas", "url", "logo") and isinstance(v, str):
                        _add(v)
                    elif kl == "sameas" and isinstance(v, list):
                        for item in v:
                            if isinstance(item, str):
                                _add(item)
                    elif kl in ("telephone", "phone") and isinstance(v, str):
                        digits = re.sub(r"\D", "", v)
                        if len(digits) >= 7:
                            _add(f"tel:{digits}")
                    elif kl == "email" and isinstance(v, str) and "@" in v:
                        _add(f"mailto:{v}")
                    else:
                        if isinstance(v, (dict, list)):
                            stack.append(v)
            elif isinstance(cur, list):
                stack.extend(cur)

    # Plain text / already-extracted blocks: scan for URLs (cleaned)
    blob = text or ""
    for m in _EXPLICIT_URL_RE.finditer(blob):
        _add(_clean_href(m.group(0)))
    # wa.me without scheme — digits only (avoid swallowing JSON after the number)
    for m in re.finditer(r"(?i)(?:https?://)?wa\.me/(\d{8,15})", blob):
        _add(f"https://wa.me/{m.group(1)}")
    for m in re.finditer(
        r"(?i)(?:https?://)?api\.whatsapp\.com/send\?[^ \n\"'<>]{0,120}phone=(\d{8,15})",
        blob,
    ):
        _add(f"https://wa.me/{m.group(1)}")

    return found


def format_outbound_presence_block(
    links: Iterable[OutboundPresence],
    *,
    title: str = "OUTBOUND PRESENCE (decoded from official-page buttons / schema)",
) -> str:
    """Corpus block: WhatsApp phones, social handles — safe for scrub + grounding."""
    items = list(links)
    if not items:
        return ""
    parts: list[str] = [
        f"=== {title} ===",
        "These channels were linked from the official page (buttons, schema.org, etc.).",
        "Messaging phone digits from WhatsApp links ARE valid contact evidence.",
        "Social profile URLs should be followed for bio/posts via live search + HTTP fetch.",
        "Do NOT invent other handles or phone numbers beyond this list.",
        "",
    ]
    for op in items:
        if op.kind == "whatsapp":
            disp = _format_phone_display(op.phone_digits) if op.phone_digits else ""
            parts.append(f"- WhatsApp link: {op.url}")
            if op.phone_digits:
                parts.append(
                    f"  WhatsApp phone (from button): {disp} "
                    f"(digits {op.phone_digits})"
                )
                # Also write digits alone so scrub/phone matching always hits
                parts.append(f"  phone digits: {op.phone_digits}")
                parts.append(f"  tel:+{op.phone_digits}")
            if op.source_page:
                parts.append(f"  discovered_on: {op.source_page}")
        elif op.kind == "email":
            parts.append(f"- Email: {op.email} ({op.url})")
        elif op.kind == "phone":
            disp = _format_phone_display(op.phone_digits)
            parts.append(f"- Phone link: {op.url} → {disp} (digits {op.phone_digits})")
        elif op.kind in {k for _, k in _FOLLOWABLE_SOCIAL_HOSTS}:
            handle_bit = f" @{op.handle}" if op.handle else ""
            parts.append(f"- {op.kind.title()} profile{handle_bit}: {op.url}")
            if op.handle:
                parts.append(f"  handle: {op.handle}")
                parts.append(f"  follow_for_posts: yes — search recent public posts for this handle")
            if op.source_page:
                parts.append(f"  discovered_on: {op.source_page}")
        else:
            parts.append(f"- {op.kind}: {op.url}")
            if op.source_page:
                parts.append(f"  discovered_on: {op.source_page}")
    parts.append(f"=== END {title.split('(')[0].strip()} ===")
    return "\n".join(parts)


def outbound_presence_search_facets(
    links: Iterable[OutboundPresence],
    *,
    max_facets: int = 10,
) -> list[str]:
    """Live-search facet strings derived from discovered social/messaging links."""
    facets: list[str] = []
    seen: set[str] = set()

    def _add(q: str) -> None:
        q = " ".join((q or "").split()).strip()
        if not q:
            return
        key = q.casefold()
        if key in seen:
            return
        seen.add(key)
        facets.append(q[:150])

    for op in links:
        if op.kind == "whatsapp":
            # Don't spam phone as search; contact is already in corpus
            continue
        if op.kind in ("email", "phone", "maps"):
            continue
        if op.url:
            _add(op.url)
        if op.handle and op.kind == "instagram":
            _add(f"site:instagram.com/{op.handle}")
            _add(f"instagram.com/{op.handle}")
            _add(f"@{op.handle} instagram posts")
            _add(f'"{op.handle}" instagram')
        elif op.handle and op.kind == "facebook":
            _add(f"site:facebook.com/{op.handle}")
            _add(f"facebook.com/{op.handle}")
            _add(f'"{op.handle}" facebook posts OR page')
        elif op.handle and op.kind == "x":
            _add(f"site:x.com/{op.handle}")
            _add(f"@{op.handle} twitter OR x.com")
        elif op.handle and op.kind == "tiktok":
            _add(f"site:tiktok.com/@{op.handle.lstrip('@')}")
            _add(f"@{op.handle} tiktok")
        elif op.handle and op.kind == "linkedin":
            _add(f"site:linkedin.com {op.handle}")
            _add(f'"{op.handle}" linkedin')
        elif op.handle and op.kind == "youtube":
            _add(f"site:youtube.com {op.handle}")
            _add(f'"{op.handle}" youtube')
        elif op.url:
            _add(f"site:{_host_of(op.url)}")
        if len(facets) >= max_facets:
            break
    return facets[:max_facets]


def fetch_outbound_presence_pages(
    links: Iterable[OutboundPresence],
    *,
    max_fetch: int = 3,
    timeout: float = 8.0,
    max_chars: int = 6000,
) -> list[FetchedSource]:
    """HTTP-fetch social profile pages discovered on the official site.

    Many social hosts return login walls; still attempt fetch and record status.
    WhatsApp / tel / mailto are not HTTP-fetched (already decoded into corpus).
    Fetches run in parallel (bounded) to cut latency.
    """
    targets: list[OutboundPresence] = []
    seen_hosts_paths: set[str] = set()
    skip_kinds = {"whatsapp", "email", "phone", "maps"}
    for op in links:
        if len(targets) >= max_fetch:
            break
        if op.kind in skip_kinds:
            continue
        url = normalize_url(op.url)
        if not url or not is_plausible_source_url(url):
            continue
        key = _host_of(url) + urlparse(url).path.rstrip("/").lower()
        if key in seen_hosts_paths:
            continue
        seen_hosts_paths.add(key)
        targets.append(op)

    if not targets:
        return []

    def _one(op: OutboundPresence) -> FetchedSource:
        url = normalize_url(op.url)
        src = fetch_url(
            url,
            timeout=timeout,
            max_chars=max_chars,
            extract_signals=True,
            follow_outbound=False,
        )
        if src.ok and src.text:
            header = (
                f"[Linked {op.kind} profile fetch | handle={op.handle or '—'} | "
                f"from_official={op.source_page or '—'}]\n"
            )
            return FetchedSource(
                url=src.url,
                ok=src.ok,
                status=src.status,
                text=(header + src.text)[: max_chars + 500],
                error=src.error,
                outbound=src.outbound,
            )
        return src

    results: list[FetchedSource] = []
    workers = min(3, len(targets))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_one, op): op for op in targets}
        for fut in as_completed(futs):
            try:
                results.append(fut.result())
            except Exception as exc:
                op = futs[fut]
                results.append(
                    FetchedSource(
                        url=normalize_url(op.url),
                        ok=False,
                        status=None,
                        text="",
                        error=str(exc),
                    )
                )
    # Stable order matching targets
    by_url = {r.url.rstrip("/"): r for r in results}
    ordered: list[FetchedSource] = []
    for op in targets:
        u = normalize_url(op.url).rstrip("/")
        if u in by_url:
            ordered.append(by_url[u])
        else:
            # prefix match fallback
            for k, r in by_url.items():
                if k.startswith(u) or u.startswith(k):
                    ordered.append(r)
                    break
    return ordered or results


def format_linked_presence_fetch_block(sources: Iterable[FetchedSource]) -> str:
    """Block for HTTP-fetched social profiles linked from the official site."""
    items = list(sources)
    if not items:
        return ""
    parts: list[str] = [
        "=== LINKED PRESENCE FETCHES (social/profile pages found on official site) ===",
        "HTTP bodies may be partial (login walls). Prefer live search dump for posts.",
        "Only use facts that appear below or in the live search dump.",
        "",
    ]
    for src in items:
        if src.ok:
            parts.append(f"--- LINKED OK | URL: {src.url} | HTTP {src.status} ---")
            parts.append(src.text)
            parts.append(f"--- END LINKED {src.url} ---")
        else:
            parts.append(
                f"--- LINKED FETCH FAILED | URL: {src.url} | "
                f"status={src.status} error={src.error} ---"
            )
            parts.append(
                "Profile page could not be retrieved via HTTP. "
                "Rely on live search facets for this URL/handle; do not invent posts."
            )
            parts.append(f"--- END LINKED FAIL {src.url} ---")
        parts.append("")
    parts.append("=== END LINKED PRESENCE FETCHES ===")
    return "\n".join(parts)


def collect_outbound_from_sources(
    sources: Iterable[FetchedSource],
) -> list[OutboundPresence]:
    """Merge outbound channels from primary fetches (HTML-derived + text scan)."""
    merged: list[OutboundPresence] = []
    seen: set[str] = set()
    for src in sources:
        candidates = list(src.outbound or [])
        if src.ok and src.text:
            candidates.extend(
                extract_outbound_presence(text=src.text, base_url=src.url)
            )
        for op in candidates:
            key = f"{op.kind}|{op.url.lower().rstrip('/')}|{op.phone_digits}|{op.email.lower()}"
            if key in seen:
                continue
            seen.add(key)
            if not op.source_page:
                op = OutboundPresence(
                    kind=op.kind,
                    url=op.url,
                    handle=op.handle,
                    phone_digits=op.phone_digits,
                    email=op.email,
                    source_page=src.url,
                    note=op.note,
                )
            merged.append(op)
    return merged


def extract_structured_signals(html: str, base_url: str = "", *, max_chars: int = 6000) -> str:
    """Pull brand/contact signals that plain text extraction drops.

    JSON-LD, meta/og tags, CSS hex colors, social/WhatsApp links, logo images.
    Domain-agnostic: only reports strings literally present in the HTML.
    """
    if not html or not html.strip():
        return ""

    base = normalize_url(base_url) if base_url else ""
    lines: list[str] = [
        "--- STRUCTURED EXTRACTS (literal from HTML; not model-invented) ---",
        "Use these for contact, brand colors, logos, and schema when present.",
        "Do NOT invent additional hex colors, fonts, or asset URLs beyond this list.",
    ]

    title_m = _TITLE_RE.search(html)
    if title_m:
        title = re.sub(r"\s+", " ", title_m.group(1)).strip()
        if title:
            lines.append(f"HTML title: {title}")

    # Meta / Open Graph
    meta_bits: list[str] = []
    for m in _META_TAG_RE.finditer(html):
        attrs = _parse_tag_attrs(m.group(1))
        name = (attrs.get("name") or attrs.get("property") or attrs.get("itemprop") or "").strip()
        content = (attrs.get("content") or "").strip()
        if not name or not content:
            continue
        name_l = name.lower()
        if name_l in (
            "description",
            "keywords",
            "author",
            "og:title",
            "og:description",
            "og:image",
            "og:url",
            "og:site_name",
            "twitter:image",
            "twitter:title",
            "twitter:description",
            "theme-color",
        ) or name_l.startswith("og:") or name_l.startswith("twitter:"):
            if name_l in ("og:image", "twitter:image") and base:
                content = _abs_url(base, content)
            meta_bits.append(f"{name}: {content}")
    if meta_bits:
        lines.append("Meta / Open Graph:")
        # de-dupe preserve order
        seen_m: set[str] = set()
        for bit in meta_bits:
            if bit in seen_m:
                continue
            seen_m.add(bit)
            lines.append(f"  - {bit}")

    # Icons / canonical
    for m in _LINK_TAG_RE.finditer(html):
        attrs = _parse_tag_attrs(m.group(1))
        rel = (attrs.get("rel") or "").lower()
        href = (attrs.get("href") or "").strip()
        if not href:
            continue
        if any(k in rel for k in ("icon", "apple-touch-icon", "shortcut icon", "mask-icon")):
            lines.append(f"Icon link ({rel}): {_abs_url(base, href) if base else href}")
        elif "canonical" in rel:
            lines.append(f"Canonical: {_abs_url(base, href) if base else href}")

    # JSON-LD (schema.org) — keep compact JSON
    for i, m in enumerate(_JSON_LD_RE.finditer(html), start=1):
        raw_json = (m.group(1) or "").strip()
        if not raw_json:
            continue
        try:
            parsed = json.loads(raw_json)
            compact = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            compact = re.sub(r"\s+", " ", raw_json)
        if len(compact) > 2500:
            compact = compact[:2500] + "…"
        lines.append(f"JSON-LD block {i}: {compact}")

    # CSS / inline hex colors (brand palette candidates)
    color_src = " ".join(_STYLE_BLOCK_RE.findall(html)) + " " + " ".join(
        _INLINE_STYLE_RE.findall(html)
    )
    colors: list[str] = []
    seen_c: set[str] = set()
    for c in _HEX_COLOR_RE.findall(color_src):
        key = c.lower()
        # skip near-black/white noise often used for text
        if key in ("#000", "#000000", "#fff", "#ffffff", "#111", "#111111", "#222", "#222222"):
            continue
        if key in seen_c:
            continue
        seen_c.add(key)
        colors.append(c)
        if len(colors) >= 24:
            break
    if colors:
        lines.append("Hex colors found in page CSS/inline styles: " + ", ".join(colors))

    # Contact / social hrefs
    contact_links: list[str] = []
    seen_l: set[str] = set()
    contact_markers = (
        "wa.me",
        "api.whatsapp.com",
        "whatsapp.com",
        "instagram.com",
        "facebook.com",
        "fb.com",
        "linkedin.com",
        "tiktok.com",
        "youtube.com",
        "x.com",
        "twitter.com",
        "mailto:",
        "tel:",
        "maps.google",
        "goo.gl/maps",
        "g.page",
    )
    for m in _A_HREF_RE.finditer(html):
        href = (m.group(1) or "").strip()
        if not href:
            continue
        href_l = href.lower()
        if not any(k in href_l for k in contact_markers):
            continue
        resolved = href
        if href_l.startswith(("http://", "https://")) and base:
            resolved = href
        elif href_l.startswith(("mailto:", "tel:", "https://", "http://")):
            resolved = href
        elif base:
            resolved = _abs_url(base, href)
        key = resolved.lower()
        if key in seen_l:
            continue
        seen_l.add(key)
        contact_links.append(resolved)
        if len(contact_links) >= 20:
            break
    if contact_links:
        lines.append("Contact / social links found in HTML:")
        for cl in contact_links:
            lines.append(f"  - {cl}")

    # Decoded outbound (WhatsApp phone digits, social handles) — critical for contact
    outbound = extract_outbound_presence(html, base_url=base)
    if outbound:
        lines.append("Decoded contact / social channels (from buttons & schema):")
        for op in outbound:
            if op.kind == "whatsapp" and op.phone_digits:
                disp = _format_phone_display(op.phone_digits)
                lines.append(
                    f"  - WhatsApp phone from button: {disp} "
                    f"(digits {op.phone_digits}) link={op.url}"
                )
            elif op.kind in {k for _, k in _FOLLOWABLE_SOCIAL_HOSTS}:
                h = f"@{op.handle}" if op.handle else op.url
                lines.append(f"  - {op.kind} profile: {h} → {op.url}")
            elif op.kind == "email":
                lines.append(f"  - email: {op.email}")
            elif op.kind == "phone" and op.phone_digits:
                lines.append(
                    f"  - phone: {_format_phone_display(op.phone_digits)} "
                    f"(digits {op.phone_digits})"
                )
            else:
                lines.append(f"  - {op.kind}: {op.url}")

    # Brand-ish images
    images: list[str] = []
    seen_i: set[str] = set()

    def _add_img(src: str, alt: str = "") -> None:
        if not src:
            return
        abs_src = _abs_url(base, src) if base else src
        if not _looks_like_brand_asset(abs_src, alt) and "imagenes/" not in abs_src.lower():
            # Still keep first few img if alt/src empty and path is site-local
            if not (base and _host_of(abs_src) == _host_of(base)):
                return
            if not re.search(r"\.(png|jpe?g|svg|webp)(?:\?|$)", abs_src, re.I):
                return
        key = abs_src.lower()
        if key in seen_i:
            return
        seen_i.add(key)
        label = f"{abs_src}" + (f' (alt="{alt}")' if alt else "")
        images.append(label)

    for m in _IMG_SRC_RE.finditer(html):
        _add_img(m.group(1), m.group(2) or "")
    for m in _IMG_ALT_RE.finditer(html):
        _add_img(m.group(2), m.group(1) or "")
    # Prefer logo-named first
    images_sorted = sorted(
        images,
        key=lambda s: (0 if "logo" in s.lower() else 1, s),
    )[:12]
    if images_sorted:
        lines.append("Image assets (logo/brand candidates):")
        for im in images_sorted:
            lines.append(f"  - {im}")

    lines.append("--- END STRUCTURED EXTRACTS ---")
    block = "\n".join(lines)
    # Only keep if we found something beyond the header/footer labels
    useful = any(
        x in block
        for x in (
            "JSON-LD",
            "Hex colors",
            "Contact / social",
            "Decoded contact",
            "Image assets",
            "Meta / Open Graph",
            "Icon link",
            "HTML title:",
        )
    )
    if not useful:
        return ""
    return block[:max_chars]


def fetch_url(
    url: str,
    *,
    timeout: float = 18.0,
    max_chars: int = 12000,
    user_agent: str = _DEFAULT_UA,
    extract_signals: bool = True,
    follow_outbound: bool = True,
) -> FetchedSource:
    """HTTP GET + text extraction. Never raises — returns ok=False on failure.

    When *extract_signals* is True, append STRUCTURED EXTRACTS (brand/contact).
    When *follow_outbound* is True, populate ``FetchedSource.outbound`` for
    downstream social/WhatsApp follow-up (no second hop inside this call).
    """
    url = normalize_url(url)
    if not url:
        return FetchedSource(url="", ok=False, status=None, text="", error="empty url")
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
                "Accept-Language": "es,es-419;q=0.9,en;q=0.8",
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            ctype = (resp.headers.get("Content-Type") or "").lower()
            raw = resp.read(max(max_chars * 3, 200_000))
        decoded = raw.decode("utf-8", errors="replace")
        outbound: list[OutboundPresence] = []
        if "html" in ctype or raw.lstrip()[:1] == b"<" or b"<!DOCTYPE" in raw[:200].upper():
            text = html_to_text(decoded, max_chars=max_chars)
            if extract_signals:
                signals = extract_structured_signals(decoded, base_url=url, max_chars=6000)
                if signals:
                    budget = max_chars + 6000
                    combined = (text + "\n\n" + signals).strip() if text.strip() else signals
                    text = combined[:budget]
            if follow_outbound:
                outbound = extract_outbound_presence(decoded, base_url=url)
        else:
            text = decoded[:max_chars]
        if not text.strip():
            return FetchedSource(
                url=url,
                ok=False,
                status=int(status) if status else None,
                text="",
                error="empty body after extract",
                outbound=outbound,
            )
        return FetchedSource(
            url=url,
            ok=True,
            status=int(status) if status else 200,
            text=text,
            error="",
            outbound=outbound,
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
    timeout: float = 12.0,
    max_chars: int = 10000,
) -> list[FetchedSource]:
    """Fetch up to *max_urls* user-named sites (homepage first per host).

    Parallel GETs when multiple domains; skips implausible hosts (e.g. ``e.g``).
    """
    urls = extract_user_urls(query, max_urls=max_urls * 2)
    # Deduplicate by host, keep homepage + maybe one path
    selected: list[str] = []
    hosts_done: set[str] = set()
    for u in urls:
        h = _host_of(u)
        if not h or h in hosts_done:
            continue
        if not is_plausible_public_host(h) or _is_skippable_host(h):
            continue
        hosts_done.add(h)
        selected.append(f"https://{h}")
        if len(selected) >= max_urls:
            break
    if not selected:
        return []
    if len(selected) == 1:
        return [fetch_url(selected[0], timeout=timeout, max_chars=max_chars)]

    results: dict[str, FetchedSource] = {}
    workers = min(3, len(selected))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {
            pool.submit(fetch_url, u, timeout=timeout, max_chars=max_chars): u
            for u in selected
        }
        for fut in as_completed(futs):
            u = futs[fut]
            try:
                results[u] = fut.result()
            except Exception as exc:
                results[u] = FetchedSource(
                    url=u, ok=False, status=None, text="", error=str(exc)
                )
    return [results[u] for u in selected if u in results]


def format_primary_source_block(sources: Iterable[FetchedSource]) -> str:
    """Markdown/text block injected at the top of search_results."""
    parts: list[str] = [
        "=== PRIMARY SOURCES (fetched by MultiAgent from URLs/domains in the user topic) ===",
        "Highest-trust evidence for the OFFICIAL website only.",
        "Also use the LIVE WEB SEARCH DUMP below for third-party / open-web findings",
        "(Maps, directories, social, news, reviews) about the same entity.",
        "Do NOT invent Wayback/archive snapshots, emails, phones, colors, logos, or",
        "citation URLs that do not appear in these bodies or in the live search dump.",
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


# PRIMARY OK blocks produced by format_primary_source_block
_PRIMARY_OK_BLOCK_RE = re.compile(
    r"--- PRIMARY OK \| URL: (\S+) \| HTTP \d+ ---\n(.*?)\n--- END PRIMARY \1 ---",
    re.DOTALL,
)
_STRUCTURED_EXTRACTS_RE = re.compile(
    r"--- STRUCTURED EXTRACTS \(literal from HTML; not model-invented\) ---\n"
    r"(.*?)\n--- END STRUCTURED EXTRACTS ---",
    re.DOTALL,
)
_DENIAL_OF_SITE_RE = re.compile(
    r"(?is)\b("
    r"no\s+(?:direct\s+)?hits?|"
    r"no\s+(?:official\s+)?website|"
    r"yielded\s+no|"
    r"could\s+not\s+be\s+verified|"
    r"cannot\s+be\s+verified|"
    r"website\s+(?:not\s+found|unavailable)|"
    r"no\s+digital\s+footprint|"
    r"digital\s+footprint:\s*no\s|"
    r"existence:\s*no\s+proof"
    r")\b"
)


def extract_primary_ok_blocks(search_results: str) -> list[tuple[str, str]]:
    """Return ``(url, body)`` pairs for successful host PRIMARY fetches."""
    if not search_results:
        return []
    out: list[tuple[str, str]] = []
    for m in _PRIMARY_OK_BLOCK_RE.finditer(search_results):
        url = (m.group(1) or "").strip()
        body = (m.group(2) or "").strip()
        if url and body:
            out.append((url, body))
    return out


def merge_host_verified_primary(
    content: str,
    sources: Optional[list[str]],
    search_results: str,
    *,
    max_appendix_chars: int = 4500,
) -> tuple[str, list[str]]:
    """Ensure successful PRIMARY fetches survive model omissions and denials.

    Free-tier grounding/synthesis models sometimes ignore a successful
    ``PRIMARY OK`` block and claim the official site does not exist, or drop
    brand colors / WhatsApp / logo URLs from the prose. When the host already
    fetched the page, re-inject those facts and source URLs.
    """
    blocks = extract_primary_ok_blocks(search_results or "")
    src_list: list[str] = list(sources or [])
    text = content or ""
    if not blocks:
        return text, src_list

    def _add_source(u: str) -> None:
        u = (u or "").strip()
        if not u or not is_plausible_source_url(u):
            return
        key = u.rstrip("/").lower()
        if any(s.rstrip("/").lower() == key for s in src_list):
            return
        src_list.append(u)

    brand_tokens: list[str] = []
    appendix_chunks: list[str] = []

    for url, body in blocks:
        _add_source(url)
        # Asset / contact URLs from the fetch body
        for u in re.findall(
            r"https?://[^\s\)\]\"'>,;]+", body
        )[:24]:
            u = u.rstrip(".,);")
            if any(
                k in u.lower()
                for k in (
                    "wa.me",
                    "whatsapp",
                    "instagram.com",
                    "facebook.com",
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".svg",
                    ".webp",
                    "logo",
                )
            ):
                _add_source(u)
                brand_tokens.append(u)
        for m in _HEX_COLOR_RE.findall(body):
            if m.lower() not in {"#000", "#000000", "#fff", "#ffffff", "#555"}:
                brand_tokens.append(m)
        for m in re.finditer(r"wa\.me/(\d{8,15})", body, re.I):
            brand_tokens.append(m.group(0))
            brand_tokens.append(m.group(1))

        structured = None
        sm = _STRUCTURED_EXTRACTS_RE.search(body)
        if sm:
            structured = sm.group(1).strip()
        # Prefer structured extracts for the appendix; else a short plain snippet
        snippet = structured or re.sub(r"\s+", " ", body)[:1200]
        appendix_chunks.append(f"### {url}\n{snippet}")

    text_l = text.lower()
    hosts = {_host_of(u) for u, _ in blocks if _host_of(u)}
    host_mentioned = any(h in text_l for h in hosts if h)
    denial = bool(_DENIAL_OF_SITE_RE.search(text))
    missing_brand = [
        t for t in brand_tokens if t and t.lower() not in text_l
    ]
    # De-dupe missing while preserving order
    seen_m: set[str] = set()
    missing_unique: list[str] = []
    for t in missing_brand:
        k = t.lower()
        if k in seen_m:
            continue
        seen_m.add(k)
        missing_unique.append(t)

    needs_appendix = (
        denial
        or not host_mentioned
        or len(missing_unique) >= 2
        or (not src_list and blocks)
    )
    if needs_appendix and appendix_chunks:
        note = (
            "\n\n## Host-verified primary sources (HTTP fetch by MultiAgent)\n"
            "The following was retrieved directly from user-named official URL(s). "
            "Treat as ground truth even if the narrative above understated the site.\n\n"
        )
        body_app = "\n\n".join(appendix_chunks)
        if len(body_app) > max_appendix_chars:
            body_app = body_app[: max_appendix_chars - 1] + "…"
        text = text.rstrip() + note + body_app + "\n"

    # Primary URLs first in sources list
    primary_urls = [u for u, _ in blocks]
    rest = [s for s in src_list if s.rstrip("/").lower() not in {
        p.rstrip("/").lower() for p in primary_urls
    }]
    ordered = []
    for p in primary_urls:
        if is_plausible_source_url(p):
            ordered.append(p)
    ordered.extend(rest)
    return text, ordered
