"""
LangGraph orchestration for the System B (Deep Research) pipeline.
Orchestrates: Safety Filter -> Context Compressor -> Web Search -> Grounding -> Synthesizer
Features:
  - Persistent SQLite checkpointing to allow resumption on failures.
  - Immediate termination on safety filter rejection.
  - Immediate termination if the web search step admits it did not perform
    a real live search (NoLiveSearchError) — prevents ungrounded content
    from silently flowing into a report that looks verified.
  - Native Cohere grounding parameter integration.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

from agents.deep_research.context_compressor import run_context_compressor
from agents.deep_research.grounding import run_grounding
from agents.deep_research.safety_filter import run_safety_filter
from agents.deep_research.synthesizer import run_synthesizer
from agents.deep_research.web_search import NoLiveSearchError, run_web_search
from core.runs import get_run_history
from schemas.deep_research import CondensedTrends, GroundedReport, SafetyClassification
from schemas.requests import DeepResearchRequest

logger = logging.getLogger(__name__)

# Always under MultiAgent install root so /research works from any cwd.
_DEFAULT_CHECKPOINT_DB = str(
    Path(__file__).resolve().parent.parent / "data" / "checkpoints.db"
)


# ---------------------------------------------------------------------------
# State definition
# ---------------------------------------------------------------------------


class DeepResearchState(TypedDict):
    """LangGraph state representation for the Deep Research pipeline."""

    query: str
    safety: Optional[SafetyClassification]
    trends: Optional[CondensedTrends]
    search_results: Optional[str]
    grounded_report: Optional[GroundedReport]
    final_report: Optional[GroundedReport]
    error: Optional[str]


# ---------------------------------------------------------------------------
# Nodes implementation
# ---------------------------------------------------------------------------


def safety_filter_node(state: DeepResearchState) -> dict[str, Any]:
    """Assess whether the input research query is safe."""
    logger.info("--- SAFETY FILTER NODE ---")
    try:
        safety = run_safety_filter(state["query"])
        return {"safety": safety, "error": None}
    except Exception as exc:
        logger.error("Safety node failed: %s", exc)
        raise exc


def context_compressor_node(state: DeepResearchState) -> dict[str, Any]:
    """Analyze the query to produce keywords/trends."""
    logger.info("--- CONTEXT COMPRESSOR NODE ---")
    try:
        trends = run_context_compressor(state["query"])
        return {"trends": trends, "error": None}
    except Exception as exc:
        logger.error("Context compressor node failed: %s", exc)
        raise exc


def web_search_node(state: DeepResearchState) -> dict[str, Any]:
    """Execute real web search using compound-mini (Tavily integrated).

    HARD BARRIER: if the search step's own output admits it did not perform
    a real live search (NoLiveSearchError), the pipeline stops here with an
    explicit, visible error instead of letting unverified content flow
    downstream into grounding/synthesis.
    """
    logger.info("--- WEB SEARCH NODE ---")
    trends = state["trends"]
    if not trends:
        return {"error": "Missing trends for search."}

    try:
        results = run_web_search(trends.technologies)
        return {"search_results": results, "error": None}
    except NoLiveSearchError as exc:
        logger.error(
            "⚠️ ABORTING — search step did not perform a real live search: %s", exc
        )
        return {
            "search_results": None,
            "error": (
                "El paso de búsqueda no devolvió resultados verificados en vivo. "
                "Abortando para evitar generar un reporte no fundamentado. "
                f"Detalle: {exc}"
            ),
        }
    except Exception as exc:
        logger.error("Web search node failed: %s", exc)
        raise exc


def grounding_node(state: DeepResearchState) -> dict[str, Any]:
    """Synthesize web results into grounded assertions with sources."""
    logger.info("--- GROUNDING NODE ---")
    search_results = state["search_results"]
    if not search_results:
        # Covers both "no results at all" and the NoLiveSearchError abort
        # from web_search_node (which sets search_results=None + error).
        return {"error": state.get("error") or "No search results to ground against."}

    try:
        grounded = run_grounding(state["query"], search_results)
        return {"grounded_report": grounded, "error": None}
    except Exception as exc:
        logger.error("Grounding node failed: %s", exc)
        raise exc


def synthesizer_node(state: DeepResearchState) -> dict[str, Any]:
    """Polishes and structures final document."""
    logger.info("--- SYNTHESIZER NODE ---")
    grounded_report = state["grounded_report"]
    if not grounded_report:
        return {"error": state.get("error") or "No grounded report to synthesize."}

    try:
        final_report = run_synthesizer(
            grounded_report, search_results=state.get("search_results", "")
        )
        return {"final_report": final_report, "error": None}
    except Exception as exc:
        logger.error("Synthesizer node failed: %s", exc)
        raise exc


# ---------------------------------------------------------------------------
# Routing logic
# ---------------------------------------------------------------------------


def safety_routing(state: DeepResearchState) -> str:
    """Conditional edge evaluating safety filter."""
    safety = state["safety"]
    if not safety:
        return "unsafe"

    if safety.is_safe:
        logger.info("✔ Query is safe. Proceeding to compressor.")
        return "safe"

    logger.warning("⚠️ Unsafe query detected! Terminating pipeline.")
    return "unsafe"


def search_routing(state: DeepResearchState) -> str:
    """Conditional edge: stop the pipeline if web_search set an error
    (either no results, or the NoLiveSearchError hard-abort)."""
    if state.get("error"):
        logger.warning(
            "⚠️ Search step failed/aborted. Terminating pipeline: %s", state["error"]
        )
        return "aborted"
    return "ok"


# ---------------------------------------------------------------------------
# Graph compilation factory
# ---------------------------------------------------------------------------


def get_deep_research_graph(db_path: Optional[str] = None) -> Any:
    """Build and compile the StateGraph for System B.

    Equipped with a persistent SqliteSaver checkpointer.
    """
    db_file = db_path or _DEFAULT_CHECKPOINT_DB
    Path(db_file).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_file, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    checkpointer = SqliteSaver(conn)
    checkpointer.setup()

    workflow = StateGraph(DeepResearchState)

    workflow.add_node("safety_filter", safety_filter_node)
    workflow.add_node("context_compressor", context_compressor_node)
    workflow.add_node("web_search", web_search_node)
    workflow.add_node("grounding", grounding_node)
    workflow.add_node("synthesizer", synthesizer_node)

    workflow.set_entry_point("safety_filter")

    workflow.add_conditional_edges(
        "safety_filter",
        safety_routing,
        {
            "safe": "context_compressor",
            "unsafe": END,
        },
    )

    workflow.add_edge("context_compressor", "web_search")

    # Changed from an unconditional edge to a conditional one: if web_search
    # aborted because of NoLiveSearchError (or produced no results at all),
    # stop here instead of continuing to grounding with unverified/empty data.
    workflow.add_conditional_edges(
        "web_search",
        search_routing,
        {
            "ok": "grounding",
            "aborted": END,
        },
    )

    workflow.add_edge("grounding", "synthesizer")
    workflow.add_edge("synthesizer", END)

    return workflow.compile(checkpointer=checkpointer)


def initial_deep_research_state(topic: str) -> DeepResearchState:
    """Build a fresh graph state for System B."""
    return {
        "query": topic,
        "safety": None,
        "trends": None,
        "search_results": None,
        "grounded_report": None,
        "final_report": None,
        "error": None,
    }


def summarize_deep_research_state(final_state: dict[str, Any]) -> dict[str, Any]:
    """JSON-serializable summary (full report content included for CLI display)."""
    safety = final_state.get("safety")
    report = final_state.get("final_report")
    return {
        "error": final_state.get("error"),
        "is_safe": safety.is_safe if safety else None,
        "safety_reasons": safety.reasons if safety else [],
        "content": report.content if report else None,
        "sources": report.sources if report else [],
        "has_report": report is not None,
    }


def invoke_deep_research_pipeline(
    topic: str,
    *,
    thread_id: Optional[str] = None,
    db_path: Optional[str] = None,
    graph=None,
    record_history: bool = True,
) -> dict[str, Any]:
    """Validate input, run System B (optionally resume), record history.

    Shared entrypoint for CLI (and future HTTP) so checkpoint resume stays consistent.
    """
    req = DeepResearchRequest(topic=topic, thread_id=thread_id)
    tid = req.thread_id or f"research-{abs(hash(req.topic)) % 100000}"

    history = get_run_history() if record_history else None
    run_id = None
    if history is not None:
        run_id = history.start(
            "deep_research",
            req.topic,
            meta={"thread_id": tid, "resume": bool(req.thread_id)},
        )

    compiled = graph if graph is not None else get_deep_research_graph(db_path=db_path)
    config = {"configurable": {"thread_id": tid}}
    inputs: Any = None if req.thread_id else initial_deep_research_state(req.topic)

    try:
        final_state = compiled.invoke(inputs, config=config)
        summary = summarize_deep_research_state(final_state)
        summary["thread_id"] = tid
        if history is not None and run_id is not None:
            if summary.get("error"):
                status = "aborted"
            elif summary.get("is_safe") is False:
                status = "unsafe"
            elif summary.get("has_report"):
                status = "success"
            else:
                status = "failed"
            history.finish(
                run_id,
                status=status,
                result_summary=(summary.get("content") or status or "")[:500],
                error=summary.get("error"),
                meta={
                    "thread_id": tid,
                    "is_safe": summary.get("is_safe"),
                    "source_count": len(summary.get("sources") or []),
                },
            )
        if run_id is not None:
            summary["run_id"] = run_id
        return summary
    except Exception as exc:
        if history is not None and run_id is not None:
            history.finish(
                run_id,
                status="error",
                error=str(exc),
                meta={"thread_id": tid},
            )
        raise
