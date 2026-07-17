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


def extract_name_variants(query: str) -> list[str]:
    """Pull likely official-name variants from a free-text research topic."""
    q = (query or "").strip()
    if not q:
        return []

    variants: list[str] = []
    # Prefer the first clause before commas/parentheses for the brand block.
    head = re.split(r"[,;(]", q, maxsplit=1)[0].strip()
    # Drop leading verbs like "Research …", "Investiga …"
    head = re.sub(
        r"^(?:research|investiga(?:r)?|busca(?:r)?|find|look\s+up|"
        r"tell\s+me\s+about|información\s+sobre|todo\s+sobre)\s+",
        "",
        head,
        flags=re.IGNORECASE,
    ).strip()

    parts = [p.strip(" \t\"'") for p in _VARIANT_SPLIT.split(head) if p.strip()]
    for p in parts:
        # Keep short proper-name chunks (drop trailing filler words)
        p = re.sub(
            r"\s+(?:la|el|the|misma\s+empresa|same\s+company).*$",
            "",
            p,
            flags=re.IGNORECASE,
        ).strip()
        if 2 <= len(p) <= 80:
            variants.append(p)

    # Deduplicate case-insensitively, preserve order
    seen: set[str] = set()
    out: list[str] = []
    for v in variants:
        key = v.casefold()
        if key not in seen:
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

    # Full topic (truncated) as primary live search — never drop the user intent.
    primary = " ".join(q.split())
    if len(primary) > 140:
        primary = primary[:140].rsplit(" ", 1)[0]
    if primary:
        anchors.append(primary)

    # Location-ish tail from the original query
    loc_bits = _LOCATION_HINTS.findall(q)
    loc = " ".join(dict.fromkeys(b.lower() for b in loc_bits))  # unique order

    for name in variants:
        anchors.append(name)
        if loc:
            anchors.append(f"{name} {loc}")
        anchors.append(f'"{name}"')

    # Common official-site / review patterns for the first name only
    if variants:
        main = variants[0]
        anchors.append(f"{main} site oficial")
        anchors.append(f"{main} Google reviews")

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
        # Skip ultra-generic terms that cause entity bleed
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
