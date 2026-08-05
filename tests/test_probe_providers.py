"""WAVE-19: scripts/probe_providers.py smoke tests — no live network.

Covers the mandatory smoke test from mejoras.md WAVE-19: ``--help`` runs,
``diff_catalog`` flags a synthetic gone/live pair, and the HTTP layer is
mocked so no real provider is ever contacted.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "probe_providers.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("probe_providers", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_probe_providers_cli_help():
    res = subprocess.run(
        [sys.executable, str(_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert res.returncode == 0
    assert "usage" in (res.stdout + res.stderr).lower()


def test_diff_catalog_flags_gone_and_live_only():
    mod = _load_module()
    diff = mod.diff_catalog(configured={"a", "b"}, live={"b", "c"})
    assert diff.gone == ["a"]
    assert diff.live_only == ["c"]
    assert diff.matched == ["b"]
    assert diff.clean is False


def test_diff_catalog_clean():
    mod = _load_module()
    assert mod.diff_catalog({"x"}, {"x"}).clean is True


def test_probe_provider_parses_openai_compat_without_network(monkeypatch):
    mod = _load_module()
    seen = {}

    def fake_get(url, headers, **kwargs):
        seen["url"] = url
        seen["auth"] = headers.get("Authorization")
        return {"data": [{"id": "models/normalized"}, {"id": "plain"}, {"id": ""}]}

    monkeypatch.setattr(mod, "_http_get_json", fake_get)
    res = mod.probe_provider(
        "fake",
        {
            "kind": "openai_compatible",
            "base_url": "https://fake.example/v1",
            "env_key": "FAKE_PROBE_KEY",
            "models": ["plain"],
        },
        env={"FAKE_PROBE_KEY": "sk-fake"},
    )
    assert res.ok is True
    assert res.live == {"normalized", "plain"}
    assert seen["url"] == "https://fake.example/v1/models"
    assert seen["auth"] == "Bearer sk-fake"


def test_probe_provider_missing_key_fails_without_network(monkeypatch):
    mod = _load_module()
    monkeypatch.setenv("FAKE_PROBE_KEY", "")
    monkeypatch.setenv("FAKE_PROBE_KEY_2", "")
    res = mod.probe_provider(
        "fake",
        {
            "kind": "openai_compatible",
            "base_url": "https://fake.example/v1",
            "env_key": "FAKE_PROBE_KEY_2",
            "models": [],
        },
    )
    assert res.ok is False
    assert "FAKE_PROBE_KEY_2" in (res.error or "")


def test_probe_cohere_parses_v1_names(monkeypatch):
    mod = _load_module()
    monkeypatch.setenv("COHERE_API_KEY", "sk-fake-cohere")

    def fake_get(url, headers, **kwargs):
        return {"models": [{"name": "command-a-plus-05-2026"}, {"name": "command-r7b-12-2024"}]}

    monkeypatch.setattr(mod, "_http_get_json", fake_get)
    res = mod.probe_provider("cohere", {"kind": "cohere_v2", "env_key": "COHERE_API_KEY"})
    assert res.ok is True
    assert "command-a-plus-05-2026" in res.live
