"""
Console environment setup: UTF-8 encoding + ANSI/VT100 for Windows.

Call ``ensure_utf8_and_ansi()`` at the earliest possible moment —
before any ``click.secho`` or ``Textual.run()`` — so every subsequent
print statement or terminal render uses the correct bytes and escape
sequences on all platforms (Windows CMD / PowerShell / Git Bash /
GitHub Codespaces / macOS / Linux).
"""

from __future__ import annotations

import os
import sys
from typing import Optional

_WIN = sys.platform == "win32"


def _enable_vt100_windows() -> None:
    """Activate ANSI/VT100 escape processing on the native Windows console.
    
    Without this, Windows 10 < 1903 or unconfigured PowerShell / CMD
    treats every ``\x1b[`` sequence as literal bytes and renders them
    as ``?`` inside a rectangle.  The flag combinations we set:
      - ENABLE_VIRTUAL_TERMINAL_PROCESSING (0x0004) — interpret ANSI
      - DISABLE_NEWLINE_AUTO_RETURN            (0x0008) — prevent \r\n duplication
    """
    if not _WIN:
        return
    try:
        kernel32 = ctypes.windll.kernel32  # type: ignore[name-defined]
        STD_OUTPUT_HANDLE = -11
        h = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
        mode = ctypes.c_uint32()  # type: ignore[name-defined]
        kernel32.GetConsoleMode(h, ctypes.byref(mode))  # type: ignore[arg-type]
        mode.value |= 0x0004 | 0x0008
        kernel32.SetConsoleMode(h, mode)  # type: ignore[arg-type]
    except Exception:
        pass  # Not a Windows console (e.g. Git Bash, WSL, CI)


def ensure_utf8_and_ansi() -> None:
    """Force UTF-8 std streams + enable ANSI on Windows console.
    
    Safe to call multiple times.  Idempotent.
    """
    if _WIN:
        _enable_vt100_windows()
    for stream in (sys.stdout, sys.stderr):
        try:
            if (
                hasattr(stream, "reconfigure")
                and stream.encoding
                and stream.encoding.upper() not in ("UTF-8", "UTF8")
            ):
                stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")


# Lazy-import ctypes only when it's actually needed (Windows path)
import ctypes  # noqa: E402  # pylint: disable=wrong-import-position
