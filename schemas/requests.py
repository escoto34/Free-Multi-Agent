"""
Public entry schemas for CLI / MCP / future HTTP APIs.

Validates user input *before* any LLM call so garbage prompts fail cheaply
instead of burning free-tier quota.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# Pipeline chaining (/do research → vibe) injects prior step output into idea/topic.
# Keep room for a full research report + instruction without hitting validation.
_PIPELINE_INPUT_MAX = 32000


class VibeCodingRequest(BaseModel):
    """Input for System A (Vibe Coding)."""

    idea: str = Field(
        ...,
        min_length=3,
        max_length=_PIPELINE_INPUT_MAX,
        description="Natural-language description of what to build.",
    )


class DeepResearchRequest(BaseModel):
    """Input for System B (Deep Research)."""

    topic: str = Field(
        ...,
        min_length=3,
        max_length=_PIPELINE_INPUT_MAX,
        description="Research topic / query.",
    )
    thread_id: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Optional LangGraph thread id to resume a checkpoint.",
    )


class PipelineStep(BaseModel):
    """One step chosen by the planner AI for a user prompt."""

    action: str = Field(
        ...,
        description='Either "vibe" (System A code) or "research" (System B research).',
    )
    prompt: str = Field(
        ...,
        min_length=3,
        max_length=4000,
        description="Sub-prompt for this step (may be a slice of the user request).",
    )
    rationale: str = Field(
        default="",
        description="Why this step is needed and how it complements others.",
    )
    uses_prior: bool = Field(
        default=False,
        description="If true, feed prior step outputs into this step as context.",
    )


class PipelinePlan(BaseModel):
    """Planner output: ordered steps using vibe and/or research."""

    summary: str = Field(
        default="",
        description="One-line plan overview for the user.",
    )
    steps: list[PipelineStep] = Field(
        ...,
        min_length=1,
        max_length=6,
        description="Ordered steps; research then vibe is common when both are needed.",
    )
