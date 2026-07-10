"""
Read/write model role assignments in ``config/model_router.yaml``.

Factory defaults live in ``config/defaults_model_router.yaml`` (current System A/B
stack). The interactive CLI and ``/config`` slash commands use this module so
operators can change provider/model per role without editing Python.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Optional

import yaml

from core.agent_config import reload_config

_ROOT = Path(__file__).parent.parent
_LIVE = _ROOT / "config" / "model_router.yaml"
_DEFAULTS = _ROOT / "config" / "defaults_model_router.yaml"

# Roles exposed in the CLI (system, role) — matches current orchestration.
KNOWN_ROLES: list[tuple[str, str]] = [
    ("vibe_coding", "architect"),
    ("vibe_coding", "coder"),
    ("vibe_coding", "debugger"),
    ("deep_research", "safety_filter"),
    ("deep_research", "context_compressor"),
    ("deep_research", "web_search"),
    ("deep_research", "grounding"),
    ("deep_research", "synthesizer"),
    ("cli", "chat"),
    ("cli", "planner"),
]

# Extended by runtime list from model_router.yaml / clients (mistral, gemini, …)
KNOWN_PROVIDERS = (
    "groq",
    "openrouter",
    "cohere",
    "mistral",
    "gemini",
    "cerebras",
)


def known_providers() -> tuple[str, ...]:
    try:
        from core.clients import list_provider_names

        return tuple(list_provider_names())
    except Exception:
        return KNOWN_PROVIDERS


def _read(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid YAML root in {path}")
    return data


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(
            data,
            fh,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )


def ensure_defaults_snapshot() -> None:
    """Create defaults file from live config if missing (first run)."""
    if not _DEFAULTS.exists() and _LIVE.exists():
        shutil.copy2(_LIVE, _DEFAULTS)


def list_roles(config_path: Optional[Path] = None) -> list[dict[str, Any]]:
    """Return flat list of role configs for display."""
    path = config_path or _LIVE
    cfg = _read(path)
    rows: list[dict[str, Any]] = []
    for system, role in KNOWN_ROLES:
        node = (cfg.get(system) or {}).get(role)
        if not isinstance(node, dict):
            rows.append(
                {
                    "id": f"{system}.{role}",
                    "system": system,
                    "role": role,
                    "provider": None,
                    "model": None,
                    "fallback": None,
                    "missing": True,
                }
            )
            continue
        fb = node.get("fallback")
        rows.append(
            {
                "id": f"{system}.{role}",
                "system": system,
                "role": role,
                "provider": node.get("provider"),
                "model": node.get("model"),
                "fallback": (
                    f"{fb.get('provider')}/{fb.get('model')}"
                    if isinstance(fb, dict)
                    else None
                ),
                "free_until": node.get("free_until"),
                "missing": False,
            }
        )
    # Scalar orchestration knobs
    vc = cfg.get("vibe_coding") or {}
    if "max_fix_cycles" in vc:
        rows.append(
            {
                "id": "vibe_coding.max_fix_cycles",
                "system": "vibe_coding",
                "role": "max_fix_cycles",
                "provider": None,
                "model": str(vc.get("max_fix_cycles")),
                "fallback": None,
                "missing": False,
                "scalar": True,
            }
        )
    return rows


def set_role(
    system: str,
    role: str,
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    fallback_provider: Optional[str] = None,
    fallback_model: Optional[str] = None,
    clear_fallback: bool = False,
    config_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Update a role's provider/model/fallback and persist YAML.

    Returns the updated role node.
    """
    path = config_path or _LIVE
    if (system, role) not in KNOWN_ROLES and role != "max_fix_cycles":
        raise KeyError(
            f"Unknown role {system}.{role}. Known: "
            + ", ".join(f"{s}.{r}" for s, r in KNOWN_ROLES)
        )

    cfg = _read(path)
    section = cfg.setdefault(system, {})
    if not isinstance(section, dict):
        raise ValueError(f"{system} is not a mapping in YAML")

    if role == "max_fix_cycles":
        if model is None:
            raise ValueError("max_fix_cycles requires a numeric value in model=")
        section["max_fix_cycles"] = int(model)
        _write(path, cfg)
        reload_config()
        return {"max_fix_cycles": section["max_fix_cycles"]}

    node = section.setdefault(role, {})
    if not isinstance(node, dict):
        node = {}
        section[role] = node

    if provider is not None:
        valid = known_providers()
        if provider not in valid:
            raise ValueError(
                f"Unknown provider {provider!r}. Valid: {valid}"
            )
        node["provider"] = provider
    if model is not None:
        node["model"] = model

    if clear_fallback:
        node.pop("fallback", None)
    elif fallback_provider is not None or fallback_model is not None:
        fb = dict(node.get("fallback") or {})
        if fallback_provider is not None:
            valid = known_providers()
            if fallback_provider not in valid:
                raise ValueError(
                    f"Unknown fallback provider {fallback_provider!r}. "
                    f"Valid: {valid}"
                )
            fb["provider"] = fallback_provider
        if fallback_model is not None:
            fb["model"] = fallback_model
        if "provider" not in fb or "model" not in fb:
            raise ValueError("fallback requires both provider and model")
        node["fallback"] = fb

    if "provider" not in node or "model" not in node:
        raise ValueError("role must have both provider and model after update")

    _write(path, cfg)
    reload_config()
    return dict(node)


