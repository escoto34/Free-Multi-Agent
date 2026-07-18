"""
Task difficulty scoring (0–100) aligned with systems.md / model_benchmarks.yaml.

Produces structured :class:`DifficultyAssessment` values — never free-form
text — so the model selector can decide primary vs fallback deterministically.

Two entry points:

* ``score_task_difficulty`` — pure heuristic (no LLM, free, test-friendly).
* ``plan_pipeline_difficulties`` — planner-side multi-role assessments
  before delegation (System A architect / System B compressor).
"""

from __future__ import annotations

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

AreaName = Literal["code", "reason", "ground", "synth", "safety"]
ALL_AREAS: tuple[AreaName, ...] = ("code", "reason", "ground", "synth", "safety")

PipelineKind = Literal["vibe_coding", "deep_research"]


class DifficultyAssessment(BaseModel):
    """Structured difficulty scores for one subtask / role.

    Area fields mirror the systems.md rubric (0–100). Extra dimensions
    capture planner-style estimates (logic, error handling, context size).
    """

    code: int = Field(default=0, ge=0, le=100)
    reason: int = Field(default=0, ge=0, le=100)
    ground: int = Field(default=0, ge=0, le=100)
    synth: int = Field(default=0, ge=0, le=100)
    safety: int = Field(default=0, ge=0, le=100)

    logic_complexity: int = Field(
        default=0,
        ge=0,
        le=100,
        description="How hard the core logic/algorithms are.",
    )
    error_handling_complexity: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Edge cases, retries, validation, failure modes.",
    )
    estimated_context_tokens: int = Field(
        default=2000,
        ge=0,
        description="Rough context the worker model will need.",
    )
    overall: int = Field(default=0, ge=0, le=100)
    rationale: str = Field(default="", description="Short machine-readable why.")
    subtask: str = Field(default="", description="Label e.g. coder, grounding.")
    role_path: str = Field(
        default="",
        description="Dotted role path e.g. vibe_coding.coder",
    )

    @field_validator(
        "code",
        "reason",
        "ground",
        "synth",
        "safety",
        "logic_complexity",
        "error_handling_complexity",
        "overall",
        mode="before",
    )
    @classmethod
    def _clamp_int(cls, v: Any) -> int:
        try:
            n = int(v)
        except (TypeError, ValueError):
            n = 0
        return max(0, min(100, n))

    def area_score(self, area: str) -> int:
        return int(getattr(self, area, 0) or 0)

    def relevant_max(self, areas: list[str]) -> int:
        if not areas:
            return self.overall
        return max(self.area_score(a) for a in areas)


# ---------------------------------------------------------------------------
# Heuristic keyword banks (language-agnostic-ish + EN/ES)
# ---------------------------------------------------------------------------

_CODE_HARD = re.compile(
    r"\b("
    r"concurrency|race\s*condition|deadlock|distributed|microservice|"
    r"kubernetes|refactor\s+entire|multi[- ]?file|cryptograph|oauth|jwt|"
    r"performance|optimize|lock[- ]free|async\s+pipeline|compiler|"
    r"type\s*system|parser|interpreter|wasm|gpu|cuda|"
    r"concurrencia|distribuido|cifrado|rendimiento|refactorizar"
    r")\b",
    re.I,
)
_CODE_EASY = re.compile(
    r"\b("
    r"hello\s*world|print\s*\(|todo\s*list|simple\s+function|"
    r"crud\s+basico|hola\s*mundo|funcion\s+simple|lista\s+de\s+tareas"
    r")\b",
    re.I,
)
_REASON_HARD = re.compile(
    r"\b("
    r"prove|theorem|multi[- ]?step\s+plan|architecture\s+trade|"
    r"constraint\s+satisf|formal\s+verif|dependency\s+graph|"
    r"demostr|planificaci[oó]n\s+compleja|arquitectura\s+completa"
    r")\b",
    re.I,
)
_GROUND_HARD = re.compile(
    r"\b("
    r"cite|citation|sources?|ground(ed|ing)?|live\s+search|"
    r"verify\s+url|rag\b|with\s+references|fuentes|citas|"
    r"verificad|b[uú]squeda\s+en\s+vivo"
    r")\b",
    re.I,
)
_SYNTH_HARD = re.compile(
    r"\b("
    r"long\s+report|executive\s+summary|multi[- ]?section|"
    r"whitepaper|s[ií]ntesis\s+extensa|informe\s+largo|memoria"
    r")\b",
    re.I,
)
_SAFETY_HARD = re.compile(
    r"\b("
    r"weapon|exploit|malware|bioweapon|self[- ]harm|child\s+sexual|"
    r"illegal\s+drug|violencia|arma|exploit|autolesi"
    r")\b",
    re.I,
)
_ERROR_HARD = re.compile(
    r"\b("
    r"retry|backoff|circuit\s*breaker|idempoten|transaction|"
    r"rollback|partial\s+failure|timeout|rate\s*limit|"
    r"reintento|transacc|parcial"
    r")\b",
    re.I,
)


def _clip(n: int) -> int:
    return max(0, min(100, int(n)))


def _length_base(text: str) -> int:
    n = len(text or "")
    if n < 80:
        return 15
    if n < 300:
        return 30
    if n < 1200:
        return 45
    if n < 4000:
        return 60
    if n < 12000:
        return 72
    return 85


