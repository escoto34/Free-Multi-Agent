"""
Multi-turn conversation context for the interactive CLI.

Tracks messages, estimates token usage (chars/4), and can compact older
turns into a summary so long sessions stay under the configured limit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from core.config_editor import get_cli_settings

logger = logging.getLogger(__name__)


def estimate_tokens(text: str) -> int:
    """Cheap token estimate without tiktoken (≈ 4 chars/token)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


@dataclass
class Message:
    role: str  # system | user | assistant | system-note
    content: str
    ts: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def tokens(self) -> int:
        return estimate_tokens(self.content)


@dataclass
class ConversationSession:
    """In-memory chat session with a soft context budget."""

    messages: list[Message] = field(default_factory=list)
    limit_tokens: int = 32000
    keep_recent: int = 6
    # Session override for the planner AI (/planner set); None → YAML cli.planner
    planner_provider: Optional[str] = None
    planner_model: Optional[str] = None
    # Graphify injection state: only on session start or when graph.json changes.
    graph_used: bool = False
    graph_mtime_at_inject: Optional[float] = None
    cached_graph_snippet: str = ""
    # Tool approval: when True, write/terminal tools run without prompting.
    always_approve: bool = False
    system_prompt: str = (
        "You are the Free-Multi-Agent assistant for this local codebase. "
        "You may use host tools (read/write files, graphify, terminal) with user approval. "
        "Heavy work: /do <task> (planner chooses vibe-coding and/or deep-research). "
        "Other commands: /planner, /config, /keys, /skills, /tools, /help, /approve. "
        "For modern terminal tool recommendations use host tool toolbox_query "
        "(or tell the user about /tools doctor|suggest) — do not invent CLI names. "
        "Never invent API keys or secrets."
    )

    def __post_init__(self) -> None:
        settings = get_cli_settings()
        self.limit_tokens = int(settings["context_limit_tokens"])
        self.keep_recent = int(settings["compact_keep_recent_messages"])
        if not self.messages:
            self.messages.append(Message(role="system", content=self.system_prompt))

    def reload_limits(self) -> None:
        settings = get_cli_settings()
        self.limit_tokens = int(settings["context_limit_tokens"])
        self.keep_recent = int(settings["compact_keep_recent_messages"])

    def used_tokens(self) -> int:
        return sum(m.tokens() for m in self.messages)

    def usage_ratio(self) -> float:
        if self.limit_tokens <= 0:
            return 0.0
        return min(1.0, self.used_tokens() / self.limit_tokens)

    def status_line(self) -> str:
        used = self.used_tokens()
        lim = self.limit_tokens
        pct = int(self.usage_ratio() * 100)
        return f"ctx {used}/{lim} ({pct}%) · {len(self.messages)} msgs"

    def add(self, role: str, content: str) -> Message:
        msg = Message(role=role, content=content)
        self.messages.append(msg)
        return msg

    def clear(self, keep_system: bool = True) -> None:
        if keep_system and self.messages and self.messages[0].role == "system":
            sys_msg = self.messages[0]
            self.messages = [sys_msg]
        else:
            self.messages = []
            self.messages.append(Message(role="system", content=self.system_prompt))

    def as_chat_messages(self) -> list[dict[str, str]]:
        """OpenAI-style messages for the chat role (skip pure system-notes)."""
        out: list[dict[str, str]] = []
        for m in self.messages:
            if m.role == "system-note":
                # Fold notes into system channel so the model still sees them
                out.append({"role": "system", "content": m.content})
            elif m.role in ("system", "user", "assistant"):
                out.append({"role": m.role, "content": m.content})
        return out

    def recent_turns(
        self,
        n: int = 4,
        *,
        max_chars_each: int = 600,
    ) -> list[dict[str, str]]:
        """Last *n* user/assistant turns only (for slim graph-augmented chat).

        Excludes the system prompt and does not include the current pending
        user message if the caller already holds it separately.
        """
        turns = [
            m
            for m in self.messages
            if m.role in ("user", "assistant")
        ]
        # Drop the last user message if we're about to re-send the question
        # with a graph block (caller usually passes question separately).
        selected = turns[-n:] if n > 0 else []
        out: list[dict[str, str]] = []
        for m in selected:
            content = m.content
            if len(content) > max_chars_each:
                content = content[: max_chars_each - 1] + "…"
            out.append({"role": m.role, "content": content})
        return out

    def maybe_autocompact(self, threshold: float = 0.55) -> Optional[str]:
        """Auto-run local compact when usage exceeds *threshold*."""
        if self.usage_ratio() >= threshold:
            return self.compact_local()
        return None

    def needs_compact(self, threshold: float = 0.85) -> bool:
        return self.usage_ratio() >= threshold

    def compact_local(self) -> str:
        """Drop middle turns, keep system + recent messages (no LLM).

        Returns a human-readable summary of what was done.
        """
        if len(self.messages) <= self.keep_recent + 1:
            return "Nothing to compact — session already short."

        system = [m for m in self.messages if m.role == "system"][:1]
        rest = [m for m in self.messages if m not in system]
        if len(rest) <= self.keep_recent:
            return "Nothing to compact — session already short."

        dropped = rest[: -self.keep_recent]
        recent = rest[-self.keep_recent :]
        drop_tokens = sum(m.tokens() for m in dropped)
        n_drop = len(dropped)

        stub = (
            f"[compacted {n_drop} earlier messages ≈{drop_tokens} tokens] "
            "Earlier turns were summarized away to free context. "
            "Recent conversation continues below."
        )
        note = Message(role="system-note", content=stub)
        self.messages = system + [note] + recent
        return (
            f"Compacted: dropped {n_drop} messages (~{drop_tokens} tokens). "
            f"Now {self.used_tokens()}/{self.limit_tokens}."
        )

    def compact_with_llm(
        self,
        llm_call: Callable[[list[dict[str, str]]], str],
    ) -> str:
        """Summarize older turns via LLM, keep recent messages intact."""
        if len(self.messages) <= self.keep_recent + 1:
            return "Nothing to compact — session already short."

        system = [m for m in self.messages if m.role == "system"][:1]
        rest = [m for m in self.messages if m not in system]
        if len(rest) <= self.keep_recent:
            return "Nothing to compact — session already short."

        older = rest[: -self.keep_recent]
        recent = rest[-self.keep_recent :]
        blob = "\n\n".join(f"{m.role.upper()}: {m.content}" for m in older)

        prompt = [
            {
                "role": "system",
                "content": (
                    "Summarize the following conversation turns into a dense "
                    "bullet brief for an AI assistant. Preserve decisions, "
                    "file paths, errors, and user goals. Max 400 words. "
                    "No fluff."
                ),
            },
            {"role": "user", "content": blob[:120000]},
        ]
        try:
            summary = llm_call(prompt).strip()
        except Exception as exc:
            logger.warning("LLM compact failed, falling back to local: %s", exc)
            return self.compact_local() + f" (LLM compact failed: {exc})"

        note = Message(
            role="system-note",
            content=f"[conversation summary]\n{summary}",
        )
        before = self.used_tokens()
        self.messages = system + [note] + recent
        after = self.used_tokens()
        return (
            f"Compacted via LLM: {before} → {after} tokens "
            f"(limit {self.limit_tokens}). Kept last {len(recent)} messages."
        )
