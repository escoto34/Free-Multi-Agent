"""
Language helpers for chat + pipelines.

- Chat answers in the user's language (prompt-level instruction).
- Systems A/B receive English prompts (translate when needed).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Lightweight heuristic: common non-English signals (esp. Spanish/French/etc.)
_NON_EN_CHARS = re.compile(
    r"[áéíóúñü¿¡àâäæçèêëìîïòôœùûüßА-Яа-я\u4e00-\u9fff\u3040-\u30ff\u0600-\u06ff]",
    re.I,
)
_NON_EN_WORDS = re.compile(
    r"\b("
    r"el|la|los|las|de|del|que|por|para|con|una|uno|como|más|mas|también|"
    r"también|está|esta|esto|eso|aquí|alli|allí|hacer|quiero|puedes|gracias|"
    r"le|les|des|une|est|dans|pour|avec|sur|pas|plus|être|avoir|"
    r"der|die|das|und|nicht|mit|ich|sie|ein|eine|"
    r"o|a|os|as|não|nao|sim|com|para|por|uma"
    r")\b",
    re.I,
)


def looks_non_english(text: str) -> bool:
    """Cheap check — not a full language detector."""
    t = (text or "").strip()
    if not t:
        return False
    if _NON_EN_CHARS.search(t):
        return True
    # Word markers only count when several appear (avoid "el" false positives alone)
    hits = _NON_EN_WORDS.findall(t)
    return len(hits) >= 3


def chat_language_instruction() -> str:
    return (
        "Language: always reply in the **same language** the user is writing in "
        "(Spanish → Spanish, English → English, etc.). "
        "Do not switch language unless the user explicitly asks."
    )


def to_english_for_pipelines(
    text: str,
    *,
    invoke_fn: Optional[Any] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    fallback: Optional[dict] = None,
) -> str:
    """Return English text suitable for Systems A/B.

    If the text already looks English, return it unchanged. Otherwise ask the
    chat model to translate (when *invoke_fn* is provided).
    """
    raw = (text or "").strip()
    if not raw:
        return raw
    if not looks_non_english(raw):
        return raw

    if invoke_fn is None or not provider or not model:
        # No LLM available — return original (pipelines still get the text)
        logger.debug("to_english: non-English text but no LLM; passing through")
        return raw

    messages = [
        {
            "role": "system",
            "content": (
                "You translate user tasks into clear technical English for "
                "coding/research pipelines. "
                "If the input is already English, return it unchanged. "
                "Output ONLY the English text — no quotes, no preamble."
            ),
        },
        {"role": "user", "content": raw[:8000]},
    ]
    try:
        resp = invoke_fn(
            None,
            provider=provider,
            model=model,
            messages=messages,
            fallback=fallback,
        )
        out = (getattr(resp, "content", None) or str(resp) or "").strip()
        return out or raw
    except Exception as exc:
        logger.warning("to_english translation failed: %s", exc)
        return raw
