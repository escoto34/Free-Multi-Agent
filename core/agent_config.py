"""
Central loader for per-agent provider/model assignments.

``config/model_router.yaml`` is meant to be the single source of truth for
which provider/model each agent role uses. Previously each agent file
hardcoded its own provider/model directly in Python, which meant editing
the YAML had no actual effect — this module closes that gap.

Usage::

    from core.agent_config import get_agent_config

    cfg = get_agent_config("deep_research", "context_compressor")
    # {"provider": "openrouter", "model": "tencent/hy3:free",
    #  "free_until": "2026-07-21",
    #  "fallback": {"provider": "groq", "model": "openai/gpt-oss-120b"}}

    resp = call_agent(provider=cfg["provider"], model=cfg["model"], ...)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "model_router.yaml"

_cache: Optional[dict] = None


def _load(config_path: Optional[Path] = None) -> dict:
    """Load (and cache) the full YAML config.

    A custom ``config_path`` bypasses the cache — mainly useful for tests
    that want to point at a fixture file instead of the real config.
    """
    global _cache
    if config_path is not None:
        with open(config_path) as fh:
            return yaml.safe_load(fh)
    if _cache is None:
        with open(_CONFIG_PATH) as fh:
            _cache = yaml.safe_load(fh)
    return _cache


def reload_config() -> None:
    """Force the next ``get_agent_config`` call to re-read the YAML from disk.

    Useful in tests, or if the config file is edited while the process is
    running (e.g. a long-lived server) and you want the change picked up
    without a restart.
    """
    global _cache
    _cache = None


def get_full_config(config_path: Optional[Path] = None) -> dict[str, Any]:
    """Return the entire cached ``model_router.yaml`` document."""
    return _load(config_path)


def get_agent_config(*path: str, config_path: Optional[Path] = None) -> dict[str, Any]:
    """Fetch a nested agent role config by dot-path.

    Example::

        get_agent_config("vibe_coding", "debugger")
        # {"provider": "openrouter", "model": "tencent/hy3:free",
        #  "free_until": "2026-07-21",
        #  "fallback": {"provider": "groq", "model": "openai/gpt-oss-120b"}}

    Raises:
        KeyError: if any segment of the path doesn't exist in the YAML —
            fails loudly rather than silently falling back to a hardcoded
            default, so a typo or a renamed YAML key is caught immediately
            instead of quietly using the wrong model.
    """
    node: Any = _load(config_path)
    for key in path:
        try:
            node = node[key]
        except (KeyError, TypeError) as exc:
            raise KeyError(
                f"model_router.yaml: no se encontró la ruta "
                f"{'.'.join(path)!r} (falló en {key!r}). "
                f"Revisa config/model_router.yaml."
            ) from exc
    return node


def get_max_fix_cycles(config_path: Optional[Path] = None) -> int:
    """Return System A max debugger fix cycles from YAML (default 3)."""
    try:
        vc = get_agent_config("vibe_coding", config_path=config_path)
    except KeyError:
        return 3
    raw = vc.get("max_fix_cycles", 3)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return 3
    return max(1, n)
