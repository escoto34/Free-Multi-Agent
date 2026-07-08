"""
LangGraph orchestration for the System A (Vibe Coding) pipeline.
Orchestrates: Architect -> Coder -> Test Executor -> Debugger
Features:
  - Maximum 3 fix/retry cycles on failing tests.
  - Actual Git commit on success and Git rollback (git reset --hard) on exhaustion.
  - Automatic model fallback from tencent/hy3 to gpt-oss-120b.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Optional, TypedDict

import git
from langgraph.graph import END, StateGraph

from agents.vibe_coding.architect import run_architect
from agents.vibe_coding.coder import run_coder
from agents.vibe_coding.debugger import run_debugger
from schemas.vibe_coding import CodeArtifact, DebugReport, TechnicalSpec

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State definition
# ---------------------------------------------------------------------------


class VibeCodingState(TypedDict):
    """LangGraph state representation for the Vibe Coding pipeline."""

    idea: str
    spec: Optional[TechnicalSpec]
    artifact: Optional[CodeArtifact]
    test_logs: Optional[str]
    debug_report: Optional[DebugReport]
    fix_attempts: int
    git_checkpoint_sha: Optional[str]
    error: Optional[str]


# ---------------------------------------------------------------------------
# Git helper functions
# ---------------------------------------------------------------------------


def get_git_repo(path: str = ".") -> Optional[git.Repo]:
    """Retrieve the Git repository instance if available."""
    try:
        return git.Repo(path, search_parent_directories=True)
    except Exception as exc:
        logger.warning("No Git repository found at path %s: %s", path, exc)
        return None


def make_git_checkpoint(repo: git.Repo, message: str) -> Optional[str]:
    """Stage all changes and commit, returning the commit SHA."""
    try:
        repo.git.add(A=True)
        # Check if there are changes to commit
        if repo.is_dirty(untracked_files=True):
            commit = repo.index.commit(message)
            logger.info("Git checkpoint created: %s - %s", commit.hexsha[:7], message)
            return commit.hexsha
        else:
            logger.info("No changes to commit for checkpoint.")
            return repo.head.commit.hexsha
    except Exception as exc:
        logger.error("Failed to create Git checkpoint: %s", exc)
        return None


def perform_git_rollback(repo: git.Repo, sha: str) -> bool:
    """Perform a hard reset to the specified Git SHA and clean untracked files."""
    try:
        repo.git.reset("--hard", sha)
        repo.git.clean("-fd")
        logger.warning("Git reset and cleaned successfully to checkpoint: %s", sha[:7])
        return True
    except Exception as exc:
        logger.error("Failed to perform Git rollback to %s: %s", sha, exc)
        return False


# ---------------------------------------------------------------------------
# Nodes implementation
# ---------------------------------------------------------------------------


def architect_node(state: VibeCodingState) -> dict[str, Any]:
    """Runs the Architect agent to design the TechnicalSpec."""
    logger.info("--- ARCHITECT NODE ---")
    try:
        # Before starting, capture the current Git HEAD SHA as the clean state checkpoint
        repo = get_git_repo()
        sha = repo.head.commit.hexsha if repo else None

        spec = run_architect(state["idea"])
        return {
            "spec": spec,
            "git_checkpoint_sha": sha,
            "error": None,
        }
    except Exception as exc:
        logger.error("Architect node failed: %s", exc)
        return {"error": f"Architect error: {exc}"}


class UnsafeFilePathError(Exception):
    """Raised when the Coder agent tries to write outside the repo root or
    to a path that isn't a plain relative file path."""


def _resolve_repo_root() -> Path:
    """Return the repo root to constrain writes to, falling back to cwd."""
    repo = get_git_repo()
    if repo is not None and repo.working_tree_dir:
        return Path(repo.working_tree_dir).resolve()
    return Path(".").resolve()


