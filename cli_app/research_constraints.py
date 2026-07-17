"""
Extract grounded constraints from a research report for vibe-coding steps.

When /do chains research → vibe, the coder otherwise invents brand colors,
emails, maps, and bios. This module builds a strict instruction block from
strings that already appear in the research corpus — domain-agnostic.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

from core.search_guards import extract_emails, extract_phones, extract_urls

_HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")
_WA_RE = re.compile(r"(?:https?://)?(?:wa\.me|api\.whatsapp\.com/send\?[^\s]*phone=)/?(\d{8,15})", re.I)
_HANDLE_RE = re.compile(
    r"(?i)\b(?:instagram|facebook|tiktok|linkedin|youtube|x(?:\.com)?|twitter)\s*"
    r"(?:profile|handle|account)?\s*[:@]?\s*@?([A-Za-z0-9._]{2,40})"
)
_IG_URL_RE = re.compile(
    r"(?i)https?://(?:www\.)?instagram\.com/([A-Za-z0-9._]+)/?"
)
_FB_URL_RE = re.compile(
    r"(?i)https?://(?:www\.)?(?:facebook|fb)\.com/([A-Za-z0-9.]+)/?"
)
_LOGO_URL_RE = re.compile(
    r"(?i)(https?://[^\s\)\]\"'>,;]+(?:logo|favicon|icon|brand|ventana|marca)[^\s\)\]\"'>,;]*"
    r"\.(?:png|jpe?g|svg|webp)(?:\?[^\s\)\]\"'>,;]*)?)"
)
_IMG_URL_RE = re.compile(
    r"(?i)(https?://[^\s\)\]\"'>,;]+\.(?:png|jpe?g|svg|webp)(?:\?[^\s\)\]\"'>,;]*)?)"
)
_GAP_LINE_RE = re.compile(
    r"(?im)^[*\-•]?\s*(email|e-mail|hours?|horario|reviews?|testimonial|"
    r"typography|font|phone|tel[eé]fono|address|dirección)\s*[:：\-–]?\s*"
    r"(not found|no .*found|missing|unavailable|no encontrado|no hay|sin datos).*$"
)
# Soft address cues (do not invent; only quote if present as longer line)
_ADDRESS_HINT_RE = re.compile(
    r"(?im)^[*\-•]?\s*.{0,40}(?:address|dirección|ubicaci[oó]n|location|col\.|colonia|"
    r"calle|ave\.|avenida).{5,120}$"
)


def _unique(items: Iterable[str], *, limit: int = 24) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for x in items:
        s = (x or "").strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= limit:
            break
    return out


def _hex_colors(text: str) -> list[str]:
    # Skip pure black/white noise
    skip = {"#000", "#000000", "#fff", "#ffffff"}
    found = []
    for m in _HEX_RE.findall(text or ""):
        if m.lower() in skip:
            continue
        found.append(m)
    return _unique(found, limit=12)


def _whatsapp(text: str) -> list[str]:
    out = []
    for m in _WA_RE.finditer(text or ""):
        digits = m.group(1)
        out.append(f"https://wa.me/{digits} (phone digits {digits})")
    # Also bare wa.me URLs via extract_urls
    for u in extract_urls(text or ""):
        if "wa.me" in u.lower() or "whatsapp" in u.lower():
            out.append(u)
    return _unique(out, limit=6)


def _social(text: str) -> list[str]:
    out: list[str] = []
    for m in _IG_URL_RE.finditer(text or ""):
        h = m.group(1)
        if h.lower() in {"p", "reel", "reels", "stories", "explore"}:
            continue
        out.append(f"Instagram @{h} → https://www.instagram.com/{h}/")
    for m in _FB_URL_RE.finditer(text or ""):
        h = m.group(1)
        if h.lower() in {"share", "watch", "pages"}:
            continue
        out.append(f"Facebook → https://www.facebook.com/{h}")
    for u in extract_urls(text or ""):
        ul = u.lower()
        if any(
            k in ul
            for k in (
                "instagram.com/",
                "facebook.com/",
                "tiktok.com/",
                "linkedin.com/",
                "youtube.com/",
                "x.com/",
                "twitter.com/",
            )
        ):
            out.append(u)
    return _unique(out, limit=10)


def _asset_urls(text: str) -> list[str]:
    logos = list(_LOGO_URL_RE.findall(text or ""))
    imgs: list[str] = []
    for u in extract_urls(text or ""):
        if re.search(r"\.(png|jpe?g|svg|webp)(?:\?|$)", u, re.I):
            imgs.append(u)
    # Prefer logo-named URLs first
    return _unique([*logos, *imgs], limit=12)


def _gaps(text: str) -> list[str]:
    lines = []
    for m in _GAP_LINE_RE.finditer(text or ""):
        lines.append(m.group(0).strip()[:200])
    # Common explicit gap phrases
    for phrase in (
        "no email",
        "email: not found",
        "email not found",
        "no phone",
        "hours: not",
        "no review",
        "no testimonial",
    ):
        if phrase in (text or "").lower():
            lines.append(f"Gap noted in research: {phrase}")
    return _unique(lines, limit=12)


def _address_lines(text: str) -> list[str]:
    lines = []
    for m in _ADDRESS_HINT_RE.finditer(text or ""):
        line = re.sub(r"^[*\-•\s]+", "", m.group(0)).strip()
        if len(line) < 12:
            continue
        # skip pure section headers
        if line.lower().rstrip(":") in ("address", "location", "dirección", "ubicación"):
            continue
        lines.append(line[:220])
    return _unique(lines, limit=6)


def extract_research_facts(report_text: str, sources: Optional[list[str]] = None) -> dict[str, list[str]]:
    """Parse a research report (+ optional source URLs) into fact buckets."""
    blob = report_text or ""
    if sources:
        blob = blob + "\n" + "\n".join(sources)
    return {
        "colors": _hex_colors(blob),
        "phones": _unique(extract_phones(blob), limit=8),
        "emails": _unique(extract_emails(blob), limit=6),
        "whatsapp": _whatsapp(blob),
        "social": _social(blob),
        "assets": _asset_urls(blob),
        "addresses": _address_lines(blob),
        "sources": _unique(sources or extract_urls(blob), limit=16),
        "gaps": _gaps(blob),
    }


def format_grounded_constraints_block(
    report_text: str,
    sources: Optional[list[str]] = None,
    *,
    max_chars: int = 6000,
) -> str:
    """Build a MUST-FOLLOW block for vibe architect/coder after research."""
    facts = extract_research_facts(report_text, sources)
    lines: list[str] = [
        "=== GROUNDED FACTS FROM PRIOR RESEARCH (MUST FOLLOW IN CODE) ===",
        "These strings appeared in verified research. Treat them as ground truth.",
        "",
        "HARD RULES:",
        "1. Do NOT invent emails, phone numbers, WhatsApp numbers, street addresses,",
        "   map embeds/coordinates, doctor names/bios/gender/years of experience,",
        "   review scores, or brand colors/fonts not listed below.",
        "2. If a fact is missing or listed under GAPS, omit it or show a neutral",
        "   placeholder label — never fake a realistic value.",
        "3. Brand colors: use ONLY hex values listed below for primary UI chrome.",
        "   Do not substitute a generic 'medical green' or other palette.",
        "4. Logo/images: prefer absolute URLs from ASSETS below. Do not invent binary",
        "   image files with fake extensions (no ASCII-as-.png). If no asset URL,",
        "   use an inline SVG monogram with grounded brand colors.",
        "5. Maps: only embed a third-party map if a maps URL appears in research.",
        "   Otherwise show the verified address text and optionally a Google Maps",
        "   search link built from that exact address string (no invented lat/lng).",
        "6. Contact CTAs: if WhatsApp links/digits appear, use them (wa.me).",
        "   If Instagram/Facebook URLs appear, link them. Do not invent social handles.",
        "7. Language: match the subject's language (if research is mostly Spanish,",
        "   UI copy should be Spanish unless the user asked for another language).",
        "8. Services/copy: prefer wording already in the research mission/services;",
        "   do not add unmentioned specialties.",
        "9. Static sites: prefer zero backend; tests should be simple path/content",
        "   checks (pytest reading files), not Selenium/Chrome unless requested.",
        "10. Copyright year: use a neutral current-era year or omit; do not invent founding years.",
        "",
    ]

    def _section(title: str, items: list[str]) -> None:
        if not items:
            lines.append(f"{title}: (none found in research — do not invent)")
            return
        lines.append(f"{title}:")
        for it in items:
            lines.append(f"  - {it}")
        lines.append("")

    _section("BRAND COLORS (hex)", facts["colors"])
    _section("WHATSAPP / MESSAGING", facts["whatsapp"])
    _section("PHONES", facts["phones"])
    _section("EMAILS", facts["emails"])
    _section("SOCIAL PROFILES", facts["social"])
    _section("ASSETS (logo/images)", facts["assets"])
    _section("ADDRESS / LOCATION LINES", facts["addresses"])
    _section("SOURCE URLS", facts["sources"])
    _section("EXPLICIT GAPS", facts["gaps"])

    lines.append("=== END GROUNDED FACTS ===")
    block = "\n".join(lines)
    if len(block) > max_chars:
        return block[: max_chars - 1] + "…"
    return block
