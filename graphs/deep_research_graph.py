"""
LangGraph orchestration for the System B (Deep Research) pipeline.
Orchestrates: Safety Filter -> Context Compressor -> Web Search -> Grounding -> Synthesizer
Features:
  - Persistent SQLite checkpointing to allow resumption on failures.
  - Immediate termination on safety filter rejection.
   - Real web search via DuckDuckGo + HTTP page fetches (no LLM fabrication).
    - Post-hoc verification of cited URLs against actual fetched content.
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
from agents.deep_research.research_types import profile_from_mapping
from agents.deep_research.safety_filter import run_safety_filter
from agents.deep_research.synthesizer import run_synthesizer
from agents.deep_research.web_search import run_web_search
from core.difficulty_scorer import (
    assessment_from_state,
    assessments_to_state_dict,
    plan_pipeline_difficulties,
)
from core.handoff import HandoffError, transfer_control
from core.model_selector import record_model_selection_handoff, select_for_role
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
    """LangGraph state representation for the Deep Research pipeline.

    Domain fields hold intermediate agent outputs. ``handoff_history`` is the
    formal Swarm-style audit trail (see ``core.handoff.transfer_control``).
    """

    query: str
    safety: Optional[SafetyClassification]
    trends: Optional[CondensedTrends]
    search_results: Optional[str]
    grounded_report: Optional[GroundedReport]
    final_report: Optional[GroundedReport]
    error: Optional[str]
    handoff_history: list
    difficulty_by_role: Optional[dict]
    last_model_selection: Optional[dict]
    use_gpt_researcher: bool
    celery_task_id: Optional[str]


# ---------------------------------------------------------------------------
# Nodes implementation
# ---------------------------------------------------------------------------


def safety_filter_node(state: DeepResearchState) -> dict[str, Any]:
    """Assess whether the input research query is safe."""
    logger.info("--- SAFETY FILTER NODE ---")
    try:
        # Plan difficulties for all research roles up front (planner scores).
        diff_plan = plan_pipeline_difficulties(
            state["query"], pipeline="deep_research"
        )
        difficulty_by_role = assessments_to_state_dict(diff_plan)
        assess = assessment_from_state(
            difficulty_by_role,
            role_short="safety_filter",
            task_text=state["query"],
            role_path="deep_research.safety_filter",
        )
        selection = select_for_role(
            "deep_research", "safety_filter", assessment=assess
        )
        state_for_call = {
            **dict(state),
            "difficulty_by_role": difficulty_by_role,
            **record_model_selection_handoff(
                {**dict(state), "difficulty_by_role": difficulty_by_role},
                selection,
                role="safety_filter",
                user_input_key="query",
                pipeline="deep_research",
                updates={"difficulty_by_role": difficulty_by_role},
            ),
        }

        safety = run_safety_filter(state["query"])
        if safety.is_safe:
            return transfer_control(
                state_for_call,
                from_agent="safety_filter",
                to_agent="context_compressor",
                reason="Query classified safe; proceed to compression",
                pipeline="deep_research",
                user_input_key="query",
                updates={
                    "safety": safety,
                    "error": None,
                    "difficulty_by_role": difficulty_by_role,
                    "last_model_selection": selection.as_dict(),
                },
                require_keys=["safety"],
            )
        return transfer_control(
            state_for_call,
            from_agent="safety_filter",
            to_agent="END",
            reason="Query classified unsafe; terminate pipeline",
            pipeline="deep_research",
            user_input_key="query",
            updates={
                "safety": safety,
                "error": None,
                "difficulty_by_role": difficulty_by_role,
                "last_model_selection": selection.as_dict(),
            },
            require_keys=["safety"],
            note="; ".join(safety.reasons or []) or None,
        )
    except HandoffError:
        raise
    except Exception as exc:
        logger.error("Safety node failed: %s", exc)
        raise exc


def context_compressor_node(state: DeepResearchState) -> dict[str, Any]:
    """Analyze the query to produce keywords/trends."""
    logger.info("--- CONTEXT COMPRESSOR NODE ---")
    try:
        assess = assessment_from_state(
            state.get("difficulty_by_role"),
            role_short="context_compressor",
            task_text=state["query"],
            role_path="deep_research.context_compressor",
        )
        selection = select_for_role(
            "deep_research", "context_compressor", assessment=assess
        )
        state_for_call = {
            **dict(state),
            **record_model_selection_handoff(
                state,
                selection,
                role="context_compressor",
                user_input_key="query",
                pipeline="deep_research",
            ),
        }
        trends = run_context_compressor(state["query"], assessment=assess)
        return transfer_control(
            state_for_call,
            from_agent="context_compressor",
            to_agent="web_search",
            reason="CondensedTrends ready for live web search",
            pipeline="deep_research",
            user_input_key="query",
            updates={
                "trends": trends,
                "error": None,
                "last_model_selection": selection.as_dict(),
            },
            require_keys=["trends"],
        )
    except HandoffError:
        raise
    except Exception as exc:
        logger.error("Context compressor node failed: %s", exc)
        raise exc


def web_search_node(state: DeepResearchState) -> dict[str, Any]:
    """Execute real web search via DuckDuckGo + HTTP page fetches."""
    logger.info("--- WEB SEARCH NODE ---")
    trends = state["trends"]
    if not trends:
        return transfer_control(
            state,
            from_agent="web_search",
            to_agent="END",
            reason="Missing CondensedTrends; abort before ungrounded search",
            pipeline="deep_research",
            user_input_key="query",
            updates={"error": "Missing trends for search."},
        )

    try:
        # Keep the full user topic so search stays entity-anchored (not only
        # compressed keywords that mix similar subjects).
        profile = profile_from_mapping(
            {
                "purpose": getattr(trends, "purpose", None),
                "depth": getattr(trends, "depth", None),
                "data_approach": getattr(trends, "data_approach", None),
                "design": getattr(trends, "design", None),
                "profile_rationale": getattr(trends, "profile_rationale", None),
            }
        )
        logger.info("Research profile: %s", profile.label())
        results = run_web_search(
            trends.technologies,
            original_query=state.get("query") or "",
            research_profile=profile,
        )
        return transfer_control(
            state,
            from_agent="web_search",
            to_agent="grounding",
            reason="Real web search results ready for grounding",
            pipeline="deep_research",
            user_input_key="query",
            updates={"search_results": results, "error": None},
            require_keys=["search_results"],
        )
    except HandoffError:
        raise
    except Exception as exc:
        logger.error("Web search node failed: %s", exc)
        raise exc


def grounding_node(state: DeepResearchState) -> dict[str, Any]:
    """Synthesize web results into grounded assertions with sources."""
    logger.info("--- GROUNDING NODE ---")
    search_results = state["search_results"]
    if not search_results:
    # Covers the case where web_search_node produced no results.
        return transfer_control(
            state,
            from_agent="grounding",
            to_agent="END",
            reason="No search corpus to ground against",
            pipeline="deep_research",
            user_input_key="query",
            updates={
                "error": state.get("error") or "No search results to ground against.",
            },
        )

    try:
        trends = state.get("trends")
        profile = profile_from_mapping(
            {
                "purpose": getattr(trends, "purpose", None) if trends else None,
                "depth": getattr(trends, "depth", None) if trends else None,
                "data_approach": getattr(trends, "data_approach", None) if trends else None,
                "design": getattr(trends, "design", None) if trends else None,
                "profile_rationale": getattr(trends, "profile_rationale", None)
                if trends
                else None,
            }
        )
        grounded = run_grounding(
            state["query"],
            search_results,
            research_profile=profile,
        )
        return transfer_control(
            state,
            from_agent="grounding",
            to_agent="synthesizer",
            reason="GroundedReport with citations ready for synthesis",
            pipeline="deep_research",
            user_input_key="query",
            updates={"grounded_report": grounded, "error": None},
            require_keys=["grounded_report"],
        )
    except HandoffError:
        raise
    except Exception as exc:
        logger.error("Grounding node failed: %s", exc)
        # Fallback: deliver raw search results as-is instead of crashing
        from schemas.deep_research import GroundedReport

        fallback = GroundedReport(
            content=(
                "⚠️ Grounding LLM call failed. Below are the raw web search results "
                "without structured analysis.\n\n"
                f"{search_results[:8000]}"
            ),
            sources=[],
        )
        logger.warning("Grounding failed — delivering raw search results as fallback")
        return transfer_control(
            state,
            from_agent="grounding",
            to_agent="synthesizer",
            reason="Grounding failed — raw search fallback",
            pipeline="deep_research",
            user_input_key="query",
            updates={"grounded_report": fallback, "error": None},
            require_keys=["grounded_report"],
        )


def synthesizer_node(state: DeepResearchState) -> dict[str, Any]:
    """Polishes and structures final document.

    If the synthesizer LLM chain is exhausted, still return the grounded
    draft so /do research is not a total failure after a successful search.
    """
    logger.info("--- SYNTHESIZER NODE ---")
    grounded_report = state["grounded_report"]
    if not grounded_report:
        return transfer_control(
            state,
            from_agent="synthesizer",
            to_agent="END",
            reason="No grounded report to synthesize",
            pipeline="deep_research",
            user_input_key="query",
            updates={
                "error": state.get("error") or "No grounded report to synthesize.",
            },
        )

    try:
        trends = state.get("trends")
        profile = profile_from_mapping(
            {
                "purpose": getattr(trends, "purpose", None) if trends else None,
                "depth": getattr(trends, "depth", None) if trends else None,
                "data_approach": getattr(trends, "data_approach", None) if trends else None,
                "design": getattr(trends, "design", None) if trends else None,
                "profile_rationale": getattr(trends, "profile_rationale", None)
                if trends
                else None,
            }
        )
        final_report = run_synthesizer(
            grounded_report,
            search_results=state.get("search_results", ""),
            query=state.get("query") or "",
            research_profile=profile,
        )
        return transfer_control(
            state,
            from_agent="synthesizer",
            to_agent="END",
            reason="Final report polished; research pipeline complete",
            pipeline="deep_research",
            user_input_key="query",
            updates={"final_report": final_report, "error": None},
            require_keys=["final_report"],
        )
    except HandoffError:
        raise
    except Exception as exc:
        logger.error(
            "Synthesizer failed (%s) — delivering grounded draft instead", exc
        )
        note = (
            "\n\n---\n"
            "*Note: final polish step failed (provider/quota/model cascade). "
            "Showing the grounded research draft above.*\n"
            f"*Detail: {exc}*"
        )
        draft_sources = list(grounded_report.sources or [])
        try:
            from agents.deep_research.source_fetch import is_plausible_source_url

            draft_sources = [s for s in draft_sources if is_plausible_source_url(s)]
        except Exception:
            draft_sources = [
                s
                for s in draft_sources
                if s
                and not s.lower().rstrip("/").endswith(("e.g", "i.e", "u.s", "https://e.g"))
            ]
        draft = GroundedReport(
            content=(grounded_report.content or "") + note,
            sources=draft_sources,
        )
        return transfer_control(
            state,
            from_agent="synthesizer",
            to_agent="END",
            reason="Synthesizer LLM failed; deliver grounded draft",
            pipeline="deep_research",
            user_input_key="query",
            updates={"final_report": draft, "error": None},
            require_keys=["final_report"],
            note=str(exc),
        )


def gpt_researcher_node(state: DeepResearchState) -> dict[str, Any]:
    """Run GPT-Researcher (via Celery or direct) as a LangGraph node.

    Delegates to ``agents.deep_research.gpt_researcher_wrapper.gpt_researcher_node``
    which handles Celery submission, polling with ``await asyncio.sleep(1)``
    for TUI responsiveness, and automatic fallback to direct call when
    Redis/Celery is unavailable.
    """
    import asyncio

    logger.info("--- GPT-RESEARCHER NODE ---")

    async def _run() -> dict[str, Any]:
        from agents.deep_research.gpt_researcher_wrapper import (
            gpt_researcher_node as _wrapper_node,
        )

        result = await _wrapper_node(dict(state))
        return result

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        updates = loop.run_until_complete(_run())
    finally:
        loop.close()

    celery_id = updates.get("celery_task_id")
    report = updates.get("final_report")
    return transfer_control(
        state,
        from_agent="gpt_researcher",
        to_agent="END",
        reason="GPT-Researcher completed (fallback pipeline bypass)",
        pipeline="deep_research",
        user_input_key="query",
        updates={
            "search_results": updates.get("search_results"),
            "grounded_report": report,
            "final_report": report,
            "celery_task_id": celery_id,
            "error": updates.get("error"),
        },
        require_keys=["final_report"],
        note=f"celery_task_id={celery_id}" if celery_id else "direct_call",
    )


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
    (empty search results)."""
    if state.get("error"):
        logger.warning(
            "⚠️ Search step failed/aborted. Terminating pipeline: %s", state["error"]
        )
        return "aborted"
    return "ok"