def _validate_and_resolve_target(file_path: str, repo_root: Path) -> Path:
    """Resolve `file_path` against `repo_root` and ensure it can't escape it.

    Rejects absolute paths and any `..` traversal that would land outside
    the repo root — the Coder agent's output is untrusted LLM content and
    must not be able to write arbitrary files on the host.
    """
    if not isinstance(file_path, str) or not file_path.strip():
        raise UnsafeFilePathError(f"Empty or invalid file path: {file_path!r}")

    candidate = Path(file_path)
    if candidate.is_absolute():
        raise UnsafeFilePathError(
            f"Refusing to write absolute path outside repo: {file_path!r}"
        )

    resolved = (repo_root / candidate).resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError:
        raise UnsafeFilePathError(
            f"Refusing to write outside repo root ({repo_root}): {file_path!r}"
        )
    return resolved


def _write_artifact_files(artifact: CodeArtifact, repo_root: Path) -> list[str]:
    """Validate and write every file in `artifact.files` atomically.

    All paths are validated *before* any file is touched, so a single bad
    path aborts the whole batch instead of leaving a half-written set of
    files on disk. Each file is written to a temp path in the same
    directory and then atomically renamed into place, so a crash mid-write
    can't leave a truncated/corrupt file behind either.

    Returns the list of relative file paths that were written, in the
    order they were written.
    """
    if not artifact.files:
        raise ValueError("Coder returned an empty file set — nothing to write.")

    # Pass 1: validate every path up front (fail fast, no partial writes).
    resolved_targets: list[tuple[str, Path, str]] = []
    for file_path, code in artifact.files.items():
        if not isinstance(code, str):
            raise UnsafeFilePathError(
                f"File content for {file_path!r} is not a string (got {type(code).__name__})."
            )
        resolved = _validate_and_resolve_target(file_path, repo_root)
        resolved_targets.append((file_path, resolved, code))

    # Pass 2: write each file atomically (temp file + os.replace).
    written: list[str] = []
    for file_path, resolved, code in resolved_targets:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = resolved.with_name(f".{resolved.name}.tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8", newline="") as fh:
                fh.write(code)
            os.replace(tmp_path, resolved)
        finally:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
        written.append(file_path)
        logger.info("Wrote file: %s", file_path)

    return written


def coder_node(state: VibeCodingState) -> dict[str, Any]:
    """Runs the Coder agent to implement the source code."""
    logger.info("--- CODER NODE ---")
    try:
        spec = state["spec"]
        if not spec:
            raise ValueError("No technical specification found in state.")

        # If we have a debug report, modify the query to request the fix
        dr = state["debug_report"]
        if dr and dr.suggested_fix:
            # We construct a temporary spec that appends the debug requirements
            modified_spec = TechnicalSpec(
                architecture=(
                    f"{spec.architecture}\n\n"
                    f"DEBUGGER ALERT: A previous implementation failed. "
                    f"Please apply this fix: {dr.suggested_fix}"
                ),
                test_cases=spec.test_cases,
                files_to_create=spec.files_to_create,
            )
            artifact = run_coder(modified_spec)
        else:
            artifact = run_coder(spec)

        # Write files physically to disk, constrained to the repo root and
        # atomically (all paths validated first, each file written via a
        # temp-file + rename so a mid-write crash can't corrupt a file).
        repo_root = _resolve_repo_root()
        written = _write_artifact_files(artifact, repo_root)
        logger.info("Coder wrote %d file(s) under %s", len(written), repo_root)

        return {"artifact": artifact, "error": None}
    except Exception as exc:
        logger.error("Coder node failed: %s", exc)
        return {"error": f"Coder error: {exc}"}


