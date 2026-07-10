"""
Shared runtime helpers for every agent role.

Eliminates the 8-way copy of: load YAML config → call router → strip fences →
validate JSON. Tests can still pass a plain callable as ``router_instance``;
production uses ``call_agent`` / ``ModelRouter.call_agent``.

Never log message contents or API keys here — only role path + provider/model.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, TypeVar

from pydantic import BaseModel

from core.agent_config import get_agent_config
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
    **kwargs: Any,
) -> LLMResponse:
    """Call either ``ModelRouter.call_agent``, module ``call_agent``, or a test mock.

    Never puts secrets in logs — only provider/model.
    """
    caller = router_instance if router_instance is not None else call_agent
    call_kwargs: dict[str, Any] = {
        "provider": provider,
        "model": model,
        "messages": messages,
        **kwargs,
    }
    if fallback is not None:
        call_kwargs["fallback"] = fallback

    logger.debug("LLM call → %s/%s", provider, model)

    if hasattr(caller, "call_agent"):
        return caller.call_agent(**call_kwargs)
    return caller(**call_kwargs)


def run_structured_agent(
    *role_path: str,
    messages: list[dict[str, str]],
    schema: type[T],
    router_instance: Optional[RouterLike] = None,
    fallback_override: Optional[dict[str, str]] = None,
    **call_kwargs: Any,
) -> T:
    """Load role config from YAML, call the router, parse JSON into ``schema``.

    Example::

        return run_structured_agent(
            "vibe_coding", "architect",
            messages=messages,
            schema=TechnicalSpec,
            router_instance=router_instance,
        )
    """
    cfg = get_agent_config(*role_path)
    fb = fallback_override if fallback_override is not None else cfg.get("fallback")

    resp = invoke_router(
        router_instance,
        provider=cfg["provider"],
        model=cfg["model"],
        messages=messages,
        fallback=fb,
        **call_kwargs,
    )
    return schema.model_validate_json(strip_fences(resp.content))


def run_role_raw(
    *role_path: str,
    messages: list[dict[str, str]],
    router_instance: Optional[RouterLike] = None,
    fallback_override: Optional[dict[str, str]] = None,
    **call_kwargs: Any,
) -> LLMResponse:
    """Like ``run_structured_agent`` but returns the raw ``LLMResponse`` (prose paths)."""
    cfg = get_agent_config(*role_path)
    fb = fallback_override if fallback_override is not None else cfg.get("fallback")
    return invoke_router(
        router_instance,
        provider=cfg["provider"],
        model=cfg["model"],
        messages=messages,
        fallback=fb,
        **call_kwargs,
    )
