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

    Represents key entities, trends, or summarized points to guide the web search query.
    """

    technologies: list[str] = Field(
        ...,
        description="List of core technologies, trends, or search terms extracted from the prompt."
    )
    rationale: str = Field(
        ...,
        description="Brief analysis explaining why these search terms were prioritized."
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
