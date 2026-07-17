"""
Entity anchoring helpers for System B (Deep Research).

Keeps company/place research tied to the named subject so search and
synthesis do not merge unrelated businesses with similar names.
"""

from __future__ import annotations

import re

# "Creddental or Credental", "Foo / Bar", "Foo aka Bar"
_VARIANT_SPLIT = re.compile(
    r"\s+(?:o|or|/|aka|también\s+conocid[oa]\s+como|also\s+known\s+as)\s+",
    re.IGNORECASE,
)
_LOCATION_HINTS = re.compile(
    r"\b(honduras|san\s+pedro\s+sula|tegucigalpa|cl[ií]nica|dental|"
    r"hospital|empresa|company|clinic)\b",
    re.IGNORECASE,
)
# "about Creddental", "sobre Credental", "information about X"
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
_STOP_NAMES = frozenset(
    {
        "research",
        "information",
        "comprehensive",
        "clinic",
        "dental",
        "clínica",
        "clinica",
        "company",
        "empresa",
        "honduras",
        "san",
        "pedro",
        "sula",
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
    }
)


def extract_name_variants(query: str) -> list[str]:
    """Pull likely official-name variants from a free-text research topic."""
    q = (query or "").strip()
    if not q:
        return []

    variants: list[str] = []

    # Parenthetical aka: (also known as Credental)
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

    # Prefer the first clause before commas for the brand block.
    head = re.split(r"[,;(]", q, maxsplit=1)[0].strip()
    head = _FILLER_PREFIX.sub("", head).strip()
    # Drop leading fluff words left over
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
            r"a\s+dental.*|dental\s+clinic.*).*$",
            "",
            p,
            flags=re.IGNORECASE,
        ).strip()
        # If still a long sentence, take first 1–3 tokens that look like a name
        if len(p) > 40 or " " in p and p.lower().split()[0] in _STOP_NAMES:
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

    # Brand-like tokens in the full query (Creddental, CREDental, CredentalHN)
    for tok in re.findall(
        r"\b([A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]{3,})\b", q
    ):
        if tok.lower() in _STOP_NAMES:
            continue
        variants.append(tok)

    # Deduplicate case-insensitively, preserve order; drop pure stopwords
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
    loc_bits = _LOCATION_HINTS.findall(q)
    loc = " ".join(dict.fromkeys(b.lower() for b in loc_bits))

    # Prefer short entity+location anchors over the whole planner essay
    for name in variants:
        anchors.append(name)
        if loc:
            anchors.append(f"{name} {loc}")
        anchors.append(f'"{name}"')

    if variants:
        main = variants[0]
        anchors.append(f"{main} official website")
        anchors.append(f"{main} Google reviews")
        anchors.append(f"{main} Facebook")

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
    for term in list(anchors) + list(llm_terms or []):
        t = " ".join((term or "").split()).strip()
        if not t:
            continue
        key = t.casefold()
        if key in seen:
            continue
        if key in {
            "dental",
            "clinic",
            "clínica",
            "clinica",
            "dentist",
            "honduras",
            "reviews",
            "website",
        }:
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
    return (
        "ENTITY FOCUS (strict):\n"
        f"- Primary subject variants: {names}\n"
        "- Only report facts that clearly refer to THIS subject (same brand/legal "
        "entity / same physical business the user named).\n"
        "- Do NOT merge unrelated businesses, clinics, hospitals, or social accounts "
        "just because they are dental, in the same city, or have a similar name.\n"
        "- If a social handle, website, phone, or address is not clearly tied to the "
        "named entity (e.g. Instagram of another clinic), put it under "
        "'Unverified / possibly unrelated' and do not present it as fact.\n"
        "- When sources conflict or only look similar, say so explicitly.\n"
        "- Prefer official domain, Google Business, government registries, and pages "
        "that print the exact name + location.\n"
    )
