"""
Centralized icon registry with automatic ASCII fallback for limited terminals.

Detection logic
~~~~~~~~~~~~~~~
* If ``sys.platform == "win32"`` the module conservatively assumes
  no UTF-8 / Nerd Font availability and returns the ASCII equivalents.
* On macOS / Linux it reads ``LC_ALL`` / ``LC_CTYPE`` / ``LANG`` and
  returns Unicode only if the locale contains ``utf-8``.

Usage
~~~~~
.. code-block:: python

    from cli_app.icons import get_icon, strip_icons

    get_icon("ok")          # → "✔" (or "[OK]" on Windows CMD)
    get_icon("arrow")       # → "→" (or "->" on Windows CMD)
    strip_icons(some_text)  # Replace every icon with its ASCII equivalent
"""

from __future__ import annotations

import os
import sys
import re

_IS_WINDOWS = sys.platform == "win32"
_CACHE: dict[str, bool] = {"utf8": None}


def _utf8_capable() -> bool:
    """Return True when the current terminal can display Unicode glyphs."""
    if _CACHE["utf8"] is not None:
        return _CACHE["utf8"]
    if _IS_WINDOWS:
        _CACHE["utf8"] = False
        return False
    try:
        locale = (
            os.environ.get("LC_ALL", "")
            or os.environ.get("LC_CTYPE", "")
            or os.environ.get("LANG", "")
        )
        _CACHE["utf8"] = bool(re.search(r"utf-?8", locale, re.I))
    except Exception:
        _CACHE["utf8"] = True
    return _CACHE["utf8"]


_ICONS: dict[str, tuple[str, str]] = {
    "ok": ("✔", "[OK]"),
    "fail": ("✘", "[FAIL]"),
    "error": ("✘", "[ERROR]"),
    "warning": ("⚠", "[!]"),
    "info": ("ℹ", "[i]"),
    "question": ("?", "[?]"),
    "bullet": ("•", "*"),
    "arrow": ("→", "->"),
    "arrow_right": ("→", "->"),
    "arrow_left": ("←", "<-"),
    "arrow_up": ("↑", "^"),
    "arrow_down": ("↓", "v"),
    "ellipsis": ("…", "..."),
    "check": ("✓", "[x]"),
    "cross": ("✗", "[ ]"),
    "star": ("★", "*"),
    "heart": ("♥", "<3"),
    "key": ("🔑", "(key)"),
    "lock": ("🔒", "(locked)"),
    "clock": ("⏱", "(time)"),
    "search": ("🔎", "[?]"),
    "link": ("🔗", "(link)"),
    "globe": ("🌐", "(web)"),
    "folder": ("📁", "(dir)"),
    "file": ("📄", "(file)"),
    "user": ("👤", "(user)"),
    "robot": ("🤖", "(bot)"),
    "speech": ("💬", "(msg)"),
    "lightbulb": ("💡", "(idea)"),
    "fire": ("🔥", "(hot)"),
    "gear": ("⚙", "[*]"),
    "pipeline": ("⚙", "[*]"),
    "planner": ("📋", "[P]"),
    "research": ("🔍", "[R]"),
    "vibe": ("🎨", "[V]"),
    "code": ("💻", "[C]"),
    "brain": ("🧠", "[B]"),
    "calendar": ("📅", "(date)"),
    "task_pending": ("⏳", "[.]"),
    "task_running": ("🔄", "[~]"),
    "task_success": ("✅", "[OK]"),
    "task_failure": ("❌", "[FAIL]"),
    "task_retry": ("🔁", "[RETRY]"),
    "clipboard": ("📋", "[_]"),
    "edit": ("✎", "(edit)"),
    "trash": ("🗑", "(del)"),
    "flag": ("⚑", "(flag)"),
    "bullet": ("▸", ">"),
    "windows": ("⊞", "[WIN]"),
}


def get_icon(name: str) -> str:
    """Return the icon for *name* or its ASCII fallback.

    Parameters
    ----------
    name:
        Key present in the internal registry.  Unknown names fall back
        to ``[name]``.
    """
    entry = _ICONS.get(name)
    if entry is None:
        return f"[{name}]"
    if _IS_WINDOWS or not _utf8_capable():
        return entry[1]
    return entry[0]


def strip_icons(text: str) -> str:
    """Replace every known Unicode icon in *text* with its ASCII equivalent."""
    for _, (uni, asc) in _ICONS.items():
        text = text.replace(uni, asc)
    return text
