"""
Optional Lightpanda (Zig headless browser) rendering.

**Integration decision (WAVE-12): shell out to the ``lightpanda`` binary**
rather than speaking CDP over a websocket. Python has no stdlib websocket
client, so a CDP-over-ws path would force a new third-party dependency
(prohibited); shelling out requires none and surfaces cleanly as an opt-in flag.

This module is a **no-op by default**: it proactively probes for the binary
once (cached for the process lifetime) and returns ``None`` for every request
when absent. Callers then fall back to their existing plain-HTML path, so a
user who never installs Lightpanda gets byte-identical behavior — never an
exception, never a hang, exactly one log line.

Returns raw rendered *markup* (not text) so the caller reuses its own HTML→text
extractor and keeps signals/outbound extraction identical.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

_UNSET = object()
_bin_cache: object = _UNSET


def lightpanda_bin() -> Optional[str]:
    """Locate the binary once (env override or PATH); cache for process life."""
    global _bin_cache
    if _bin_cache is not _UNSET:
        return _bin_cache  # type: ignore[return-value]
    path = os.environ.get("LIGHTPANDA_BIN") or shutil.which("lightpanda")
    _bin_cache = path or None
    if _bin_cache is None:
        logger.info("Lightpanda not found (LIGHTPANDA_BIN / PATH); rendering off")
    return _bin_cache  # type: ignore[return-value]


def lightpanda_available() -> bool:
    """True if the renderer binary resolves (cached for the process lifetime)."""
    return lightpanda_bin() is not None


def render_html(url: str, *, timeout: float = 45.0) -> Optional[str]:
    """Render *url* and return the rendered DOM markup.

    Returns:
        - ``None`` when Lightpanda is unavailable or the render itself failed —
          the caller must degrade to plain-HTML fetching.
        - The rendered markup string on success — which may be empty (a shell
          that never populated its DOM). Callers distinguish this ``""`` from
          ``None`` as "rendered but empty".
    """
    if not url or not url.startswith(("http://", "https://")):
        return None
    bin_path = _bin_cache if _bin_cache is not _UNSET else lightpanda_bin()
    if bin_path is None:
        return None
    try:
        proc = subprocess.run(
            [bin_path, "--dump-dom", url],
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Lightpanda render failed for %s: %s", url, exc)
        return None
    if proc.returncode != 0:
        logger.warning(
            "Lightpanda exited rc=%s for %s: %s",
            proc.returncode,
            url,
            (proc.stderr or b"").decode("utf-8", errors="replace")[:300],
        )
        return None
    try:
        return proc.stdout.decode("utf-8", errors="replace")
    except Exception:
        return None