def reset_to_defaults(
    *,
    config_path: Optional[Path] = None,
    defaults_path: Optional[Path] = None,
) -> None:
    """Overwrite live model_router.yaml with factory defaults (System A/B stack)."""
    ensure_defaults_snapshot()
    live = config_path or _LIVE
    defaults = defaults_path or _DEFAULTS
    if not defaults.exists():
        raise FileNotFoundError(
            f"Defaults file missing: {defaults}. Cannot reset."
        )
    shutil.copy2(defaults, live)
    reload_config()


def reset_role_to_default(
    system: str,
    role: str,
    *,
    config_path: Optional[Path] = None,
    defaults_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Restore a single role from factory defaults (``defaults_model_router.yaml``).

    Returns the restored role node.
    """
    ensure_defaults_snapshot()
    live_path = config_path or _LIVE
    defaults_path = defaults_path or _DEFAULTS
    if not defaults_path.exists():
        raise FileNotFoundError(f"Defaults file missing: {defaults_path}")
    if (system, role) not in KNOWN_ROLES and role != "max_fix_cycles":
        raise KeyError(
            f"Unknown role {system}.{role}. Known: "
            + ", ".join(f"{s}.{r}" for s, r in KNOWN_ROLES)
        )

    defaults = _read(defaults_path)
    live = _read(live_path)
    src_section = defaults.get(system) or {}
    if role == "max_fix_cycles":
        if "max_fix_cycles" not in src_section:
            raise KeyError(f"No default for {system}.max_fix_cycles")
        live.setdefault(system, {})["max_fix_cycles"] = src_section["max_fix_cycles"]
        _write(live_path, live)
        reload_config()
        return {"max_fix_cycles": src_section["max_fix_cycles"]}

    src_node = src_section.get(role)
    if not isinstance(src_node, dict):
        raise KeyError(f"No default for {system}.{role}")
    # Deep-ish copy of the role dict (provider/model/fallback/free_until)
    import copy

    restored = copy.deepcopy(src_node)
    live.setdefault(system, {})[role] = restored
    _write(live_path, live)
    reload_config()
    return dict(restored)


def get_cli_settings(config_path: Optional[Path] = None) -> dict[str, Any]:
    """Return ``cli`` section with safe defaults."""
    cfg = _read(config_path or _LIVE)
    cli = cfg.get("cli") or {}
    chat = cli.get("chat") or {
        "provider": "groq",
        "model": "openai/gpt-oss-120b",
    }
    use_g = cli.get("use_graphify")
    if use_g is None:
        use_g = True
    return {
        "chat": chat,
        "context_limit_tokens": int(cli.get("context_limit_tokens") or 16000),
        "compact_keep_recent_messages": int(
            cli.get("compact_keep_recent_messages") or 4
        ),
        "compact_target_ratio": float(cli.get("compact_target_ratio") or 0.45),
        # Graph-backed chat: inject a budgeted graphify query each turn
        # instead of shipping the full conversation + codebase into the model.
        "use_graphify": bool(use_g),
        "graphify_budget": int(cli.get("graphify_budget") or 1200),
        "chat_recent_messages": int(cli.get("chat_recent_messages") or 4),
        "store_reply_max_chars": int(cli.get("store_reply_max_chars") or 1200),
    }


def set_context_limit(limit: int, config_path: Optional[Path] = None) -> None:
    """Persist a new interactive context limit."""
    if limit < 1000:
        raise ValueError("context limit must be >= 1000 tokens")
    path = config_path or _LIVE
    cfg = _read(path)
    cli = cfg.setdefault("cli", {})
    cli["context_limit_tokens"] = int(limit)
    _write(path, cfg)
    reload_config()
