"""
Tests for LangGraph orchestration.
Includes testing the Git rollback behavior for System A (Vibe Coding)
and SQLite checkpoint resumption for System B (Deep Research).
"""

from __future__ import annotations

import os
import shutil
import pytest
from pathlib import Path
import git

from schemas.vibe_coding import TechnicalSpec, CodeArtifact, DebugReport
from schemas.deep_research import SafetyClassification, CondensedTrends, GroundedReport
from graphs.vibe_coding_graph import get_vibe_coding_graph
from graphs.deep_research_graph import get_deep_research_graph


# ---------------------------------------------------------------------------
# System A — Vibe Coding tests
# ---------------------------------------------------------------------------

@pytest.fixture()
def temp_git_repo(tmp_path: Path):
    """Create a temporary initialized Git repository with an initial commit."""
    repo_dir = tmp_path / "project_repo"
    repo_dir.mkdir()

    # Change working directory to the temp repo dir so git commands run inside it
    old_cwd = os.getcwd()
    os.chdir(repo_dir)

    repo = git.Repo.init(repo_dir)

    initial_file = repo_dir / "README.md"
    initial_file.write_text("# Initial Project Title\n")

    repo.git.add(A=True)
    repo.index.commit("Initial commit")

    yield repo, repo_dir

    # Restore CWD
    os.chdir(old_cwd)


def test_vibe_coding_git_rollback_forced(temp_git_repo, monkeypatch):
    """Test that if vibe-coding fails 3 cycles, git rolls back to the initial commit."""
    repo, repo_dir = temp_git_repo

    # Mock the Architect agent to return a valid spec
    spec = TechnicalSpec(
        architecture="Test architecture",
        test_cases=["Test 1"],
        files_to_create=["src/main.py"],
    )
    monkeypatch.setattr(
        "graphs.vibe_coding_graph.run_architect",
        lambda idea: spec
    )

    # Mock the Coder agent to write a buggy file
    buggy_code = "def hello():\n    return 'buggy'\n"
    monkeypatch.setattr(
        "graphs.vibe_coding_graph.run_coder",
        lambda *args, **kwargs: CodeArtifact(
            files={"src/main.py": buggy_code},
            summary="Written buggy code"
        )
    )

    # Mock Debugger agent to ALWAYS return passed=False
    monkeypatch.setattr(
        "graphs.vibe_coding_graph.run_debugger",
        lambda *args, **kwargs: DebugReport(
            passed=False,
            issues=["Failing test 1"],
            suggested_fix="Please fix the buggy return value."
        )
    )

    # Mock subprocess.run for pytest
    class MockCompletedProcess:
        returncode = 1
        stdout = "Test failed"
        stderr = ""

    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: MockCompletedProcess()
    )

    # Compile and run the Vibe Coding Graph
    graph = get_vibe_coding_graph()

    initial_state = {
        "idea": "Build a hello function",
        "spec": None,
        "artifact": None,
        "test_logs": None,
        "debug_report": None,
        "fix_attempts": 0,
        "git_checkpoint_sha": None,
        "error": None,
    }

    final_state = graph.invoke(initial_state)

    # 1. Assertions on State
    assert final_state["fix_attempts"] == 3
    assert final_state["debug_report"].passed is False

    # 2. Git rollback assertion
    target_file = repo_dir / "src" / "main.py"
    assert not target_file.exists(), "src/main.py should be deleted by the git rollback"

    readme_file = repo_dir / "README.md"
    assert readme_file.exists()
    assert readme_file.read_text() == "# Initial Project Title\n"


# ---------------------------------------------------------------------------
# System B — Deep Research tests
# ---------------------------------------------------------------------------

def test_deep_research_checkpoint_resumption(tmp_path, monkeypatch):
    """Test that Deep Research can resume from a failed node without re-running earlier steps."""
    db_file = str(tmp_path / "checkpoints.db")

    # Tracking calls to verify which nodes get executed in each run
    calls = {
        "safety": 0,
        "compressor": 0,
        "web_search": 0,
        "grounding": 0,
        "synthesizer": 0
    }

    # 1. Setup agent mocks
    monkeypatch.setattr(
        "graphs.deep_research_graph.run_safety_filter",
        lambda query: (calls.update({"safety": calls["safety"] + 1}) or SafetyClassification(is_safe=True))
    )
    monkeypatch.setattr(
        "graphs.deep_research_graph.run_context_compressor",
        lambda query: (calls.update({"compressor": calls["compressor"] + 1}) or CondensedTrends(technologies=["AI"], rationale="test"))
    )
    monkeypatch.setattr(
        "graphs.deep_research_graph.run_web_search",
        lambda terms: (calls.update({"web_search": calls["web_search"] + 1}) or "Web search results compilation text.")
    )

    # Grounding will fail on the first run, and succeed on the second run
    fail_grounding = True

    def mock_grounding(query, search_results):
        calls["grounding"] += 1
        nonlocal fail_grounding
        if fail_grounding:
            raise ValueError("Cohere V2 rate limit 429 simulated failure")
        return GroundedReport(content="Grounded summary of AI trends.", sources=["http://example.com"])

    monkeypatch.setattr(
        "graphs.deep_research_graph.run_grounding",
        mock_grounding
    )

    monkeypatch.setattr(
        "graphs.deep_research_graph.run_synthesizer",
        lambda report, *args, **kwargs: (calls.update({"synthesizer": calls["synthesizer"] + 1}) or GroundedReport(content="Final synthesized executive report.", sources=["http://example.com"]))
    )

    # 2. First Run (Fails at grounding node)
    graph = get_deep_research_graph(db_path=db_file)
    config = {"configurable": {"thread_id": "thread-123"}}

    initial_state = {
        "query": "Quantum AI",
        "safety": None,
        "trends": None,
        "search_results": None,
        "grounded_report": None,
        "final_report": None,
        "error": None,
    }

    with pytest.raises(ValueError) as exc:
        graph.invoke(initial_state, config=config)

    assert "simulated failure" in str(exc.value)

    # Verify node call counts after first (failed) run
    assert calls["safety"] == 1
    assert calls["compressor"] == 1
    assert calls["web_search"] == 1
    assert calls["grounding"] == 1
    assert calls["synthesizer"] == 0

    # 3. Second Run (Resume after fixing the failure)
    fail_grounding = False

    # Invoke the graph again with None as input to resume the saved state from checkpointer
    # Using the EXACT SAME thread_id
    final_state = graph.invoke(None, config=config)

    # Verify final output is successful
    assert final_state["final_report"] is not None
    assert final_state["final_report"].content == "Final synthesized executive report."

    # Verify earlier nodes were NOT run a second time (checkpoint worked!)
    assert calls["safety"] == 1        # Stays at 1 (not re-run)
    assert calls["compressor"] == 1    # Stays at 1 (not re-run)
    assert calls["web_search"] == 1    # Stays at 1 (not re-run)
    assert calls["grounding"] == 2      # Incremented from 1 to 2 (re-run from failure point)
    assert calls["synthesizer"] == 1    # Incremented from 0 to 1 (run for the first time)
