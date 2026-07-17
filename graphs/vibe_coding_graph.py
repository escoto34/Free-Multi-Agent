"""
LangGraph orchestration for the System A (Vibe Coding) pipeline.
Orchestrates: Architect -> Coder -> Test Executor -> Debugger
Features:
  - Maximum 3 fix/retry cycles on failing tests.
  - Actual Git commit on success and Git rollback (git reset --hard) on exhaustion.
  - Pre-existing dirty work is auto-stashed before the run so rollback cannot
    silently destroy the caller's uncommitted changes (critical for MCP use).
  - Automatic model fallback from tencent/hy3 to gpt-oss-120b (via YAML config).
"""

from __future__ import annotations

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
from agents.vibe_coding.preserve import (
    missing_preserved_symbols,
    read_existing_sources,
)
from agents.vibe_coding.test_runner import execute_vibe_tests
from core.agent_config import get_max_fix_cycles
from core.runs import get_run_history
from schemas.requests import VibeCodingRequest
from schemas.vibe_coding import CodeArtifact, DebugReport, TechnicalSpec

logger = logging.getLogger(__name__)

# Marker used for auto-stashes of the caller's pre-run WIP. Must stay stable so
# restore can find the right entry even if other stashes exist on the repo.
USER_WIP_STASH_MESSAGE = "vibe-coding: pre-run user WIP (auto-stashed)"

# Snapshot of last failed vibe artifact (survives git rollback; under data/ gitignore)
_FAILED_ARTIFACT_DIR = (
    Path(__file__).resolve().parent.parent / "data" / "vibe_last_failed"
)


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
    user_wip_stashed: bool
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


def stash_preexisting_work(repo: git.Repo) -> bool:
    """If the working tree is dirty, stash user changes (incl. untracked).

    Rollback does ``git reset --hard`` + ``git clean -fd`` to the pre-run HEAD.
    Without this stash, any uncommitted work that was already present when the
    pipeline started would be destroyed along with the LLM's failed edits —
    a real footgun for CLI/MCP use against whatever repo is cwd.

    Returns True if a stash was created.
    """
    if not repo.is_dirty(untracked_files=True):
        return False
    logger.warning(
        "Working tree has uncommitted changes. Stashing them as %r so a "
        "failed run's git reset --hard cannot destroy them. Restored after "
        "commit or rollback.",
        USER_WIP_STASH_MESSAGE,
    )
    repo.git.stash("push", "-u", "-m", USER_WIP_STASH_MESSAGE)
    return True