def score_task_difficulty(
    task_text: str,
    *,
    role_path: str = "",
    subtask: str = "",
) -> DifficultyAssessment:
    """Heuristic 0–100 assessment (no LLM). Suitable for planners and tests."""
    text = task_text or ""
    base = _length_base(text)

    code = base
    reason = base
    ground = max(10, base - 15)
    synth = max(10, base - 10)
    safety = 20
    logic = base
    errors = max(15, base - 10)

    if _CODE_HARD.search(text):
        # Multiple hard signals stack lightly via findall length
        hits = len(_CODE_HARD.findall(text))
        code = _clip(code + 30 + min(15, hits * 5))
        logic = _clip(logic + 35 + min(10, hits * 3))
    if _CODE_EASY.search(text):
        code = _clip(code - 25)
        logic = _clip(logic - 20)
        reason = _clip(reason - 15)
    if _REASON_HARD.search(text):
        reason = _clip(reason + 25)
        logic = _clip(logic + 15)
    if _GROUND_HARD.search(text):
        ground = _clip(ground + 30)
    if _SYNTH_HARD.search(text):
        synth = _clip(synth + 25)
    if _SAFETY_HARD.search(text):
        safety = _clip(safety + 50)
    if _ERROR_HARD.search(text):
        errors = _clip(errors + 25)
        code = _clip(code + 10)

    # Role bias: emphasize the areas that role cares about.
    rp = role_path or subtask
    if "coder" in rp or "debugger" in rp:
        code = _clip(max(code, logic, errors))
        reason = _clip(max(reason, logic - 5))
    elif "architect" in rp or "planner" in rp:
        reason = _clip(max(reason, base + 5))
        synth = _clip(max(synth, base - 5))
    elif "grounding" in rp:
        ground = _clip(max(ground, base + 10))
    elif "synthesizer" in rp:
        synth = _clip(max(synth, base + 10))
    elif "safety" in rp:
        safety = _clip(max(safety, 40))
    elif "web_search" in rp:
        ground = _clip(max(ground, base + 5))
    elif "compressor" in rp:
        reason = _clip(max(reason, base))
        synth = _clip(max(synth, base - 5))

    # Context estimate from length
    est_tokens = max(500, min(200_000, int(len(text) * 0.35) + 1500))
    if est_tokens > 12000:
        code = _clip(code + 10)
        reason = _clip(reason + 8)
        synth = _clip(synth + 8)

    overall = _clip(
        int(
            round(
                0.30 * code
                + 0.25 * reason
                + 0.15 * ground
                + 0.15 * synth
                + 0.05 * safety
                + 0.10 * max(logic, errors)
            )
        )
    )

    bits = []
    if _CODE_HARD.search(text):
        bits.append("hard_code_keywords")
    if _CODE_EASY.search(text):
        bits.append("easy_code_keywords")
    if _GROUND_HARD.search(text):
        bits.append("grounding_keywords")
    if est_tokens > 12000:
        bits.append("large_context")
    bits.append(f"len={len(text)}")

    return DifficultyAssessment(
        code=code,
        reason=reason,
        ground=ground,
        synth=synth,
        safety=safety,
        logic_complexity=logic,
        error_handling_complexity=errors,
        estimated_context_tokens=est_tokens,
        overall=overall,
        rationale=";".join(bits) or "length_baseline",
        subtask=subtask or (role_path.split(".")[-1] if role_path else ""),
        role_path=role_path,
    )


_VIBE_ROLES = (
    "vibe_coding.architect",
    "vibe_coding.coder",
    "vibe_coding.debugger",
)
_RESEARCH_ROLES = (
    "deep_research.safety_filter",
    "deep_research.context_compressor",
    "deep_research.web_search",
    "deep_research.grounding",
    "deep_research.synthesizer",
)


def plan_pipeline_difficulties(
    user_text: str,
    *,
    pipeline: PipelineKind,
) -> dict[str, DifficultyAssessment]:
    """Planner output: one assessment per role before delegation.

    Returns a dict keyed by short role name (``coder``, ``grounding``, …)
    and also by dotted path for convenience.
    """
    roles = _VIBE_ROLES if pipeline == "vibe_coding" else _RESEARCH_ROLES
    out: dict[str, DifficultyAssessment] = {}
    for dotted in roles:
        short = dotted.split(".", 1)[-1]
        a = score_task_difficulty(user_text, role_path=dotted, subtask=short)
        out[short] = a
        out[dotted] = a
    return out


def assessments_to_state_dict(
    plans: dict[str, DifficultyAssessment],
) -> dict[str, dict[str, Any]]:
    """JSON-serializable map for LangGraph state (short keys only)."""
    return {
        k: v.model_dump()
        for k, v in plans.items()
        if "." not in k  # keep short role keys in state
    }


def assessment_from_state(
    raw: Any,
    *,
    role_short: str,
    task_text: str = "",
    role_path: str = "",
) -> DifficultyAssessment:
    """Load assessment from graph state or re-score."""
    if isinstance(raw, DifficultyAssessment):
        return raw
    if isinstance(raw, dict):
        # raw may be difficulty_by_role map or a single assessment dict
        if role_short in raw and isinstance(raw[role_short], dict):
            return DifficultyAssessment.model_validate(raw[role_short])
        if "overall" in raw or "code" in raw:
            return DifficultyAssessment.model_validate(raw)
    return score_task_difficulty(
        task_text, role_path=role_path or role_short, subtask=role_short
    )
