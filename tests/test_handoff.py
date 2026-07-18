"""Unit tests for the formal agent handoff protocol (core.handoff)."""

from __future__ import annotations

import pytest

from core.handoff import HandoffError, transfer_control
from schemas.handoff import HandoffRecord
from schemas.vibe_coding import TechnicalSpec


def test_transfer_control_preserves_user_input_and_appends_history():
    state = {
        "idea": "Build a CLI todo app",
        "spec": None,
        "handoff_history": [],
    }
    spec = TechnicalSpec(
        architecture="simple",
        test_cases=["t1"],
        files_to_create=["main.py"],
    )
    patch = transfer_control(
        state,
        from_agent="architect",
        to_agent="coder",
        reason="spec ready",
        pipeline="vibe_coding",
        user_input_key="idea",
        updates={"spec": spec, "error": None},
        require_keys=["spec"],
    )
    assert patch["spec"] is spec
    assert len(patch["handoff_history"]) == 1
    rec = patch["handoff_history"][0]
    assert rec["from_agent"] == "architect"
    assert rec["to_agent"] == "coder"
    assert rec["user_input"] == "Build a CLI todo app"
    assert "spec" in rec["carried_keys"]
    assert "idea" in rec["carried_keys"]
    # Validate against Pydantic schema
    HandoffRecord.model_validate(rec)


def test_transfer_control_refuses_empty_user_input():
    with pytest.raises(HandoffError, match="user input"):
        transfer_control(
            {"idea": "   ", "handoff_history": []},
            from_agent="architect",
            to_agent="coder",
            reason="x",
            pipeline="vibe_coding",
            user_input_key="idea",
            updates={"error": None},
        )


def test_transfer_control_refuses_missing_required_keys():
    with pytest.raises(HandoffError, match="required context"):
        transfer_control(
            {"query": "quantum", "handoff_history": []},
            from_agent="grounding",
            to_agent="synthesizer",
            reason="x",
            pipeline="deep_research",
            user_input_key="query",
            updates={"error": None},
            require_keys=["grounded_report"],
        )


def test_transfer_control_refuses_clearing_user_input():
    with pytest.raises(HandoffError, match="clear"):
        transfer_control(
            {"query": "keep me", "handoff_history": []},
            from_agent="safety_filter",
            to_agent="END",
            reason="x",
            pipeline="deep_research",
            user_input_key="query",
            updates={"query": ""},
        )


def test_history_accumulates_across_handoffs():
    state: dict = {"query": "topic", "handoff_history": []}
    s1 = transfer_control(
        state,
        from_agent="safety_filter",
        to_agent="context_compressor",
        reason="safe",
        pipeline="deep_research",
        user_input_key="query",
        updates={"safety": object()},
    )
    state = {**state, **s1}
    s2 = transfer_control(
        state,
        from_agent="context_compressor",
        to_agent="web_search",
        reason="trends",
        pipeline="deep_research",
        user_input_key="query",
        updates={"trends": object()},
    )
    assert len(s2["handoff_history"]) == 2
    assert s2["handoff_history"][0]["from_agent"] == "safety_filter"
    assert s2["handoff_history"][1]["from_agent"] == "context_compressor"
