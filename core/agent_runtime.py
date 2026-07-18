"""
Shared runtime helpers for every agent role.

Eliminates the 8-way copy of: load YAML config → call router → strip fences →
validate JSON. Tests can still pass a plain callable as ``router_instance``;
production uses ``call_agent`` / ``ModelRouter.call_agent``.

Optionally applies difficulty-based model selection (``core.model_selector``)
and reasoning-effort kwargs (``core.reasoning_params``) before the call.
Never log message contents or API keys here — only role path + provider/model.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Mapping, MutableMapping, Optional, TypeVar

from pydantic import BaseModel

from core.agent_config import get_agent_config
from core.difficulty_scorer import DifficultyAssessment, score_task_difficulty
from core.model_selector import ModelSelection, select_for_role
from core.reasoning_params import resolve_reasoning_kwargs
from core.router import LLMResponse, call_agent

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Callable shape used by tests (mock_router(provider, model, messages, **kw)).
RouterLike = Any


def strip_fences(content: str) -> str:
    """Remove optional markdown code fences around model JSON/text output."""
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()
    return text


def invoke_router(
    router_instance: Optional[RouterLike],
    *,
    provider: str,
    model: str,
    messages: list[dict[str, str]],
    fallback: Optional[dict[str, str]] = None,
    assessment: Optional[DifficultyAssessment] = None,
    role_path: str = "",
    apply_reasoning: bool = True,
    **kwargs: Any,
) -> LLMResponse:
    """Call either ``ModelRouter.call_agent``, module ``call_agent``, or a test mock.

    When ``apply_reasoning`` is true, merges difficulty-based reasoning kwargs
    for models that support them (see ``core.reasoning_params``). Explicit
    ``kwargs`` from the caller win over auto-injected keys.

    Never puts secrets in logs — only provider/model.
    """
    call_kwargs: dict[str, Any] = dict(kwargs)

    if apply_reasoning:
        auto = resolve_reasoning_kwargs(
            provider,
            model,
            assessment=assessment,
            role_path=role_path,
        )
        # Auto first, caller overrides (e.g. force include_reasoning=True)
        call_kwargs = {**auto, **call_kwargs}
        if assessment is not None:
            call_kwargs["_difficulty_assessment"] = assessment
        if role_path:
            call_kwargs["_role_path"] = role_path

    caller = router_instance if router_instance is not None else call_agent
    final: dict[str, Any] = {
        "provider": provider,
        "model": model,
        "messages": messages,
        **call_kwargs,
    }
    if fallback is not None:
        final["fallback"] = fallback

    effort = call_kwargs.get("reasoning_effort")
    logger.debug(
        "LLM call → %s/%s reasoning_effort=%s",
        provider,
        model,
        effort,
    )

    if hasattr(caller, "call_agent"):
        return caller.call_agent(**final)
    return caller(**final)


def _task_text_from_messages(messages: list[dict[str, str]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user" and msg.get("content"):
            return str(msg["content"])
    if messages:
        return str(messages[-1].get("content") or "")
    return ""


def resolve_role_selection(
    *role_path: str,
    messages: list[dict[str, str]],
    assessment: Optional[DifficultyAssessment] = None,
    task_text: Optional[str] = None,
    fallback_override: Optional[dict[str, str]] = None,
    skip_difficulty_selection: bool = False,
    today: Optional[date] = None,
) -> tuple[
    str,
    str,
    Optional[dict[str, str]],
    Optional[ModelSelection],
    Optional[DifficultyAssessment],
]:
    """Return (provider, model, fallback, selection, assessment) for a role call."""
    cfg = get_agent_config(*role_path)
    dotted = ".".join(role_path)
    text = task_text if task_text is not None else _task_text_from_messages(messages)

    if skip_difficulty_selection:
        fb = fallback_override if fallback_override is not None else cfg.get("fallback")
        assess = assessment or score_task_difficulty(
            text, role_path=dotted, subtask=role_path[-1] if role_path else ""
        )
        return str(cfg["provider"]), str(cfg["model"]), fb, None, assess

    assess = assessment or score_task_difficulty(
        text, role_path=dotted, subtask=role_path[-1] if role_path else ""
    )
    selection = select_for_role(*role_path, assessment=assess, today=today)

    # If caller forced a fallback_override, prefer that as the *chain* after selection
    if selection.used_fallback:
        fb = fallback_override  # may be None — already on fallback model
    else:
        fb = (
            fallback_override
            if fallback_override is not None
            else selection.chain_fallback or cfg.get("fallback")
        )

    logger.info(
        "Role %s → %s/%s (fallback_used=%s, overall=%s)",
        dotted,
        selection.provider,
        selection.model,
        selection.used_fallback,
        selection.assessment_overall,
    )
    return selection.provider, selection.model, fb, selection, assess


def run_structured_agent(
    *role_path: str,
    messages: list[dict[str, str]],
    schema: type[T],
    router_instance: Optional[RouterLike] = None,
    fallback_override: Optional[dict[str, str]] = None,
    assessment: Optional[DifficultyAssessment] = None,
    task_text: Optional[str] = None,
    skip_difficulty_selection: bool = False,
    today: Optional[date] = None,
    selection_out: Optional[MutableMapping[str, Any]] = None,
    apply_reasoning: bool = True,
    **call_kwargs: Any,
) -> T:
    """Load role config, pick model by difficulty, apply reasoning, call LLM.

    Example::

        return run_structured_agent(
            "vibe_coding", "architect",
            messages=messages,
            schema=TechnicalSpec,
            router_instance=router_instance,
        )

    Pass ``selection_out`` (mutable dict) to capture the :class:`ModelSelection`
    as ``selection_out["selection"]`` for graph-level handoff recording.
    """
    provider, model, fb, selection, assess = resolve_role_selection(
        *role_path,
        messages=messages,
        assessment=assessment,
        task_text=task_text,
        fallback_override=fallback_override,
        skip_difficulty_selection=skip_difficulty_selection,
        today=today,
    )
    if selection_out is not None and selection is not None:
        selection_out["selection"] = selection

    resp = invoke_router(
        router_instance,
        provider=provider,
        model=model,
        messages=messages,
        fallback=fb,
        assessment=assess,
        role_path=".".join(role_path),
        apply_reasoning=apply_reasoning,
        **call_kwargs,
    )
    return schema.model_validate_json(strip_fences(resp.content))


def run_role_raw(
    *role_path: str,
    messages: list[dict[str, str]],
    router_instance: Optional[RouterLike] = None,
    fallback_override: Optional[dict[str, str]] = None,
    assessment: Optional[DifficultyAssessment] = None,
    task_text: Optional[str] = None,
    skip_difficulty_selection: bool = False,
    today: Optional[date] = None,
    selection_out: Optional[MutableMapping[str, Any]] = None,
    apply_reasoning: bool = True,
    **call_kwargs: Any,
) -> LLMResponse:
    """Like ``run_structured_agent`` but returns the raw ``LLMResponse`` (prose paths)."""
    provider, model, fb, selection, assess = resolve_role_selection(
        *role_path,
        messages=messages,
        assessment=assessment,
        task_text=task_text,
        fallback_override=fallback_override,
        skip_difficulty_selection=skip_difficulty_selection,
        today=today,
    )
    if selection_out is not None and selection is not None:
        selection_out["selection"] = selection

    return invoke_router(
        router_instance,
        provider=provider,
        model=model,
        messages=messages,
        fallback=fb,
        assessment=assess,
        role_path=".".join(role_path),
        apply_reasoning=apply_reasoning,
        **call_kwargs,
    )
