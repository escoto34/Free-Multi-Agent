"""
Intelligent model router with cascading fallback and quota management.

The router wraps all LLM calls and provides:

1. **Quota gating** — refuses to call a provider whose daily quota is
   exhausted and immediately falls back.
2. **Exponential-backoff retries** — on transient HTTP 429/402/413/422 errors.
3. **Cascading fallback** — when retries are exhausted the router walks
   through the configured fallback chain:

       Cohere  →  OpenRouter / hy3:free
       OpenRouter  →  Groq / gpt-oss-120b
       Groq  →  OpenRouter / north-mini-code:free

   Role-specific overrides (e.g. debugger's hy3 → gpt-oss-120b) can be
   passed via the ``fallback`` argument to ``call_agent``.
4. **Cycle detection** — a ``_visited`` set prevents infinite loops when
   the cascade circles back on itself.
5. **Empty-content guard** — a call that "succeeds" at the HTTP level but
   returns an empty/whitespace-only completion is treated as a failure and
   cascades to the next fallback, instead of silently returning empty
   content that later crashes downstream Pydantic validation.

Usage::

    from core.router import call_agent

    response = call_agent(
        provider="cohere",
        model="command-a-plus-05-2026",
        messages=[{"role": "user", "content": "Hello"}],
    )
    print(response.content)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import cohere as cohere_sdk
import yaml
from openai import APIStatusError, OpenAI

from core.clients import get_client
from core.quotas import QuotaTracker

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "model_router.yaml"

# HTTP status codes that trigger retry / fallback.
# 413 added: a payload-too-large response should also cascade (retrying the
# exact same oversized payload would just fail again, but the cascade to a
# different provider/model is still the correct behaviour).
_RETRIABLE_STATUSES = frozenset({402, 413, 422, 429})


class EmptyCompletionError(Exception):
    """Raised when a provider returns HTTP 200 but empty/whitespace content.

    Treated as a non-retriable-but-cascadable failure: the current
    provider/model is considered to have failed, and the router falls
    back to the next one in the chain, exactly as it would for a 422/429.
    """


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class LLMResponse:
    """Standardised response envelope returned by ``call_agent``."""

    content: str
    provider: str
    model: str
    used_fallback: bool = False
    fallback_reason: str = ""
    raw_response: Any = field(default=None, repr=False)


class QuotaExhaustedError(Exception):
    """Raised when every provider in the fallback chain is exhausted."""


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


class ModelRouter:
    """Routes LLM calls with automatic fallback cascade and quota tracking."""

    def __init__(
        self,
        config_path: Optional[Path] = None,
        quota_tracker: Optional[QuotaTracker] = None,
    ) -> None:
        self._config_path = config_path or _CONFIG_PATH
        self._config = self._load_config()
        self._quota = quota_tracker or QuotaTracker()

    def _load_config(self) -> dict:
        with open(self._config_path) as fh:
            return yaml.safe_load(fh)

    @property
    def quota(self) -> QuotaTracker:
        return self._quota

    def _resolve_fallback(
        self,
        provider: str,
        model: str,
        explicit: Optional[dict[str, str]],
    ) -> Optional[dict[str, str]]:
        if explicit:
            return explicit
        cascade = self._config.get("fallback_cascade", {})
        entry = cascade.get(f"{provider}_fallback")
        if entry:
            return {"provider": entry["provider"], "model": entry["model"]}
        return None

    @staticmethod
    def _call_openai_compatible(
        client: OpenAI,
        model: str,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> tuple[str, Any]:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            **kwargs,
        )
        content = response.choices[0].message.content or ""
        return content, response

    @staticmethod
    def _call_cohere_v2(
        client: cohere_sdk.ClientV2,
        model: str,
        messages: list[dict[str, str]],
        documents: Optional[list[dict]] = None,
        **kwargs: Any,
    ) -> tuple[str, Any]:
        call_kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        if documents is not None:
            call_kwargs["documents"] = documents
        call_kwargs.update(kwargs)

        response = client.chat(**call_kwargs)

        text = ""
        if hasattr(response.message, "content") and response.message.content:
            for block in response.message.content:
                if hasattr(block, "text"):
                    text = block.text
                    break
        return text, response

    def _dispatch(
        self,
        provider: str,
        model: str,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> tuple[str, Any]:
        """Route the call to the correct provider backend.

        Raises:
            EmptyCompletionError: if the provider returned HTTP 200 but the
                completion content is empty or whitespace-only.
        """
        client = get_client(provider)

        if provider == "cohere":
            documents = kwargs.pop("documents", None)
            content, raw = self._call_cohere_v2(
                client, model, messages, documents=documents, **kwargs
            )
        else:
            clean = {k: v for k, v in kwargs.items() if k not in ("documents",)}
            content, raw = self._call_openai_compatible(
                client, model, messages, **clean
            )

        if not content or not content.strip():
            raise EmptyCompletionError(
                f"{provider}/{model} returned HTTP 200 with empty/whitespace "
                "completion content — treating as a failure to trigger fallback."
            )

        return content, raw

    @staticmethod
    def _extract_status(error: Exception) -> Optional[int]:
        if isinstance(error, APIStatusError):
            return error.status_code
        status = getattr(error, "status_code", None)
        if status is not None:
            return int(status)
        return None

    def call_agent(
        self,
        provider: str,
        model: str,
        messages: list[dict[str, str]],
        *,
        fallback: Optional[dict[str, str]] = None,
        max_retries: int = 3,
        base_delay: float = 1.0,
        _visited: Optional[set[tuple[str, str]]] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Make an LLM call with automatic fallback on quota / HTTP / empty-completion errors.

        Returns:
            :class:`LLMResponse` with the generated content and metadata.
            ``content`` is guaranteed to be non-empty.

        Raises:
            QuotaExhaustedError: Every provider in the chain is exhausted or
                has failed permanently (including empty-completion failures).
        """
        if _visited is None:
            _visited = set()

        key = (provider, model)
        if key in _visited:
            raise QuotaExhaustedError(
                f"Cycle detected in fallback chain at {provider}/{model}. "
                f"Visited: {_visited}"
            )
        _visited.add(key)

        if not self._quota.can_call(provider, model):
            logger.warning(
                "Quota exhausted for %s/%s (remaining: %d). Cascading…",
                provider,
                model,
                self._quota.remaining(provider, model),
            )
            return self._cascade(
                provider,
                model,
                messages,
                fallback=fallback,
                reason=f"Quota exhausted for {provider}/{model}",
                max_retries=max_retries,
                base_delay=base_delay,
                _visited=_visited,
                **kwargs,
            )

        last_error: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                content, raw = self._dispatch(provider, model, messages, **kwargs)
                self._quota.record_call(provider, model)
                logger.info(
                    "✔ %s/%s  attempt=%d  remaining=%d",
                    provider,
                    model,
                    attempt,
                    self._quota.remaining(provider, model),
                )
                return LLMResponse(
                    content=content,
                    provider=provider,
                    model=model,
                    raw_response=raw,
                )

            except EmptyCompletionError as exc:
                # Go straight to fallback — retrying the same call won't help.
                last_error = exc
                logger.error("Empty completion from %s/%s: %s", provider, model, exc)
                break

            except Exception as exc:
                last_error = exc
                status = self._extract_status(exc)

                # Cohere's 422 NO_VALID_RESPONSE_GENERATED is a semantic
                # rejection, not a transient rate-limit — retrying the exact
                # same payload 3 times just wastes Cohere's scarce daily
                # quota for no benefit. Fail fast to fallback on the first
                # 422 from Cohere specifically, instead of exhausting all
                # retries like we do for genuinely transient errors (429/402).
                if provider == "cohere" and status == 422:
                    logger.warning(
                        "HTTP 422 from %s/%s — Cohere semantic rejection, "
                        "skipping remaining retries to save quota.",
                        provider,
                        model,
                    )
                    break
                elif status in _RETRIABLE_STATUSES and attempt < max_retries:
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "HTTP %s from %s/%s  attempt=%d/%d  retry_in=%.1fs",
                        status,
                        provider,
                        model,
                        attempt,
                        max_retries,
                        delay,
                    )
                    time.sleep(delay)
                elif status in _RETRIABLE_STATUSES:
                    logger.warning(
                        "HTTP %s from %s/%s  attempt=%d/%d  retries exhausted",
                        status,
                        provider,
                        model,
                        attempt,
                        max_retries,
                    )
                    break
                else:
                    logger.error(
                        "Non-retriable error from %s/%s: %s", provider, model, exc
                    )
                    break

        reason = (
            f"All {max_retries} retries exhausted for {provider}/{model}: {last_error}"
        )
        logger.warning(reason)
        return self._cascade(
            provider,
            model,
            messages,
            fallback=fallback,
            reason=reason,
            max_retries=max_retries,
            base_delay=base_delay,
            _visited=_visited,
            **kwargs,
        )

    def _cascade(
        self,
        original_provider: str,
        original_model: str,
        messages: list[dict[str, str]],
        *,
        fallback: Optional[dict[str, str]],
        reason: str,
        max_retries: int,
        base_delay: float,
        _visited: set[tuple[str, str]],
        **kwargs: Any,
    ) -> LLMResponse:
        fb = self._resolve_fallback(original_provider, original_model, fallback)
        if fb is None:
            raise QuotaExhaustedError(
                f"No fallback configured for {original_provider}/{original_model}. "
                f"Reason: {reason}"
            )

        fb_provider = fb["provider"]
        fb_model = fb["model"]

        logger.info(
            "⤷ Fallback: %s/%s → %s/%s  reason='%s'",
            original_provider,
            original_model,
            fb_provider,
            fb_model,
            reason,
        )

        response = self.call_agent(
            provider=fb_provider,
            model=fb_model,
            messages=messages,
            fallback=None,
            max_retries=max_retries,
            base_delay=base_delay,
            _visited=_visited,
            **kwargs,
        )
        response.used_fallback = True
        response.fallback_reason = reason
        return response


_default_router: Optional[ModelRouter] = None


def get_router(
    config_path: Optional[Path] = None,
    quota_tracker: Optional[QuotaTracker] = None,
) -> ModelRouter:
    global _default_router
    if _default_router is None:
        _default_router = ModelRouter(
            config_path=config_path, quota_tracker=quota_tracker
        )
    return _default_router


def call_agent(
    provider: str,
    model: str,
    messages: list[dict[str, str]],
    **kwargs: Any,
) -> LLMResponse:
    """Module-level shortcut that delegates to the default router."""
    return get_router().call_agent(provider, model, messages, **kwargs)
