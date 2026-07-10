"""
Safe API-key helpers for the interactive CLI.

Writes only to the project ``.env`` file. Never logs or returns full key
values — only masked previews and boolean status.

Provider → env var mapping is driven by ``config/model_router.yaml``
(providers.*.env_key) plus built-in defaults in ``core.clients``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).parent.parent
_ENV_PATH = _ROOT / ".env"

# Static fallbacks (used before clients can import / if YAML missing).
_BUILTIN_ENV: dict[str, str] = {
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "cohere": "COHERE_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "cerebras": "CEREBRAS_API_KEY",
}

_KEY_LINE = re.compile(
    r"^(?P<name>[A-Z0-9_]+)=(?P<val>.*)$",
    re.MULTILINE,
)


def env_path() -> Path:
    return _ENV_PATH


def provider_env_map() -> dict[str, str]:
    """Alias → env var for every known free-tier provider."""
    out = dict(_BUILTIN_ENV)
    try:
        from core.clients import list_provider_names, get_provider_meta

        for name in list_provider_names():
            try:
                meta = get_provider_meta(name)
                if meta.get("env_key"):
                    out[name] = meta["env_key"]
            except Exception:
                continue
    except Exception:
        pass
    return out


# Back-compat name used elsewhere
PROVIDER_ENV = _BUILTIN_ENV  # mutated lazily via provider_env_map in callers


def mask_key(value: str) -> str:
    """Return a safe display form (last 4 chars only if long enough)."""
    v = (value or "").strip()
    if not v or "your_" in v or v.endswith("_here"):
        return "(not set)"
    if len(v) <= 8:
        return "****"
    return f"…{v[-4:]}"


def _is_placeholder(value: str) -> bool:
    v = (value or "").strip()
    if not v:
        return True
    return "your_" in v or v.endswith("_here") or v == "changeme"


def get_key_status(env_file: Optional[Path] = None) -> list[dict[str, str]]:
    """Status of each provider key (never includes raw secret)."""
    path = env_file or _ENV_PATH
    file_vals = _parse_env_file(path) if path.exists() else {}
    rows: list[dict[str, str]] = []
    for alias, env_name in sorted(provider_env_map().items()):
        raw = os.environ.get(env_name) or file_vals.get(env_name, "")
        set_ok = not _is_placeholder(raw)
        rows.append(
            {
                "provider": alias,
                "env": env_name,
                "status": "set" if set_ok else "missing",
                "preview": mask_key(raw) if set_ok else "(not set)",
            }
        )
    return rows


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = _KEY_LINE.match(s)
        if not m:
            continue
        out[m.group("name")] = m.group("val").strip().strip('"').strip("'")
    return out


def set_api_key(
    provider: str,
    api_key: str,
    *,
    env_file: Optional[Path] = None,
) -> str:
    """Write/update a provider API key in ``.env`` and process env.

    Returns masked preview. Raises ValueError on bad input.
    """
    alias = provider.strip().lower()
    env_map = provider_env_map()
    if alias not in env_map:
        raise ValueError(
            f"Unknown provider {provider!r}. Valid: {sorted(env_map)}"
        )
    key = api_key.strip()
    if not key or _is_placeholder(key):
        raise ValueError("API key looks empty or like a placeholder")

    env_name = env_map[alias]
    path = env_file or _ENV_PATH
    _upsert_env_var(path, env_name, key)
    os.environ[env_name] = key

    try:
        from core.clients import clear_client_cache

        clear_client_cache()
    except Exception:
        pass

    return mask_key(key)


def _upsert_env_var(path: Path, name: str, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    else:
        example = path.parent / ".env.example"
        lines = (
            example.read_text(encoding="utf-8").splitlines()
            if example.exists()
            else []
        )

    found = False
    new_lines: list[str] = []
    pattern = re.compile(rf"^{re.escape(name)}=")
    for line in lines:
        if pattern.match(line.strip()):
            new_lines.append(f"{name}={value}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        new_lines.append(f"{name}={value}")

    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
