"""WAVE-15 tests: concurrent execution of independent plan steps.

Covers the concurrency decision's correctness (independent steps run in
parallel, dependent steps stay sequential and ordered) and the acceptance-critical
WAVE-07 ledger guarantee (parallel steps making parallel LLM calls never
over-commit a shared provider quota). Everything is deterministic via mocked
`_run_research`/`_run_vibe`.
"""

from __future__ import annotations

import threading
import time

from cli_app.orchestrate import execute_plan, _run_step
from schemas.requests import PipelinePlan, PipelineStep


def _ok_research(prompt: str, *_a, **_k):
    return {
        "content": prompt,
        "sources": ["http://src.test"],
        "is_safe": True,
        "error": None,
    }


def _ok_vibe(prompt: str, *_a, **_k):
    return {
        "passed": True,
        "fix_attempts": 1,
        "files_written": [{"path": "x.py", "lines": 2}],
        "summary": prompt[:20],
        "error": None,
    }


def test_independent_steps_run_concurrently(monkeypatch):
    """A batch of independent (uses_prior=False) steps overlaps in time."""
    lock = threading.Lock()
    cur = 0
    maxc = 0

    def fake_vibe(prompt, *_a, **_k):
        nonlocal cur, maxc
        with lock:
            cur += 1
            maxc = max(maxc, cur)
        time.sleep(0.05)
        with lock:
            cur -= 1
        return _ok_vibe(prompt)

    monkeypatch.setattr("cli_app.orchestrate._run_vibe", fake_vibe)
    plan = PipelinePlan(
        summary="parallel",
        steps=[
            PipelineStep(action="vibe", prompt=f"task{i}", uses_prior=False)
            for i in range(3)
        ],
    )
    res = execute_plan(plan)
    assert res["ok"] is True
    assert maxc >= 2  # overlapped, not one-at-a-time
    assert [s["index"] for s in res["steps"]] == [1, 2, 3]


def test_mixed_plan_matches_sequential_reference(monkeypatch):
    """Concurrent execution yields identical results to the sequential loop."""
    monkeypatch.setattr("cli_app.orchestrate._run_research", _step_research := _ok_research)
    monkeypatch.setattr("cli_app.orchestrate._run_vibe", _ok_vibe)
    plan = PipelinePlan(
        summary="mixed",
        steps=[
            PipelineStep(action="research", prompt="research one", uses_prior=False),
            PipelineStep(action="vibe", prompt="vibe step two", uses_prior=True),
            PipelineStep(action="vibe", prompt="vibe step three", uses_prior=False),
            PipelineStep(action="research", prompt="research four", uses_prior=True),
        ],
    )

    par = execute_plan(plan)

    # Sequential reference that mirrors the pre-WAVE-15 loop exactly.
    prior_blobs: list[str] = []
    seq_results = []
    for i, st in enumerate(plan.steps, 1):
        pc = "\n\n".join(prior_blobs[-3:]) if st.uses_prior and prior_blobs else None
        res, blob = _run_step(
            i, st, origin="", use_gpt_researcher=False, prior_context=pc
        )
        seq_results.append(res)
        if blob:
            prior_blobs.append(blob)

    def key(s):
        return (
            s["index"],
            s["action"],
            s["ok"],
            (s.get("summary") or "")[:20],
        )

    assert [key(s) for s in par["steps"]] == [key(s) for s in seq_results]
    assert par["ok"] == all(s["ok"] for s in seq_results)


def test_parallel_plan_never_over_commits_quota(monkeypatch, tmp_quota_db):
    """Concurrent independent steps near a shared limit: exactly the limit is
    granted, nothing over-commits, and the ledger serializes correctly."""
    from core.quotas import QuotaTracker

    tracker = QuotaTracker(db_path=tmp_quota_db)
    monkeypatch.setattr(QuotaTracker, "_limit_for", staticmethod(lambda prov: 3))
    granted: list[int] = []
    lock = threading.Lock()

    def fake_research(prompt, *_a, **_k):
        row = tracker.try_reserve("openrouter", "cohere/north-mini-code:free")
        if row is None:
            return {"error": "quota exhausted", "is_safe": True}
        with lock:
            granted.append(row)
        time.sleep(0.02)
        tracker.confirm(row)
        return _ok_research(prompt)

    monkeypatch.setattr("cli_app.orchestrate._run_research", fake_research)
    plan = PipelinePlan(
        summary="quota",
        steps=[
            PipelineStep(action="research", prompt=f"topic number {i}", uses_prior=False)
            for i in range(6)
        ],
    )
    res = execute_plan(plan)

    assert len(granted) == 3  # a single wave of 6 parallel steps gets exactly the limit
    assert tracker.get_usage("openrouter", "cohere/north-mini-code:free") == 3
    assert tracker.remaining("openrouter", "cohere/north-mini-code:free") == 0
    # The 3 that got a slot succeeded; the rest were refused quota-aware.
    assert sum(1 for s in res["steps"] if s["ok"]) == 3
    refused = [
        s for s in res["steps"] if (s.get("result") or {}).get("error")
    ]
    assert len(refused) == 3
    assert all("quota exhausted" in r["result"]["error"] for r in refused)