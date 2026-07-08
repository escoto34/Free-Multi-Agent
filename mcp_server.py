"""
MCP server for the "vibe_coding" pipeline (architect -> coder ->
test_executor -> debugger -> git_commit/git_rollback).

Exposes a single tool, `run_vibe_coding`, that opencode (or any MCP client)
can call as if it were a normal tool. Internally it drives the existing
LangGraph pipeline (graphs/vibe_coding_graph.py) and returns the final
CodeArtifact (files + summary) plus debug/status info as structured JSON.

Run standalone (stdio transport, what opencode expects) with:

    python mcp_server.py

Note: the current graph implementation has no checkpointer, so there is no
resumable `thread_id` yet — each call runs the pipeline fully from scratch.
If you later add a SqliteSaver checkpointer to `get_vibe_coding_graph()`,
extend `_invoke_graph` to pass a `configurable={"thread_id": ...}` through
to `.invoke()`.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load .env from this file's own directory, regardless of what cwd/env
# opencode (or any other MCP client) launched this process with. This means
# COHERE_API_KEY / OPENROUTER_API_KEY / GROQ_API_KEY don't need to be
# exported in the parent shell or re-declared in opencode.json's
# "environment" block — they just need to exist in this .env file.
load_dotenv(Path(__file__).parent / ".env")

from graphs.vibe_coding_graph import VibeCodingState, get_vibe_coding_graph

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("vibe-coding")

# Compile the graph once at import time; reused across tool calls.
_graph = get_vibe_coding_graph()


def _initial_state(idea: str) -> VibeCodingState:
    """Build a fresh initial state matching VibeCodingState's TypedDict shape."""
    return {
        "idea": idea,
        "spec": None,
        "artifact": None,
        "test_logs": None,
        "debug_report": None,
        "fix_attempts": 0,
        "git_checkpoint_sha": None,
        "error": None,
    }


def _invoke_graph(idea: str) -> dict[str, Any]:
    """Run the compiled StateGraph end-to-end and normalize the final state
    into a plain JSON-serializable summary.

    Deliberately does NOT include full file contents: the files are already
    written to disk by `coder_node`, and echoing potentially large source
    files back through the MCP response would burn a lot of the calling
    agent's (opencode's) tokens for no benefit — the agent just needs to
    know what happened, not re-read the code it already caused to be
    written.
    """
    final_state: VibeCodingState = _graph.invoke(_initial_state(idea))

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
        "error": final_state.get("error"),
    }


@mcp.tool()
def run_vibe_coding(idea: str) -> str:
    """Run the full vibe-coding pipeline (architect -> coder -> test_executor
    -> debugger -> git_commit/git_rollback) on a software idea, write the
    resulting files to disk, and return a lightweight status summary as
    JSON (NOT the full file contents — the files are already on disk under
    the repo root; read them directly if you need their contents).

    On success (tests pass within 3 fix cycles) the changes are committed to
    Git. On exhausting 3 fix cycles without passing, the repo is rolled back
    (`git reset --hard` + `git clean -fd`) to the pre-run checkpoint.

    Args:
        idea: Natural-language description of what to build,
            e.g. "Build a REST API for task management with SQLite".

    Returns:
        JSON string: {
            "files_written": [{"path": "...", "lines": N}, ...],
            "file_count": N,
            "summary": "...",
            "passed": true_or_false_or_null,
            "issues": ["..."],
            "fix_attempts": 0-3,
            "git_checkpoint_sha": "...",
            "error": null_or_error_message
        }
    """
    try:
        result = _invoke_graph(idea)
    except Exception as exc:
        logger.exception("vibe_coding pipeline crashed")
        result = {"error": str(exc)}
    return json.dumps(result)


if __name__ == "__main__":
    # stdio transport is what opencode (and most MCP clients) expect for
    # locally-spawned servers.
    mcp.run(transport="stdio")
