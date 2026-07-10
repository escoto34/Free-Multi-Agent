"""
Graph-backed retrieval for the interactive chat.

Queries ``graphify-out/graph.json`` (via the graphify CLI when available, else
a lightweight local keyword scan) so the chat model receives a **small, budgeted
snippet** instead of whole files or a long conversation transcript.

The graph snippet is **ephemeral** — it is injected into the LLM call only and
must not be stored in ConversationSession (that would re-fill the context window).
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
GRAPH_JSON = ROOT / "graphify-out" / "graph.json"
GRAPH_REPORT = ROOT / "graphify-out" / "GRAPH_REPORT.md"

# Max chars we ever feed the model from the graph (extra hard cap beyond --budget).
_HARD_CHAR_CAP = 6000


def graph_available() -> bool:
    return GRAPH_JSON.exists()


def query_graph(
    question: str,
    *,
    budget: int = 1200,
    timeout: int = 60,
) -> str:
    """Return a compact graph traversal for *question*.

    Prefers ``graphify query … --budget N``. Falls back to a local scan of
    GRAPH_REPORT.md / node labels if the CLI is missing or fails.
    """
    q = (question or "").strip()
    if not q:
        return ""

    # 1) graphify CLI
    try:
        proc = subprocess.run(
            ["graphify", "query", q, "--budget", str(int(budget))],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = (proc.stdout or "").strip()
        if proc.returncode == 0 and out:
            return _trim(out, max_chars=_HARD_CHAR_CAP)
        # Some builds print to stderr on partial success
        err = (proc.stderr or "").strip()
        if out:
            return _trim(out, max_chars=_HARD_CHAR_CAP)
        if err and "Traversal" in err:
            return _trim(err, max_chars=_HARD_CHAR_CAP)
    except FileNotFoundError:
        logger.debug("graphify binary not on PATH — using local fallback")
    except subprocess.TimeoutExpired:
        logger.warning("graphify query timed out")
    except Exception as exc:
        logger.warning("graphify query failed: %s", exc)

    # 2) Local fallback from report + graph.json labels
    return _trim(_local_fallback(q, budget=budget), max_chars=_HARD_CHAR_CAP)


def _trim(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20].rstrip() + "\n…[truncated]"


def _local_fallback(question: str, *, budget: int) -> str:
    """Keyword hit list from GRAPH_REPORT + graph.json when CLI is unavailable."""
    terms = [t.lower() for t in re.findall(r"[A-Za-z_][A-Za-z0-9_\.]{2,}", question)]
    terms = list(dict.fromkeys(terms))[:12]
    if not terms:
        terms = [question.lower()[:40]]

    chunks: list[str] = []
    char_budget = max(400, budget * 4)  # rough tokens→chars

    if GRAPH_REPORT.exists():
        lines = GRAPH_REPORT.read_text(encoding="utf-8", errors="replace").splitlines()
        hits = [
            ln
            for ln in lines
            if any(t in ln.lower() for t in terms)
        ][:50]
        if hits:
            chunks.append("GRAPH_REPORT hits:\n" + "\n".join(hits))

    if GRAPH_JSON.exists() and sum(len(c) for c in chunks) < char_budget:
        try:
            import json

            data = json.loads(GRAPH_JSON.read_text(encoding="utf-8"))
            nodes = data.get("nodes") or []
            scored: list[tuple[int, str]] = []
            for n in nodes:
                label = str(n.get("label") or n.get("id") or "")
                src = str(n.get("source_file") or n.get("file") or "")
                blob = f"{label} {src}".lower()
                score = sum(1 for t in terms if t in blob)
                if score:
                    scored.append(
                        (score, f"- {label}  [{src}]" if src else f"- {label}")
                    )
            scored.sort(key=lambda x: (-x[0], x[1]))
            if scored:
                chunks.append(
                    "Graph nodes:\n" + "\n".join(s for _, s in scored[:40])
                )
        except Exception as exc:
            logger.debug("local graph.json parse failed: %s", exc)

    if not chunks:
        if not graph_available():
            return (
                "(no graphify-out/graph.json — rebuild the graph with graphify "
                "so chat can use compact codebase context)"
            )
        return "(graph present but no nodes matched this question)"

    text = "\n\n".join(chunks)
    return text[:char_budget]


def build_graph_augmented_messages(
    *,
    question: str,
    graph_snippet: str,
    recent_turns: list[dict[str, str]],
    system_prompt: str,
) -> list[dict[str, str]]:
    """Compose a **small** message list for the chat model.

    - Does not include the full session history.
    - Context (files and/or graph) is a single user-side block per turn.
    """
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
    ]
    # Keep only a few recent turns (already truncated by caller).
    for m in recent_turns:
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    ctx = graph_snippet.strip() or "(empty context)"
    rules = (
        "Answer ONLY from PROJECT CONTEXT below. "
        "Do not claim you executed shell/graphify commands — context was pre-fetched. "
        "Do not invent paths, citations, or footnote markers. "
        "agents/ is the Python package; .agents/ is editor rules (different). "
        "Be concise. Preserve code fences with real backticks when quoting code."
    )
    # If caller already wrapped with === markers, don't double-wrap.
    if "=== " in ctx[:120] or ctx.startswith("--- FILE:") or ctx.startswith("--- DIR:"):
        body = f"{rules}\n\n{ctx}\n\nQUESTION: {question}"
    else:
        body = (
            f"{rules}\n\n"
            f"=== PROJECT CONTEXT ===\n{ctx}\n=== END CONTEXT ===\n\n"
            f"QUESTION: {question}"
        )
    messages.append({"role": "user", "content": body})
    return messages
