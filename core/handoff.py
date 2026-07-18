"""
Central handoff API for LangGraph agent nodes.

``transfer_control`` is the **only official** way for a graph node to pass
control (and context) to another node: it validates that the original user
input is still present, appends a :class:`~schemas.handoff.HandoffRecord`,
and returns a LangGraph state-update dict that merges cleanly with existing
domain fields (``spec``, ``artifact``, ``grounded_report``, …).
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, MutableMapping, Optional, Sequence

from schemas.handoff import HandoffRecord, PipelineName

logger = logging.getLogger(__name__)

# Domain keys we surface in handoff audit trails (values stay on graph state).
VIBE_CONTEXT_KEYS: tuple[str, ...] = (
    "idea",
    "spec",
    "artifact",
    "test_logs",
    "debug_report",
    "fix_attempts",
    "git_checkpoint_sha",
    "user_wip_stashed",
    "error",
    "difficulty_by_role",
    "last_model_selection",
    "handoff_history",
)

RESEARCH_CONTEXT_KEYS: tuple[str, ...] = (
    "query",
    "safety",
    "trends",
    "search_results",
    "grounded_report",
    "final_report",
    "error",
    "difficulty_by_role",
    "last_model_selection",
    "handoff_history",
)


class HandoffError(ValueError):
    """Raised when a handoff would drop mandatory user context."""


def _coerce_history(raw: Any) -> list[dict[str, Any]]:
    if not raw:
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, HandoffRecord):
            out.append(item.model_dump())
        elif isinstance(item, Mapping):
            out.append(dict(item))
        else:
            logger.warning("Ignoring non-mapping handoff history item: %r", type(item))
    return out


def _present_keys(merged: Mapping[str, Any], candidates: Sequence[str]) -> list[str]:
    carried: list[str] = []
    for key in candidates:
        val = merged.get(key)
        if val is None:
            continue
        if val == "" or val == [] or val == {}:
            continue
        carried.append(key)
    return carried


def extract_user_input(
    state: Mapping[str, Any],
    user_input_key: str,
    *,
    updates: Optional[Mapping[str, Any]] = None,
) -> str:
    """Return non-empty user input from updates or state, else raise."""
    candidates = []
    if updates and user_input_key in updates:
        candidates.append(updates.get(user_input_key))
    candidates.append(state.get(user_input_key))
    for raw in candidates:
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            return text
    raise HandoffError(
        f"Handoff refused: mandatory user input key {user_input_key!r} is "
        f"missing or empty — refusing to transfer control (would drop user context)."
    )


def transfer_control(
    state: Mapping[str, Any],
    *,
    from_agent: str,
    to_agent: str,
    reason: str,
    pipeline: PipelineName,
    user_input_key: str,
    updates: Optional[MutableMapping[str, Any]] = None,
    require_keys: Optional[Sequence[str]] = None,
    note: Optional[str] = None,
    context_keys: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    """Build a LangGraph state patch that records a formal agent handoff.

    Parameters
    ----------
    state:
        Current graph state (read-only).
    from_agent / to_agent:
        Node names (or sinks: ``END``, ``git_commit``, ``git_rollback``).
    reason:
        Why control is transferring (Swarm-style explicit transfer motive).
    pipeline:
        ``\"vibe_coding\"`` or ``\"deep_research\"``.
    user_input_key:
        Key holding the original user prompt (``idea`` or ``query``).
    updates:
        Domain fields this node is writing (``spec``, ``error``, …).
        Must **not** clear or overwrite the user-input key with empty.
    require_keys:
        Keys that must be present and truthy in the *merged* view after this
        handoff (e.g. ``[\"spec\"]`` after architect). Raises :class:`HandoffError`
        if any are missing.
    note:
        Optional diagnostic string stored on the handoff record.
    context_keys:
        Which state keys to list as ``carried_keys`` when present.
        Defaults depend on ``pipeline``.

    Returns
    -------
    dict
        Partial state for LangGraph to merge — always includes
        ``handoff_history`` (full list) plus any ``updates``.
    """
    patch: dict[str, Any] = dict(updates or {})

    # Never allow an update to wipe the original user input.
    if user_input_key in patch:
        incoming = patch[user_input_key]
        if incoming is None or (isinstance(incoming, str) and not incoming.strip()):
            raise HandoffError(
                f"Handoff refused: updates would clear {user_input_key!r}."
            )

    user_input = extract_user_input(state, user_input_key, updates=patch)

    # Merged view for validation + carried_keys (state base + this patch).
    merged: dict[str, Any] = {**dict(state), **patch}
    # Ensure user input key is visible even if only validated from state.
    merged[user_input_key] = user_input

    if require_keys:
        missing = [k for k in require_keys if not merged.get(k)]
        if missing:
            msg = (
                f"Handoff {from_agent!r} → {to_agent!r} refused: required context "
                f"keys missing after node work: {missing}"
            )
            logger.error(msg)
            raise HandoffError(msg)

    keys_catalog = context_keys
    if keys_catalog is None:
        keys_catalog = (
            VIBE_CONTEXT_KEYS if pipeline == "vibe_coding" else RESEARCH_CONTEXT_KEYS
        )
    carried = _present_keys(merged, keys_catalog)

    record = HandoffRecord(
        from_agent=from_agent,
        to_agent=to_agent,
        reason=reason,
        user_input=user_input,
        pipeline=pipeline,
        carried_keys=carried,
        note=note,
    )

    history = _coerce_history(state.get("handoff_history"))
    history.append(record.model_dump())
    patch["handoff_history"] = history

    logger.info(
        "HANDOFF %s → %s (%s) pipeline=%s carried=%s",
        from_agent,
        to_agent,
        reason,
        pipeline,
        carried,
    )
    return patch


def seed_handoff_state(
    *,
    user_input: str,
    user_input_key: str,
    pipeline: PipelineName,
    extra: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Helper for ``initial_*_state`` builders: validate seed user input."""
    text = (user_input or "").strip()
    if not text:
        raise HandoffError(
            f"Cannot start {pipeline} pipeline: empty {user_input_key!r}."
        )
    base: dict[str, Any] = {
        user_input_key: text,
        "handoff_history": [],
        "error": None,
    }
    if extra:
        base.update(extra)
    return base
