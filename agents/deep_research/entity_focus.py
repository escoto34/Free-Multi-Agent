"""
Entity anchoring helpers for System B (Deep Research).

Keeps research tied to the named subject so search and synthesis do not merge
unrelated entities with similar names. Domain-agnostic (any topic / industry).
"""

from __future__ import annotations

import re

# "Foo or Bar", "Foo / Bar", "Foo aka Bar"
_VARIANT_SPLIT = re.compile(
    r"\s+(?:o|or|/|aka|también\s+conocid[oa]\s+como|also\s+known\s+as)\s+",
    re.IGNORECASE,
)
# Place phrases after common location prepositions (no fixed city list)
_LOC_AFTER_PREP = re.compile(
    r"\b(?:in|en|at|near|from|de|del|desde|located\s+in|based\s+in|"
    r"ubicad[oa]\s+en|situad[oa]\s+en)\s+"
    r"([A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9][\wÁÉÍÓÚÜÑáéíóúüñ\s.\-]{1,50})",
    re.IGNORECASE,
)
# "about Foo", "sobre Bar", "information about X"
# Word boundaries required — bare "on" must not match inside "information".
_ABOUT_NAME = re.compile(
    r"\b(?:about|sobre|on)\b\s+([A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9][\w\-.]{1,40})"
    r"(?:\s+(?:o|or|/|aka)\s+([A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9][\w\-.]{1,40}))?",
    re.IGNORECASE,
)
_AKA_PAREN = re.compile(
    r"\((?:also\s+known\s+as|aka|o|or)\s*([^)]{2,60})\)",
    re.IGNORECASE,
)
_FILLER_PREFIX = re.compile(
    r"^(?:research|investiga(?:r)?|busca(?:r)?|find|look\s+up|"
    r"tell\s+me\s+about|información\s+sobre|todo\s+sobre|"
    r"comprehensive\s+information\s+about|information\s+about|"
    r"gather\s+(?:comprehensive\s+)?(?:factual\s+)?information\s+about|"
    r"use\s+the\s+deep-research\s+pipeline\s+to\s+gather.*?about)\s+",
    re.IGNORECASE | re.DOTALL,
)
# Generic fillers that should not become the "entity name"
_STOP_NAMES = frozenset(
    {
        "research",
        "information",
        "comprehensive",
        "company",
        "empresa",
        "business",
        "negocio",
        "organization",
        "organización",
        "the",
        "and",
        "with",
        "from",
        "pipeline",
        "factual",
        "gather",
        "located",
        "about",
        "sobre",
        "todo",
        "misma",
        "same",
        "official",
        "website",
        "pagina",
        "página",
        "web",
        "reviews",
        "news",
    }
)


def extract_location_phrases(query: str, *, max_phrases: int = 3) -> list[str]:
    """Location-like phrases taken from the query text (no fixed place catalog)."""
    q = (query or "").strip()
    if not q:
        return []

    out: list[str] = []
    seen: set[str] = set()

    def _push(raw: str) -> None:
        chunk = " ".join((raw or "").split()).strip(" \t,.;:-")
        if not chunk or len(chunk) < 2:
            return
        # Cap length; keep first ~5 tokens of a place phrase
        toks = chunk.split()
        if len(toks) > 5:
            chunk = " ".join(toks[:5])
        key = chunk.casefold()
        if key in seen or key in _STOP_NAMES:
            return
        seen.add(key)
        out.append(chunk)

    for m in _LOC_AFTER_PREP.finditer(q):
        _push(m.group(1))

    # Comma-separated place tail: "…, City, Country"
    parts = [p.strip() for p in q.split(",") if p.strip()]
    if len(parts) >= 2:
        for p in parts[1:]:
            # Skip pure instructions / long clauses
            if len(p) > 60 or len(p.split()) > 6:
                continue
            if re.search(
                r"\b(investiga|research|website|pagina|página|brand|marca|logo)\b",
                p,
                re.I,
            ):
                continue
            _push(p)

    return out[:max_phrases]