def restore_preexisting_work(repo: git.Repo) -> None:
    """Pop the auto-stash created by ``stash_preexisting_work``, if present."""
    try:
        stash_list = repo.git.stash("list")
    except Exception as exc:
        logger.error("Could not list stashes to restore user WIP: %s", exc)
        return

    for line in stash_list.splitlines():
        if USER_WIP_STASH_MESSAGE not in line:
            continue
        # line looks like: stash@{0}: On main: vibe-coding: pre-run user WIP ...
        ref = line.split(":", 1)[0].strip()
        try:
            repo.git.stash("pop", ref)
            logger.info("Restored pre-run user WIP from %s", ref)
        except Exception as exc:
            # Conflicts or already-applied: leave the stash for the user.
            logger.error(
                "Failed to auto-restore user WIP from %s (%s). "
                "Your changes are still in `git stash list` under message %r — "
                "run `git stash pop` manually.",
                ref,
                exc,
                USER_WIP_STASH_MESSAGE,
            )
        return


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
        # Protect any pre-existing dirty work, then snapshot HEAD as the
        # rollback target. Order matters: stash first so the checkpoint SHA
        # is a clean tree; otherwise reset --hard would wipe user WIP.
        repo = get_git_repo()
        user_wip_stashed = False
        sha = None
        if repo:
            user_wip_stashed = stash_preexisting_work(repo)
            sha = repo.head.commit.hexsha

        spec = run_architect(state["idea"])
        return {
            "spec": spec,
            "git_checkpoint_sha": sha,
            "user_wip_stashed": user_wip_stashed,
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


def _apply_preservation_warnings(
    existing: dict[str, str],
    artifact: CodeArtifact,
) -> CodeArtifact:
    """Log (and note in summary) if the Coder dropped top-level symbols from existing files.

    Does not invent code back into the file — that would risk syntax errors —
    but surfaces the risk so the Debugger / next fix cycle can restore it.
    """
    dropped: list[str] = []
    for path, old in existing.items():
        new = (artifact.files or {}).get(path)
        if new is None:
            continue
        missing = missing_preserved_symbols(old, new)
        if missing:
            dropped.append(f"{path}: missing symbols {missing}")
            logger.warning(
                "Preservation risk in %s — symbols present before but not in "
                "new content: %s",
                path,
                missing,
            )
    if not dropped:
        return artifact
    note = (
        "PRESERVATION WARNING — the following top-level symbols from existing "
        "files no longer appear in the new content (may be intentional if "
        "redundant/conflicting, otherwise a bug):\n- "
        + "\n- ".join(dropped)
    )
    summary = (artifact.summary or "").rstrip() + "\n\n" + note
    return artifact.model_copy(update={"summary": summary})


def coder_node(state: VibeCodingState) -> dict[str, Any]:
    """Runs the Coder agent, merging into existing sources when present."""
    logger.info("--- CODER NODE ---")
    try:
        spec = state["spec"]
        if not spec:
            raise ValueError("No technical specification found in state.")

        repo_root = _resolve_repo_root()
        # Load current disk contents for every path the Architect wants to touch
        # so the Coder can merge instead of rewriting from a blank slate.
        existing = read_existing_sources(repo_root, list(spec.files_to_create or []))
        if existing:
            logger.info(
                "Preservation context: %d existing file(s) loaded for merge",
                len(existing),
            )

        work_spec = spec
        dr = state["debug_report"]
        if dr and dr.suggested_fix:
            work_spec = TechnicalSpec(
                architecture=(
                    f"{spec.architecture}\n\n"
                    f"DEBUGGER ALERT: A previous implementation failed. "
                    f"Please apply this fix while STILL preserving unrelated "
                    f"existing logic: {dr.suggested_fix}"
                ),
                test_cases=spec.test_cases,
                files_to_create=spec.files_to_create,
            )

        artifact = run_coder(work_spec, existing_files=existing)
        artifact = _apply_preservation_warnings(existing, artifact)

        written = _write_artifact_files(artifact, repo_root)
        logger.info("Coder wrote %d file(s) under %s", len(written), repo_root)

        return {"artifact": artifact, "error": None}
    except Exception as exc:
        logger.error("Coder node failed: %s", exc)
        return {"error": f"Coder error: {exc}"}


def test_executor_node(state: VibeCodingState) -> dict[str, Any]:
    """Run project-local tests only — never the MultiAgent monorepo suite.

    Strategy (see ``agents.vibe_coding.test_runner``):
    - pytest only on ``test_*.py`` files from this artifact/spec
    - static HTML/CSS content checks when marketing sites are generated
    - fail fast on Next/Jest stacks (runtime has no npm test integration)
    """
    logger.info("--- TEST EXECUTOR NODE ---")
    spec = state["spec"]
    if not spec:
        return {"test_logs": "No spec to run tests against.", "error": "No spec"}

    repo_root = _resolve_repo_root()
    artifact = state.get("artifact")
    idea = state.get("idea") or ""
    try:
        logs = execute_vibe_tests(
            spec=spec,
            artifact=artifact,
            idea=idea,
            repo_root=repo_root,
        )
        logger.info(
            "Test execution finished (overall %s)",
            "PASS" if logs.startswith("OVERALL: PASS") else "FAIL",
        )
        return {"test_logs": logs, "error": None}
    except Exception as exc:
        logger.warning("Test executor error: %s", exc)
        return {"test_logs": f"Execution failed: {exc}", "error": None}


def debugger_node(state: VibeCodingState) -> dict[str, Any]:
    """Runs the Debugger agent to assess test logs and propose fixes.

    Always increments ``fix_attempts`` — even on missing artifact or LLM
    failure — so ``debugger_routing`` can hit ``max_fix_cycles`` and stop.
    (A previous bug returned only ``error`` on failure, leaving attempts at 0
    and looping coder→test→debugger until LangGraph's recursion limit.)
    """
    logger.info("--- DEBUGGER NODE ---")
    artifact = state.get("artifact")
    test_logs = state.get("test_logs") or ""
    attempts = int(state.get("fix_attempts") or 0) + 1
    max_cycles = get_max_fix_cycles()

    if not artifact:
        logger.error("Debugger: no artifact (attempt %d/%d)", attempts, max_cycles)
        return {
            "debug_report": DebugReport(
                passed=False,
                issues=["No code artifact to debug."],
                suggested_fix=None,
            ),
            "fix_attempts": attempts,
            "error": "No code artifact to debug.",
        }

    try:
        dr = run_debugger(artifact, test_logs)
        logger.info(
            "Debugger Result: passed=%s, issues=%d, attempts=%d/%d",
            dr.passed,
            len(dr.issues),
            attempts,
            max_cycles,
        )
        return {
            "debug_report": dr,
            "fix_attempts": attempts,
            "error": None,
        }
    except Exception as exc:
        logger.error("Debugger node failed (attempt %d/%d): %s", attempts, max_cycles, exc)
        # Still count the attempt so the graph cannot spin forever.
        return {
            "debug_report": DebugReport(
                passed=False,
                issues=[f"Debugger agent error: {exc}"],
                suggested_fix=(
                    "Debugger failed to analyze results. Simplify the change set "
                    "and ensure tests are runnable."
                ),
            ),
            "fix_attempts": attempts,
            "error": f"Debugger error: {exc}",
        }


def git_commit_node(state: VibeCodingState) -> dict[str, Any]:
    """Commit the successful code modifications to Git."""
    logger.info("--- GIT COMMIT NODE ---")
    repo = get_git_repo()
    if repo:
        sha = make_git_checkpoint(repo, f"Vibe Coding success: {state['idea'][:40]}")
        # Re-apply any user WIP that was stashed at the start of the run.
        if state.get("user_wip_stashed"):
            restore_preexisting_work(repo)
        return {"git_checkpoint_sha": sha}
    logger.warning("Skipping Git commit node: No Git repo found.")
    return {}


def _snapshot_failed_artifact(state: VibeCodingState) -> Optional[str]:
    """Persist last failed vibe files under data/ so rollback does not erase them."""
    artifact = state.get("artifact")
    if not artifact or not artifact.files:
        return None
    try:
        out = _FAILED_ARTIFACT_DIR
        out.mkdir(parents=True, exist_ok=True)
        # Clear previous snapshot
        for old in out.iterdir():
            if old.is_file():
                old.unlink(missing_ok=True)
            elif old.is_dir():
                import shutil

                shutil.rmtree(old, ignore_errors=True)
        for rel, code in artifact.files.items():
            target = out / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(code or "", encoding="utf-8")
        meta = out / "README_FAILED_RUN.txt"
        meta.write_text(
            "Vibe coding failed tests and Git rolled back the working tree.\n"
            "This folder is a snapshot of the last failed artifact so work is not lost.\n"
            f"idea: {(state.get('idea') or '')[:500]}\n"
            f"issues: {getattr(state.get('debug_report'), 'issues', None)}\n",
            encoding="utf-8",
        )
        logger.info("Saved failed vibe artifact snapshot to %s", out)
        return str(out)
    except Exception as exc:
        logger.warning("Could not snapshot failed artifact: %s", exc)
        return None


def git_rollback_node(state: VibeCodingState) -> dict[str, Any]:
    """Exhausted retries: revert files to the original clean Git state.

    After ``reset --hard`` + ``clean -fd``, re-apply any pre-run user WIP that
    was stashed in ``architect_node`` so uncommitted local work is not lost.
    A copy of the failed artifact is kept under ``data/vibe_last_failed/``.
    """
    logger.info("--- GIT ROLLBACK NODE (EXHAUSTED RETRIES) ---")
    snap = _snapshot_failed_artifact(state)
    if snap:
        logger.warning("Failed artifact preserved at %s", snap)
    repo = get_git_repo()
    sha = state["git_checkpoint_sha"]
    if repo and sha:
        perform_git_rollback(repo, sha)
        logger.info(
            "Git rolled back successfully to clean state checkpoint %s", sha[:7]
        )
        if state.get("user_wip_stashed"):
            restore_preexisting_work(repo)
    else:
        logger.warning("Skipping Git rollback: Repo or checkpoint SHA missing.")
    return {}


# ---------------------------------------------------------------------------
# Routing logic
# ---------------------------------------------------------------------------


def debugger_routing(state: VibeCodingState) -> str:
    """Conditional edge from Debugger node.

    Max fix cycles come from ``config/model_router.yaml``
    (``vibe_coding.max_fix_cycles``), not a hardcoded 3.

    Hard-stops even if attempts somehow fail to advance (ceiling) so we never
    burn thousands of LLM calls into a recursion-limit error.
    """
    dr = state.get("debug_report")
    attempts = int(state.get("fix_attempts") or 0)
    max_cycles = max(1, int(get_max_fix_cycles()))
    # Absolute ceiling: never more than 2× configured cycles (defense in depth).
    hard_ceiling = max(max_cycles * 2, max_cycles + 1)

    if dr and dr.passed:
        logger.info("✔ Tests passed! Committing and ending.")
        return "git_commit"

    if attempts >= max_cycles or attempts >= hard_ceiling:
        logger.warning(
            "❌ Maximum fix attempts reached (attempts=%d, max=%d). Rolling back.",
            attempts,
            max_cycles,
        )
        return "git_rollback"

    # No artifact / fatal state → do not re-enter coder forever.
    if not state.get("artifact"):
        logger.warning("❌ No artifact after debugger — rolling back.")
        return "git_rollback"

    logger.info(
        "⤷ Refactor cycle required: returning to Coder node. attempt %d/%d",
        attempts,
        max_cycles,
    )
    return "coder"


def initial_vibe_coding_state(idea: str) -> VibeCodingState:
    """Build a fresh graph state for System A."""
    return {
        "idea": idea,
        "spec": None,
        "artifact": None,
        "test_logs": None,
        "debug_report": None,
        "fix_attempts": 0,
        "git_checkpoint_sha": None,
        "user_wip_stashed": False,
        "error": None,
    }


def summarize_vibe_coding_state(final_state: dict[str, Any]) -> dict[str, Any]:
    """Normalize final state into a JSON-serializable summary (no full file bodies)."""
    artifact = final_state.get("artifact")
    debug_report = final_state.get("debug_report")
    files = artifact.files if artifact else {}
    file_summaries = [
        {"path": path, "lines": code.count("\n") + 1 if code else 0}
        for path, code in files.items()
    ]
    return {
        "files_written": file_summaries,
        "file_count": len(file_summaries),
        "summary": artifact.summary if artifact else None,
        "passed": debug_report.passed if debug_report else None,
        "issues": debug_report.issues if debug_report else [],
        "fix_attempts": final_state.get("fix_attempts", 0),
        "git_checkpoint_sha": final_state.get("git_checkpoint_sha"),
        "user_wip_stashed": final_state.get("user_wip_stashed", False),
        "error": final_state.get("error"),
    }


def invoke_vibe_coding_pipeline(
    idea: str,
    *,
    graph=None,
    record_history: bool = True,
) -> dict[str, Any]:
    """Validate input, run System A, record history, return summary dict.

    Shared entrypoint for CLI and MCP so state shape and logging stay in sync.
    """
    req = VibeCodingRequest(idea=idea)
    history = get_run_history() if record_history else None
    run_id = None
    if history is not None:
        run_id = history.start("vibe_coding", req.idea)

    compiled = graph if graph is not None else get_vibe_coding_graph()
    try:
        # Bound graph steps: architect + N×(coder+test+debugger) + git ≈ 2+3N+1.
        # Keep a small buffer; never leave the default open-ended if routing breaks.
        max_c = max(1, int(get_max_fix_cycles()))
        recursion_limit = max(25, 8 + max_c * 6)
        final_state = compiled.invoke(
            initial_vibe_coding_state(req.idea),
            config={"recursion_limit": recursion_limit},
        )
        summary = summarize_vibe_coding_state(final_state)
        if history is not None and run_id is not None:
            status = "success" if summary.get("passed") else (
                "error" if summary.get("error") else "failed"
            )
            history.finish(
                run_id,
                status=status,
                result_summary=summary.get("summary") or status,
                error=summary.get("error"),
                meta={
                    "passed": summary.get("passed"),
                    "fix_attempts": summary.get("fix_attempts"),
                    "file_count": summary.get("file_count"),
                    "git_checkpoint_sha": summary.get("git_checkpoint_sha"),
                },
            )
        if run_id is not None:
            summary["run_id"] = run_id
        return summary
    except Exception as exc:
        if history is not None and run_id is not None:
            history.finish(run_id, status="error", error=str(exc))
        raise


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------


def _after_architect(state: VibeCodingState) -> str:
    """Skip the code loop if Architect failed (no infinite empty retries)."""
    if state.get("error") or not state.get("spec"):
        return "git_rollback"
    return "coder"


def _after_coder(state: VibeCodingState) -> str:
    """Skip tests/debug if Coder produced nothing."""
    if state.get("error") or not state.get("artifact"):
        return "git_rollback"
    return "test_executor"


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

    workflow.add_conditional_edges(
        "architect",
        _after_architect,
        {"coder": "coder", "git_rollback": "git_rollback"},
    )
    workflow.add_conditional_edges(
        "coder",
        _after_coder,
        {"test_executor": "test_executor", "git_rollback": "git_rollback"},
    )
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
