"""
Formal handoff contracts between LangGraph agent nodes.

Inspired by OpenAI Swarm-style transfers: each agent may yield control to
another while preserving the original user input, intermediate artifacts,
and an explicit audit trail of who held control and why it moved.

Domain payloads (TechnicalSpec, CodeArtifact, GroundedReport, …) live in
``schemas.vibe_coding`` / ``schemas.deep_research`` — this module only
defines the *transfer envelope*, not those types.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


PipelineName = Literal["vibe_coding", "deep_research"]


class HandoffRecord(BaseModel):
    """One control transfer between two named agents (or terminal sinks)."""

    from_agent: str = Field(
        ...,
        description="Agent/node that is releasing control.",
    )
    to_agent: str = Field(
        ...,
        description="Agent/node (or sink: END, git_commit, git_rollback) receiving control.",
    )
    reason: str = Field(
        ...,
        description="Human-readable why this transfer happened.",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="UTC ISO-8601 time of the handoff.",
    )
    user_input: str = Field(
        ...,
        description="Original user input snapshot at transfer time (must not be empty).",
    )
    pipeline: PipelineName = Field(
        ...,
        description="Which pipeline this transfer belongs to.",
    )
    carried_keys: list[str] = Field(
        default_factory=list,
        description=(
            "State keys known to hold intermediate context after this handoff "
            "(e.g. 'spec', 'artifact', 'grounded_report'). Values stay in graph state."
        ),
    )
    note: Optional[str] = Field(
        default=None,
        description="Optional short diagnostic note (errors, cycle counts, etc.).",
    )


class HandoffEnvelope(BaseModel):
    """Optional structured view of the full transfer history for a run.

    Graph state stores a plain list of dicts (``handoff_history``) for
    LangGraph/TypedDict friendliness; use this model when validating or
    serializing the whole trail.
    """

    user_input: str
    pipeline: PipelineName
    history: list[HandoffRecord] = Field(default_factory=list)

    @classmethod
    def from_state(
        cls,
        state: dict[str, Any],
        *,
        pipeline: PipelineName,
        user_input_key: str,
    ) -> "HandoffEnvelope":
        raw_user = state.get(user_input_key) or ""
        history_raw = state.get("handoff_history") or []
        history: list[HandoffRecord] = []
        for item in history_raw:
            if isinstance(item, HandoffRecord):
                history.append(item)
            elif isinstance(item, dict):
                history.append(HandoffRecord.model_validate(item))
        return cls(user_input=str(raw_user), pipeline=pipeline, history=history)