def test_executor_node(state: VibeCodingState) -> dict[str, Any]:
    """Runs unit tests on the generated files and captures logs."""
    logger.info("--- TEST EXECUTOR NODE ---")
    spec = state["spec"]
    if not spec:
        return {"test_logs": "No spec to run tests against.", "error": "No spec"}

    # We will search for any generated test files and run pytest on them
    test_files = [f for f in spec.files_to_create if "test" in f]
    if not test_files:
        # Default fallback to run pytest in directory
        test_files = ["tests/"]

    logger.info("Running pytest on target test locations: %s", test_files)
    try:
        # Run pytest inside the virtualenv environment
        python_bin = "./venv/bin/pytest"
        if not Path(python_bin).exists():
            python_bin = "pytest"

        cmd = [python_bin] + test_files + ["-v"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        logs = f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
        logger.info("Test execution finished (exit code %d)", result.returncode)
        return {"test_logs": logs, "error": None}
    except Exception as exc:
        logger.warning(
            "Running real tests failed or timed out: %s. Using fallback log.", exc
        )
        return {"test_logs": f"Execution failed: {exc}", "error": None}


def debugger_node(state: VibeCodingState) -> dict[str, Any]:
    """Runs the Debugger agent to assess test logs and propose fixes."""
    logger.info("--- DEBUGGER NODE ---")
    artifact = state["artifact"]
    test_logs = state["test_logs"] or ""

    if not artifact:
        return {"error": "No code artifact to debug."}

    try:
        # Increment fix attempts
        attempts = state["fix_attempts"] + 1

        # Run debugger agent (which cascades from Hy3 to gpt-oss-120b on error)
        dr = run_debugger(artifact, test_logs)
        logger.info(
            "Debugger Result: passed=%s, issues=%d, attempts=%d/3",
            dr.passed,
            len(dr.issues),
            attempts,
        )
        return {
            "debug_report": dr,
            "fix_attempts": attempts,
            "error": None,
        }
    except Exception as exc:
        logger.error("Debugger node failed: %s", exc)
        return {"error": f"Debugger error: {exc}"}


def git_commit_node(state: VibeCodingState) -> dict[str, Any]:
    """Commit the successful code modifications to Git."""
    logger.info("--- GIT COMMIT NODE ---")
    repo = get_git_repo()
    if repo:
        sha = make_git_checkpoint(repo, f"Vibe Coding success: {state['idea'][:40]}")
        return {"git_checkpoint_sha": sha}
    logger.warning("Skipping Git commit node: No Git repo found.")
    return {}


def git_rollback_node(state: VibeCodingState) -> dict[str, Any]:
    """Exhausted retries: revert files to the original clean Git state."""
    logger.info("--- GIT ROLLBACK NODE (EXHAUSTED RETRIES) ---")
    repo = get_git_repo()
    sha = state["git_checkpoint_sha"]
    if repo and sha:
        perform_git_rollback(repo, sha)
        logger.info(
            "Git rolled back successfully to clean state checkpoint %s", sha[:7]
        )
    else:
        logger.warning("Skipping Git rollback: Repo or checkpoint SHA missing.")
    return {}


# ---------------------------------------------------------------------------
# Routing logic
# ---------------------------------------------------------------------------


def debugger_routing(state: VibeCodingState) -> str:
    """Conditional edge from Debugger node."""
    dr = state["debug_report"]
    attempts = state["fix_attempts"]

    if dr and dr.passed:
        logger.info("✔ Tests passed! Committing and ending.")
        return "git_commit"

    if attempts >= 3:
        logger.warning("❌ Maximum fix attempts (3) reached. Rolling back and ending.")
        return "git_rollback"

    logger.info(
        "⤷ Refactor cycle required: returning to Coder node. attempt %d/3", attempts
    )
    return "coder"


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------


def get_vibe_coding_graph() -> StateGraph:
    """Build and compile the StateGraph for System A."""
    workflow = StateGraph(VibeCodingState)

    # Add Nodes
    workflow.add_node("architect", architect_node)
    workflow.add_node("coder", coder_node)
    workflow.add_node("test_executor", test_executor_node)
    workflow.add_node("debugger", debugger_node)
    workflow.add_node("git_commit", git_commit_node)
    workflow.add_node("git_rollback", git_rollback_node)

    # Define Flow
    workflow.set_entry_point("architect")

    workflow.add_edge("architect", "coder")
    workflow.add_edge("coder", "test_executor")
    workflow.add_edge("test_executor", "debugger")

    # Conditional Routing Edge
    workflow.add_conditional_edges(
        "debugger",
        debugger_routing,
        {
            "git_commit": "git_commit",
            "git_rollback": "git_rollback",
            "coder": "coder",
        },
    )

    workflow.add_edge("git_commit", END)
    workflow.add_edge("git_rollback", END)

    # Compile the graph
    return workflow.compile()