def extract_name_variants(query: str) -> list[str]:
    """Pull likely subject-name variants from a free-text research topic."""
    q = (query or "").strip()
    if not q:
        return []

    variants: list[str] = []

    # Parenthetical aka: (also known as Foo)
    for m in _AKA_PAREN.finditer(q):
        chunk = m.group(1).strip(" \t\"'")
        for part in _VARIANT_SPLIT.split(chunk):
            p = part.strip(" \t\"'")
            if 2 <= len(p) <= 60:
                variants.append(p)

    # about X or Y
    for m in _ABOUT_NAME.finditer(q):
        if m.group(1):
            variants.append(m.group(1).strip())
        if m.group(2):
            variants.append(m.group(2).strip())

    # Prefer the first clause before commas for the subject block.
    head = re.split(r"[,;(]", q, maxsplit=1)[0].strip()
    head = _FILLER_PREFIX.sub("", head).strip()
    head = re.sub(
        r"^(?:comprehensive|factual|detailed)?\s*(?:information|info)?\s*"
        r"(?:about|on|sobre)?\s*",
        "",
        head,
        flags=re.IGNORECASE,
    ).strip()

    parts = [p.strip(" \t\"'") for p in _VARIANT_SPLIT.split(head) if p.strip()]
    for p in parts:
        p = re.sub(
            r"\s+(?:la|el|the|misma\s+empresa|same\s+company|"
            r"a\s+\w+.*|located\s+in.*|ubicad[oa]\s+en.*).*$",
            "",
            p,
            flags=re.IGNORECASE,
        ).strip()
        # If still a long sentence, take first 1–3 tokens that look like a name
        if len(p) > 40 or (" " in p and p.lower().split()[0] in _STOP_NAMES):
            tokens = p.split()
            name_toks: list[str] = []
            for t in tokens[:4]:
                tl = t.lower().strip(".,")
                if tl in _STOP_NAMES:
                    if name_toks:
                        break
                    continue
                name_toks.append(t.strip(".,\"'"))
            p = " ".join(name_toks)
        if 2 <= len(p) <= 80 and p.lower() not in _STOP_NAMES:
            variants.append(p)

    # Capitalized / brand-like tokens (proper names)
    for tok in re.findall(
        r"\b([A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]{2,})\b", q
    ):
        if tok.lower() in _STOP_NAMES:
            continue
        variants.append(tok)

    # Deduplicate case-insensitively, preserve order
    seen: set[str] = set()
    out: list[str] = []
    for v in variants:
        v = v.strip(" \t\"'.,")
        if not v or len(v) < 2:
            continue
        key = v.casefold()
        if key in seen or key in _STOP_NAMES:
            continue
        seen.add(key)
        out.append(v)
    return out[:6]


def extract_entity_anchors(query: str, *, max_anchors: int = 6) -> list[str]:
    """Build high-precision search strings anchored on the research subject."""
    q = (query or "").strip()
    if not q:
        return []

    anchors: list[str] = []
    variants = extract_name_variants(q)
    locs = extract_location_phrases(q)
    loc = " ".join(locs[:2])

    # User-named websites first (site: and bare domain)
    try:
        from agents.deep_research.source_fetch import extract_user_domains, extract_user_urls

        for domain in extract_user_domains(q):
            anchors.append(domain)
            anchors.append(f"site:{domain}")
        for url in extract_user_urls(q, max_urls=3):
            anchors.append(url)
    except Exception:
        pass

    for name in variants:
        anchors.append(name)
        if loc:
            anchors.append(f"{name} {loc}")
        anchors.append(f'"{name}"')

    if variants:
        main = variants[0]
        # Generic open-web facets (any industry)
        anchors.append(f"{main} official website")
        anchors.append(f"{main} reviews OR ratings")
        anchors.append(f"{main} news OR press")
        if loc:
            anchors.append(f"{main} {loc} contact")
        # Brand / visual only when the user asked for it
        if re.search(
            r"\b(marca|brand|logo|identidad|visual\s+identity|"
            r"imagen\s+de\s+marca|branding)\b",
            q,
            re.I,
        ):
            anchors.append(f"{main} logo brand identity")

    if not anchors:
        primary = " ".join(q.split())
        if len(primary) > 140:
            primary = primary[:140].rsplit(" ", 1)[0]
        anchors.append(primary)

    seen: set[str] = set()
    out: list[str] = []
    for a in anchors:
        a = " ".join(a.split()).strip()
        if not a or len(a) < 3:
            continue
        key = a.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(a[:150])
        if len(out) >= max_anchors:
            break
    return out


