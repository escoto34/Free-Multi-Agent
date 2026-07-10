"""Unit tests for agent_runtime, run history, entry schemas, and YAML helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from core.agent_config import get_max_fix_cycles, reload_config
from core.agent_runtime import strip_fences
from core.runs import RunHistory
from core.search_guards import extract_urls, find_no_live_search_marker
from schemas.requests import DeepResearchRequest, VibeCodingRequest


def test_strip_fences_removes_markdown_wrapper():
    raw = '```json\n{"a": 1}\n```'
    assert strip_fences(raw) == '{"a": 1}'


def test_strip_fences_plain_json_unchanged():
    assert strip_fences('{"a": 1}') == '{"a": 1}'


def test_vibe_coding_request_rejects_too_short():
    with pytest.raises(ValidationError):
        VibeCodingRequest(idea="ab")


def test_deep_research_request_accepts_topic():
    req = DeepResearchRequest(topic="Quantum computing trends 2026")
    assert "Quantum" in req.topic


def test_max_fix_cycles_from_yaml():
    reload_config()
    n = get_max_fix_cycles()
    assert isinstance(n, int)
    assert n >= 1


def test_run_history_start_finish_list(tmp_path: Path):
    hist = RunHistory(db_path=tmp_path / "runs.db")
    rid = hist.start("vibe_coding", "build a todo API")
    hist.finish(rid, status="success", result_summary="ok", meta={"passed": True})
    rows = hist.list_recent(limit=5)
    assert len(rows) == 1
    assert rows[0]["id"] == rid
    assert rows[0]["status"] == "success"
    assert rows[0]["meta"]["passed"] is True


def test_no_live_search_marker_shared():
    assert find_no_live_search_marker("hello world") is None
    assert find_no_live_search_marker(
        "Note: no live web-search was performed."
    ) is not None


def test_extract_urls_dedupes():
    text = "See https://a.com/x and https://a.com/x again https://b.com"
    urls = extract_urls(text)
    assert urls == ["https://a.com/x", "https://b.com"]
