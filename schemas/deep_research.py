"""
Pydantic schemas for the System B (Deep Research) pipeline.
These models define the strict API boundaries between the Safety Filter,
Context Compressor, Grounding, and Synthesizer agents.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SafetyClassification(BaseModel):
    """Output schema for the Safety Filter agent.

    Determines if the research topic is safe to process.
    """

    is_safe: bool = Field(
        ...,
        description="True if the input topic is safe, ethical, and complies with policies. False otherwise."
    )
    reasons: list[str] = Field(
        default_factory=list,
        description="List of reasons for the safety classification (empty if safe)."
    )


class CondensedTrends(BaseModel):
    """Output schema for the Context Compressor agent.

    Search terms plus an optional research typology profile so downstream
    agents adapt depth/purpose/data/design without domain hardcoding.
    """

    technologies: list[str] = Field(
        ...,
        description="List of core search terms extracted from the prompt.",
    )
    rationale: str = Field(
        ...,
        description="Brief analysis explaining why these search terms were prioritized.",
    )
    # Research typology (optional on wire; defaults keep old callers working)
    purpose: str = Field(
        default="applied",
        description="basic | applied — theoretical expansion vs practical problem-solving.",
    )
    depth: str = Field(
        default="descriptive",
        description="exploratory | descriptive | explanatory",
    )
    data_approach: str = Field(
        default="mixed",
        description="quantitative | qualitative | mixed",
    )
    design: str = Field(
        default="non_experimental",
        description="experimental | non_experimental",
    )
    profile_rationale: str = Field(
        default="",
        description="Why this research profile was chosen for the topic.",
    )
    # WAVE-18: safety gate folded into this role (the dedicated safety_filter
    # role was removed). Safe defaults keep old callers working.
    is_safe: bool = Field(
        default=True,
        description="False if the research topic falls into any unsafe category.",
    )
    safety_reasons: list[str] = Field(
        default_factory=list,
        description="Why the topic was flagged unsafe (empty when safe).",
    )


class GroundedReport(BaseModel):
    """Output schema for the Grounding and Synthesizer agents.

    Represents the final grounded research summary with explicit sources/citations.
    """

    content: str = Field(
        ...,
        description="The detailed research text body, incorporating references and citations."
    )
    sources: list[str] = Field(
        ...,
        description="List of URLs, articles, or source documents used to back up the report assertions."
    )