def merge_search_terms(
    anchors: list[str],
    llm_terms: list[str],
    *,
    max_terms: int = 8,
) -> list[str]:
    """Prefer entity anchors, then LLM keywords (deduped)."""
    merged: list[str] = []
    seen: set[str] = set()
    bare_generics = {
        "reviews",
        "website",
        "news",
        "contact",
        "company",
        "business",
        "empresa",
        "information",
        "research",
    }
    for term in list(anchors) + list(llm_terms or []):
        t = " ".join((term or "").split()).strip()
        if not t:
            continue
        key = t.casefold()
        if key in seen:
            continue
        if key in bare_generics:
            continue
        seen.add(key)
        merged.append(t[:150])
        if len(merged) >= max_terms:
            break
    return merged


def entity_focus_block(query: str) -> str:
    """Instruction block injected into search / grounding / synthesis prompts."""
    variants = extract_name_variants(query)
    names = ", ".join(f'"{v}"' for v in variants) if variants else f'"{query[:80]}"'
    locs = extract_location_phrases(query)
    loc_line = (
        f"- Location hints from the topic (use only if they appear in the query): "
        f'{", ".join(repr(x) for x in locs)}\n'
        if locs
        else ""
    )
    official_lines = ""
    try:
        from agents.deep_research.source_fetch import extract_user_domains, extract_user_urls

        urls = extract_user_urls(query, max_urls=5)
        domains = extract_user_domains(query)
        if urls or domains:
            official_lines = (
                "- USER-PROVIDED OFFICIAL WEB PRESENCE (highest trust when present):\n"
                + "".join(f"  · {u}\n" for u in urls)
                + (
                    "  Domains: " + ", ".join(domains) + "\n"
                    if domains
                    else ""
                )
                + "  Treat these as primary official sources (PRIMARY SOURCES block "
                "+ site: searches). Do not ignore them.\n"
                "  They are NOT the only evidence: also use the LIVE WEB SEARCH DUMP "
                "for third-party / open-web findings about the same subject.\n"
                "  Do NOT invent archive snapshots, contact data, brand details, or "
                "citation URLs unless they appear verbatim in PRIMARY SOURCES or the "
                "live search dump.\n"
                "  If a primary fetch failed, say so — never fabricate page content.\n"
            )
    except Exception:
        official_lines = ""

    return (
        "ENTITY FOCUS (strict):\n"
        f"- Primary subject variants: {names}\n"
        f"{loc_line}"
        f"{official_lines}"
        "- Only report facts that clearly refer to THIS subject (same organization, "
        "person, product, or place the user named).\n"
        "- Do NOT merge unrelated entities that merely share a sector, city, or "
        "similar name.\n"
        "- If a social profile, website, phone, or address is not clearly tied to the "
        "named subject, put it under 'Unverified / possibly unrelated'.\n"
        "- Contact data (phone, email, messaging): only if the exact string appears in "
        "sources. Otherwise write 'not found in verified sources'.\n"
        "- Citation sources[] must be URLs that appear in the documents; never invent "
        "links.\n"
        "- When sources conflict or only look similar, say so explicitly.\n"
        "- Use BOTH official-site content (when available) and third-party web findings.\n"
    )
