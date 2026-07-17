"""
Research typology for System B (Deep Research).

Classifies a free-text topic by classic research dimensions so search,
grounding, and synthesis adapt without hardcoding any industry or entity.

Dimensions (standard academic/professional framing):
  1. Purpose:        basic (pure) | applied
  2. Depth:          exploratory | descriptive | explanatory
  3. Data approach:  quantitative | qualitative | mixed
  4. Design:         experimental | non_experimental

Selection of the right profile shapes what evidence to seek and how to
structure the report (theory expansion vs practical problem-solving;
describe vs explain; numbers vs meanings; intervene vs observe).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Literal, Optional

Purpose = Literal["basic", "applied"]
Depth = Literal["exploratory", "descriptive", "explanatory"]
DataApproach = Literal["quantitative", "qualitative", "mixed"]
Design = Literal["experimental", "non_experimental"]


@dataclass(frozen=True)
class ResearchProfile:
    """Resolved research profile for one pipeline run."""

    purpose: Purpose = "applied"
    depth: Depth = "descriptive"
    data_approach: DataApproach = "mixed"
    design: Design = "non_experimental"
    rationale: str = ""

    def as_dict(self) -> dict[str, str]:
        return {k: str(v) for k, v in asdict(self).items()}

    def label(self) -> str:
        return (
            f"{self.purpose} · {self.depth} · {self.data_approach} · {self.design}"
        )


# ---------------------------------------------------------------------------
# Keyword heuristics (language-agnostic enough for ES/EN prompts)
# ---------------------------------------------------------------------------

_BASIC = re.compile(
    r"\b(teor[ií]a|teoric[oa]|fundamentos?|estado\s+del\s+arte|literature\s+review|"
    r"marco\s+conceptual|epistemolog|sin\s+aplicaci[oó]n\s+pr[aá]ctica|"
    r"basic\s+research|pure\s+research|theoretical)\b",
    re.I,
)
_APPLIED = re.compile(
    r"\b(aplicad[oa]|resolver|soluci[oó]n|problema\s+pr[aá]ctic|"
    r"implement|mejora|optimiz|producto|servicio|cliente|negocio|marca|"
    r"brand|rediseñ|redesign|pr[aá]ctic[oa]|applied\s+research|"
    r"how\s+to|c[oó]mo\s+(hacer|mejorar|implementar))\b",
    re.I,
)
_EXPLORATORY = re.compile(
    r"\b(explorator|poco\s+estudiad|primer\s+acercamiento|mapear|"
    r"qu[eé]\s+se\s+sabe|scoping|hypothesis\s+generat|formular\s+hip[oó]tesis|"
    r"overview|panorama|estado\s+de\s+la\s+cuesti[oó]n)\b",
    re.I,
)
_DESCRIPTIVE = re.compile(
    r"\b(descriptiv|caracter[ií]sticas?|perfil|inventario|cat[aá]logo|"
    r"qui[eé]n|qu[eé]\s+es|d[oó]nde|cu[aá]ndo|c[oó]mo\s+est[aá]|"
    r"describe|detail|mapa\s+de|identidad|presencia|contacto|"
    r"without\s+explaining\s+why|sin\s+buscar\s+el\s+por\s*qu[eé])\b",
    re.I,
)
_EXPLANATORY = re.compile(
    r"\b(explicativ|por\s*qu[eé]|causa|consecuencia|efecto|impacto|"
    r"relaci[oó]n\s+entre|determinantes?|factores\s+que|"
    r"why\s+|causal|correlation|explica\s+c[oó]mo)\b",
    re.I,
)
_QUANT = re.compile(
    r"\b(cuantitativ|estad[ií]stic|encuesta|survey|porcentaje|muestra|"
    r"n\s*=|dataset|m[eé]trica|kpi|ranking|n[uú]mero|tasa|promedio|"
    r"quantitative|regression|correlaci[oó]n\s+num[eé]ric)\b",
    re.I,
)
_QUAL = re.compile(
    r"\b(cualitativ|entrevista|focus\s+group|grupo\s+focal|discurso|"
    r"percepci[oó]n|experiencias?|narrativa|observaci[oó]n\s+particip|"
    r"sentimientos?|emociones?|qualitative|thematic\s+analysis)\b",
    re.I,
)
_EXPERIMENTAL = re.compile(
    r"\b(experiment|A\/B|ab\s+test|grupo\s+de\s+control|variable\s+independiente|"
    r"manipulaci[oó]n\s+de\s+variables|ensayo\s+controlad|RCT|"
    r"controlled\s+trial|randomi[sz]ed)\b",
    re.I,
)


def classify_research(query: str) -> ResearchProfile:
    """Heuristic classification from free text (no LLM, no domain hardcoding)."""
    q = query or ""

    # Purpose
    basic_hit = bool(_BASIC.search(q))
    applied_hit = bool(_APPLIED.search(q))
    # Explicit "no practical aim" / "basic research" wins over stray "práctica" hits
    pure_basic = bool(
        re.search(
            r"\b(investigaci[oó]n\s+b[aá]sica|basic\s+research|pure\s+research|"
            r"sin\s+(un\s+)?(objetivo\s+)?aplicaci[oó]n\s+pr[aá]ctic|"
            r"without\s+(an?\s+)?immediate\s+practical|"
            r"no\s+immediate\s+practical)\b",
            q,
            re.I,
        )
    )
    if pure_basic or (basic_hit and not applied_hit):
        purpose: Purpose = "basic"
    elif applied_hit and not basic_hit:
        purpose = "applied"
    elif basic_hit and applied_hit:
        # Practical framing wins when both appear (unless pure_basic above)
        purpose = "applied"
    else:
        # Default for web deep-research: practical / decision-support
        purpose = "applied"

    # Depth
    exp_hit = bool(_EXPLORATORY.search(q))
    des_hit = bool(_DESCRIPTIVE.search(q))
    expl_hit = bool(_EXPLANATORY.search(q))
    if expl_hit and not des_hit:
        depth: Depth = "explanatory"
    elif exp_hit and not des_hit and not expl_hit:
        depth = "exploratory"
    elif des_hit:
        depth = "descriptive"
    elif expl_hit:
        depth = "explanatory"
    elif exp_hit:
        depth = "exploratory"
    else:
        # Entity / "tell me everything" style topics → descriptive map
        depth = "descriptive"

    # Data approach
    quant = bool(_QUANT.search(q))
    qual = bool(_QUAL.search(q))
    if quant and qual:
        data: DataApproach = "mixed"
    elif quant:
        data = "quantitative"
    elif qual:
        data = "qualitative"
    else:
        data = "mixed"

    # Design
    design: Design = (
        "experimental" if _EXPERIMENTAL.search(q) else "non_experimental"
    )

    bits = [
        f"purpose={purpose}",
        f"depth={depth}",
        f"data={data}",
        f"design={design}",
    ]
    return ResearchProfile(
        purpose=purpose,
        depth=depth,
        data_approach=data,
        design=design,
        rationale="Heuristic typology from topic wording: " + ", ".join(bits),
    )


def profile_from_mapping(data: Optional[dict[str, Any]]) -> ResearchProfile:
    """Build a profile from compressor JSON fields (with safe defaults)."""
    base = classify_research("")  # defaults
    if not data:
        return base

    purpose = str(data.get("purpose") or base.purpose).lower().strip()
    depth = str(data.get("depth") or base.depth).lower().strip()
    data_approach = str(
        data.get("data_approach") or data.get("data") or base.data_approach
    ).lower().strip()
    design = str(data.get("design") or base.design).lower().strip()

    # Normalize aliases
    if purpose in ("pura", "pure", "básica", "basica", "theoretical"):
        purpose = "basic"
    if purpose in ("aplicada", "practice", "practical"):
        purpose = "applied"
    if depth in ("exploratoria",):
        depth = "exploratory"
    if depth in ("descriptiva",):
        depth = "descriptive"
    if depth in ("explicativa", "causal"):
        depth = "explanatory"
    if data_approach in ("cuantitativa", "quant", "numeric"):
        data_approach = "quantitative"
    if data_approach in ("cualitativa", "qual"):
        data_approach = "qualitative"
    if data_approach in ("mixta", "both"):
        data_approach = "mixed"
    if design in ("no_experimental", "no experimental", "observational", "no experimental"):
        design = "non_experimental"
    if design in ("experimental", "experimento"):
        design = "experimental"

    valid_p: set[str] = {"basic", "applied"}
    valid_d: set[str] = {"exploratory", "descriptive", "explanatory"}
    valid_a: set[str] = {"quantitative", "qualitative", "mixed"}
    valid_g: set[str] = {"experimental", "non_experimental"}

    return ResearchProfile(
        purpose=purpose if purpose in valid_p else base.purpose,  # type: ignore[arg-type]
        depth=depth if depth in valid_d else base.depth,  # type: ignore[arg-type]
        data_approach=data_approach if data_approach in valid_a else base.data_approach,  # type: ignore[arg-type]
        design=design if design in valid_g else base.design,  # type: ignore[arg-type]
        rationale=str(data.get("profile_rationale") or data.get("rationale") or "")[:500],
    )


def merge_profiles(heuristic: ResearchProfile, llm: ResearchProfile) -> ResearchProfile:
    """Prefer LLM labels when valid; keep heuristic rationale as backup."""
    return ResearchProfile(
        purpose=llm.purpose,
        depth=llm.depth,
        data_approach=llm.data_approach,
        design=llm.design,
        rationale=(llm.rationale or heuristic.rationale)[:500],
    )


def research_profile_block(profile: ResearchProfile) -> str:
    """Instruction block for search / grounding / synthesis agents."""
    purpose_txt = {
        "basic": (
            "BASIC (pure): expand theoretical / conceptual knowledge; "
            "prioritize definitions, frameworks, prior studies, state of the art. "
            "Do not force a product/business solution unless sources support it."
        ),
        "applied": (
            "APPLIED: use knowledge to support a practical decision or problem. "
            "Prioritize actionable facts, constraints, stakeholders, and usable outputs."
        ),
    }[profile.purpose]

    depth_txt = {
        "exploratory": (
            "EXPLORATORY: map what exists, open questions, and candidate hypotheses. "
            "Do not over-claim causes. Emphasize gaps and diversity of sources."
        ),
        "descriptive": (
            "DESCRIPTIVE: detail characteristics, configuration, presence, and facts "
            "as they appear. Answer who/what/where/when/how-it-is — not forced 'why'."
        ),
        "explanatory": (
            "EXPLANATORY: seek evidence of relationships, mechanisms, causes and "
            "consequences. Separate correlation from proven causation; report uncertainty."
        ),
    }[profile.depth]

    data_txt = {
        "quantitative": (
            "QUANTITATIVE emphasis: prefer measurable figures, rates, sample sizes, "
            "structured surveys/statistics when present. Quote numbers only if in sources."
        ),
        "qualitative": (
            "QUALITATIVE emphasis: meanings, discourses, practices, testimonials, "
            "observed behaviors — only as evidenced in sources (no fabricated interviews)."
        ),
        "mixed": (
            "MIXED: combine hard facts/figures when available with qualitative context "
            "(reputation language, narratives) — always source-grounded."
        ),
    }[profile.data_approach]

    design_txt = {
        "experimental": (
            "EXPERIMENTAL design framing: look for controlled comparisons, interventions, "
            "A/B or trial results if any. Do not invent experimental results."
        ),
        "non_experimental": (
            "NON-EXPERIMENTAL design: observe and synthesize phenomena as they appear "
            "in natural/web sources; do not claim you manipulated variables."
        ),
    }[profile.design]

    return (
        "RESEARCH PROFILE (adapt evidence gathering and report structure):\n"
        f"- Active profile: {profile.label()}\n"
        f"- Purpose — {purpose_txt}\n"
        f"- Depth — {depth_txt}\n"
        f"- Data approach — {data_txt}\n"
        f"- Design — {design_txt}\n"
        "- Always stay entity-faithful and source-grounded; typology guides focus, "
        "it does not authorize invention.\n"
    )


def search_facet_hints(profile: ResearchProfile, subject: str = "") -> list[str]:
    """Extra search facet templates from typology (subject-agnostic fillers)."""
    s = (subject or "").strip()
    # Use placeholder-free facets when subject empty; caller prefixes entity
    base = s if s else ""

    def f(suffix: str) -> str:
        return f"{base} {suffix}".strip() if base else suffix

    facets: list[str] = []

    if profile.purpose == "basic":
        facets.extend(
            [
                f("theory OR framework OR definition"),
                f("literature OR review OR state of the art"),
                f("academic OR paper OR study"),
            ]
        )
    else:
        facets.extend(
            [
                f("case study OR practical OR application"),
                f("guide OR how to OR best practices"),
                f("problem OR solution OR implementation"),
            ]
        )

    if profile.depth == "exploratory":
        facets.extend(
            [
                f("overview OR landscape OR mapping"),
                f("open questions OR gaps OR unknown"),
            ]
        )
    elif profile.depth == "descriptive":
        facets.extend(
            [
                f("profile OR characteristics OR description"),
                f("official OR contact OR location OR presence"),
            ]
        )
    else:  # explanatory
        facets.extend(
            [
                f("causes OR drivers OR factors"),
                f("impact OR effect OR consequences"),
                f("why OR analysis OR relationship"),
            ]
        )

    if profile.data_approach == "quantitative":
        facets.extend(
            [
                f("statistics OR data OR survey OR percent"),
                f("market size OR metrics OR ranking"),
            ]
        )
    elif profile.data_approach == "qualitative":
        facets.extend(
            [
                f("interview OR testimonial OR experience"),
                f("perception OR narrative OR discourse"),
            ]
        )
    else:
        facets.extend(
            [
                f("reviews OR ratings OR reputation"),
                f("report OR analysis"),
            ]
        )

    if profile.design == "experimental":
        facets.extend(
            [
                f("experiment OR A/B test OR controlled trial"),
                f("treatment OR control group OR RCT"),
            ]
        )
    else:
        facets.extend(
            [
                f("observation OR field OR real world"),
                f("news OR directory OR public records"),
            ]
        )

    return facets


def report_outline_hints(profile: ResearchProfile) -> str:
    """Suggested Markdown section emphasis for grounding/synthesis."""
    sections = [
        "1. Research framing (purpose / depth / data / design used)",
        "2. Subject identity & scope",
    ]
    if profile.purpose == "basic":
        sections.append("3. Conceptual / theoretical background")
    else:
        sections.append("3. Practical context & decision needs")

    if profile.depth == "exploratory":
        sections.append("4. Landscape map & open questions")
    elif profile.depth == "descriptive":
        sections.append("4. Descriptive profile (attributes, presence, configuration)")
    else:
        sections.append("4. Explanatory analysis (links, mechanisms, limits of evidence)")

    if profile.data_approach in ("quantitative", "mixed"):
        sections.append("5. Quantitative signals (only if present in sources)")
    if profile.data_approach in ("qualitative", "mixed"):
        sections.append("6. Qualitative signals (discourses, practices — sourced only)")

    if profile.design == "experimental":
        sections.append("7. Experimental / interventional evidence (if any)")
    else:
        sections.append("7. Observational / non-experimental evidence")

    sections.extend(
        [
            "8. Official sources vs third-party sources",
            "9. Unrelated / excluded hits",
            "10. Gaps, limits, and next research steps",
        ]
    )
    return "Suggested report emphasis:\n" + "\n".join(sections) + "\n"
