"""
Reusable Textual widgets and utilities for performance optimizations.

- ``ProgressStatus`` — a single ``Static`` line that is *updated in-place*
  (``.update()``) instead of mounting new ``Markdown`` widgets on every
  progress message.  Prevents DOM bloat and keeps TUI responsive at 60 FPS.

- ``ThrottledProgress`` — rate-limits progress callbacks so rapid streams
  of messages (LLM streaming, Celery polling) never queue more than N
  updates per second.  Used in worker threads via ``call_from_thread``.
"""

from __future__ import annotations

import asyncio
import time
from typing import Callable, Optional

from textual.widgets import Static

_DEFAULT_THROTTLE = 0.3  # seconds between UI updates


class ProgressStatus(Static):
    """Single-line status widget that updates in-place.

    Intended for a dedicated progress bar area below the chat stream but
    above the prompt input.  Each call to ``set_progress`` replaces the
    previous text — no new widgets are mounted.
    """

    DEFAULT_CSS = """
    ProgressStatus {
        height: 1;
        width: 100%;
        padding: 0 1;
        color: $text-muted;
        background: $surface;
        border-bottom: solid $foreground 10%;
        text-overflow: ellipsis;
    }
    """

    def set_progress(self, msg: str) -> None:
        self.update(f"  {msg}")


class ThrottledProgress:
    """Rate-limited progress callback.

    Defers rapid repeated messages to at most one UI update every
    ``min_interval`` seconds.  The latest message always wins.
    """

    def __init__(self, callback: Callable[[str], None], min_interval: float = _DEFAULT_THROTTLE) -> None:
        self._callback = callback
        self._interval = min_interval
        self._last = 0.0
        self._pending: Optional[str] = None

    def __call__(self, msg: str) -> None:
        now = time.monotonic()
        if now - self._last >= self._interval:
            self._last = now
            self._pending = None
            self._callback(msg)
        else:
            self._pending = msg

    async def flush(self) -> None:
        """Send the last deferred message (if any)."""
        if self._pending is not None:
            self._callback(self._pending)
            self._pending = None
            self._last = time.monotonic()
        await asyncio.sleep(0)