# ---------------------------------------------------------------------------
# Graph compilation factory
# ---------------------------------------------------------------------------


def get_deep_research_graph(
    db_path: Optional[str] = None,
    use_gpt_researcher: bool = False,
) -> Any:
    """Build and compile the StateGraph for System B.

    When ``use_gpt_researcher=True`` the graph is a single ``gpt_researcher``
    node that delegates to GPT-Researcher (via Celery or direct), bypassing
    the full native pipeline (safety_filter → … → synthesizer).

    Equipped with a persistent SqliteSaver checkpointer.
    """
    db_file = db_path or _DEFAULT_CHECKPOINT_DB
    Path(db_file).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_file, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    checkpointer = SqliteSaver(conn)
    checkpointer.setup()

    workflow = StateGraph(DeepResearchState)

    if use_gpt_researcher:
        workflow.add_node("gpt_researcher", gpt_researcher_node)
        workflow.set_entry_point("gpt_researcher")
        workflow.add_edge("gpt_researcher", END)
        return workflow.compile(checkpointer=checkpointer)

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

    # If web_search produced no results, stop instead of grounding empty data.
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


def initial_deep_research_state(
    topic: str,
    use_gpt_researcher: bool = False,
) -> DeepResearchState:
    """Build a fresh graph state for System B."""
    return {
        "query": topic,
        "safety": None,
        "trends": None,
        "search_results": None,
        "grounded_report": None,
        "final_report": None,
        "error": None,
        "handoff_history": [],
        "difficulty_by_role": None,
        "last_model_selection": None,
        "use_gpt_researcher": use_gpt_researcher,
        "celery_task_id": None,
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
        "celery_task_id": final_state.get("celery_task_id"),
    }


def invoke_deep_research_pipeline(
    topic: str,
    *,
    thread_id: Optional[str] = None,
    db_path: Optional[str] = None,
    graph=None,
    record_history: bool = True,
    use_gpt_researcher: bool = False,
) -> dict[str, Any]:
    """Validate input, run System B (optionally resume), record history.

    When ``use_gpt_researcher=True`` the graph is a single GPT-Researcher node
    (via Celery or direct), bypassing the native LangGraph pipeline.

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
            meta={
                "thread_id": tid,
                "resume": bool(req.thread_id),
                "engine": "gpt_researcher" if use_gpt_researcher else "native",
            },
        )

    compiled = (
        graph
        if graph is not None
        else get_deep_research_graph(db_path=db_path, use_gpt_researcher=use_gpt_researcher)
    )
    config = {"configurable": {"thread_id": tid}}
    inputs: Any = (
        None
        if req.thread_id
        else initial_deep_research_state(req.topic, use_gpt_researcher=use_gpt_researcher)
    )

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
