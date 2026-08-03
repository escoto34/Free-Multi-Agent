"""Fake LLM provider for deterministic, keyless testing.

Test double for the router/client seams introduced in WAVE-02. It mimics the
OpenAI-compatible client surface used by ``core.router._call_openai_compatible``
(``client.chat.completions.create(...)`` returning ``resp.choices[0].message.content``)
and injects configurable failure modes so retry/timeout code paths are testable
without a live provider or per-call-site monkeypatching.

Not a full OpenAI SDK reimplementation — only the method/attribute surface the
MultiAgent router actually consumes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

__all__ = ["FakeLLMProvider", "FakeChatCompletion", "FakeChoice", "FakeMessage"]

del Callable


@dataclass
class FakeMessage:
    content: str
    role: str = "assistant"


@dataclass
class FakeChoice:
    message: FakeMessage


@dataclass
class FakeChatCompletion:
    choices: list[FakeChoice] = field(default_factory=list)


class FakeProviderError(Exception):
    """Carries an HTTP-like status code; the router extracts it via status_code."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


class _FakeCompletions:
    def __init__(self, provider: "FakeLLMProvider") -> None:
        self._provider = provider

    def create(
        self,
        model: str,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> FakeChatCompletion:
        content = self._provider._create(model, messages, **kwargs)
        return FakeChatCompletion(
            choices=[FakeChoice(message=FakeMessage(content=content))]
        )


class _FakeChat:
    def __init__(self, provider: "FakeLLMProvider") -> None:
        self.completions = _FakeCompletions(provider)
        self._provider = provider

    def create(self, model: str, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        content = self._provider._create(model, messages, **kwargs)
        # Minimal cohere-like envelope for the cohere_v2 path.
        block = type("Block", (), {"text": content})()
        msg = type("Msg", (), {"content": [block]})()
        return type("Resp", (), {"message": msg})()


class FakeLLMProvider:
    """Deterministic LLM provider with injectable failure modes.

    Args:
        transient_failures: number of times calls fail with a 429-style error
            before succeeding. 2 means "fails exactly twice, third call succeeds".
        permanent_failure: if True, every call fails with ``permanent_failure_status``.
        delay_seconds: sleep this long before answering, to simulate latency.
        responses: mapping from model name (or last-user-message substring, applied
            longest-substring-match) to the canned completion content.
        default_content: content used when no canned response matches.
    """

    def __init__(
        self,
        *,
        transient_failures: int = 0,
        permanent_failure: bool = False,
        permanent_failure_status: int = 500,
        delay_seconds: float = 0.0,
        responses: Optional[dict[str, Any]] = None,
        default_content: str = "This is a deterministic fake response.",
    ) -> None:
        self.transient_failures = max(0, transient_failures)
        self.permanent_failure = permanent_failure
        self.permanent_failure_status = permanent_failure_status
        self.delay_seconds = max(0.0, delay_seconds)
        self.responses = dict(responses or {})
        self.default_content = default_content

        # Records every call for inspection: list of (model, messages, kwargs).
        self.call_log: list[tuple[str, list[dict[str, str]], dict[str, Any]]] = []
        self._transient_remaining = self.transient_failures

        self.chat = _FakeChat(self)

    def _create(
        self,
        model: str,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> str:
        self.call_log.append((model, messages, dict(kwargs)))

        if self.delay_seconds:
            time.sleep(self.delay_seconds)

        if self.permanent_failure:
            raise FakeProviderError(
                self.permanent_failure_status,
                f"Fake provider permanent failure for {model}",
            )

        if self._transient_remaining > 0:
            self._transient_remaining -= 1
            raise FakeProviderError(429, f"Fake provider transient failure for {model}")

        return self._resolve_content(model, messages)

    def _resolve_content(self, model: str, messages: list[dict[str, str]]) -> str:
        """Pick a canned response by model name, then by user-message substring."""
        if model in self.responses:
            return str(self.responses[model])

        last_user = ""
        for m in reversed(messages or []):
            if m.get("role") == "user":
                last_user = str(m.get("content") or "")
                break
        if last_user:
            best: Optional[tuple[int, str]] = None
            for key, value in self.responses.items():
                text = str(key)
                if text in last_user and (best is None or len(text) > best[0]):
                    best = (len(text), str(value))
            if best is not None:
                return best[1]
        return self.default_content

    def reset(self) -> None:
        """Reset injected-failure state and call log (but not responses)."""
        self._transient_remaining = self.transient_failures
        self.call_log.clear()