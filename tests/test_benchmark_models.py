"""WAVE-20: scripts/benchmark_models.py smoke tests — no live network.

Covers the mandatory smoke surface: ``--help`` runs, ``--only`` filters the
plan, stack-relative scoring matches the §4.1 rubric, and stream-event text
extraction works for both openai-compat and cohere v2 shapes.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "benchmark_models.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("benchmark_models", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_benchmark_cli_help():
    res = subprocess.run(
        [sys.executable, str(_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert res.returncode == 0
    assert "usage" in (res.stdout + res.stderr).lower()


def test_dry_run_plans_without_network():
    mod = _load_module()
    rc = mod.main(["--only", "groq"])
    assert rc == 0
    # No network was touched (no client import in dry-run); plan mentions groq keys.


def test_only_filters_targets_to_providers():
    mod = _load_module()
    targets = mod._targets(only=["groq", "cohere"])
    assert targets
    assert all(t[0] in {"groq", "cohere"} for t in targets)
    assert any(t[0] == "cohere" for t in targets)


def test_targets_exclude_embedding_models():
    mod = _load_module()
    assert all("embed" not in t[1].lower() for t in mod._targets())


def test_stack_scores_match_rubric():
    mod = _load_module()
    measured = {
        "fast": {"tokens_per_sec": 200.0, "first_token_ms": 10.0, "context_window": 16000},
        "slow": {"tokens_per_sec": 50.0, "first_token_ms": 400.0, "context_window": 16000},
        "tiny": {"tokens_per_sec": 50.0, "first_token_ms": 50.0, "context_window": 4000},
    }
    scores = mod._stack_scores(measured)
    # speed is linear against the stack max (200 tps -> 100)
    assert scores["fast"]["speed_score"] == 100.0
    assert scores["slow"]["speed_score"] == 25.0
    # same context window -> identical context_score, lower speed for "slow"
    assert scores["fast"]["context_score"] == scores["slow"]["context_score"] == 100.0
    # max tps*ctx is fast; slow has 1/4 of the capacity throughput
    assert scores["slow"]["capacity_score"] == 25.0
    # tiny ctx (4000) vs max (16000): log-ratio ~ 100*log(4001)/log(16001)
    assert 0 < scores["tiny"]["context_score"] < 100


def test_delta_text_openai_compat():
    mod = _load_module()
    chunk = SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=" hello "))])
    assert mod._delta_text(chunk, "groq") == " hello "
    empty = SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None))])
    assert mod._delta_text(empty, "groq") == ""
    assert mod._delta_text(SimpleNamespace(choices=[]), "groq") == ""


def test_delta_text_cohere_v2():
    mod = _load_module()
    event = SimpleNamespace(
        delta=SimpleNamespace(message=SimpleNamespace(content=SimpleNamespace(text=" world")))
    )
    assert mod._delta_text(event, "cohere") == " world"
    # v7 deltas carry thinking + text; both count as streamed tokens.
    thinking = SimpleNamespace(
        delta=SimpleNamespace(
            message=SimpleNamespace(
                content=SimpleNamespace(text=None, thinking="The user wants ")
            )
        )
    )
    assert mod._delta_text(thinking, "cohere") == "The user wants "
    noop = SimpleNamespace(delta=None)
    assert mod._delta_text(noop, "cohere") == ""


def test_delta_text_counts_reasoning_content():
    mod = _load_module()
    chunk = SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=None, reasoning_content="think"))]
    )
    assert mod._delta_text(chunk, "groq") == "think"


def test_fetch_context_windows_openai_compat(monkeypatch):
    mod = _load_module()
    seen = {}

    def fake_get(url, bearer=None, **kwargs):
        seen["url"] = url
        assert url == "https://api.groq.com/openai/v1/models"
        return {"data": [{"id": "openai/gpt-oss-120b", "context_window": 131072}]}

    monkeypatch.setattr(mod, "_http_get_json", fake_get)
    ctx = mod._fetch_context_windows("groq", {"base_url": "https://api.groq.com/openai/v1"})
    assert ctx == {"openai/gpt-oss-120b": 131072}
    assert "/models" in seen["url"]


def test_fetch_context_windows_cohere_v2_then_v1(monkeypatch):
    mod = _load_module()
    calls = []

    def fake_get(url, bearer=None, **kwargs):
        calls.append(url)
        return {
            "models": [{"name": "command-a-plus-05-2026", "context_length": 256000}]
        }

    monkeypatch.setattr(mod, "_http_get_json", fake_get)
    ctx = mod._fetch_context_windows("cohere", {"base_url": None})
    assert ctx.get("command-a-plus-05-2026") == 256000
    assert any("/v2/models" in u for u in calls)