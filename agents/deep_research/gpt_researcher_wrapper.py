from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

from schemas.deep_research import GroundedReport

logger = logging.getLogger(__name__)


async def _run_research_direct(
    query: str,
    report_type: str = "research_report",
    max_sources: int = 15,
) -> dict[str, Any]:
    from gpt_researcher import GPTResearcher

    researcher = GPTResearcher(query=query, report_type=report_type)
    report = await researcher.conduct_research()
    sources = list(researcher.get_source_urls() or [])
    return {"content": report, "sources": sources}


def _run_research_in_new_loop(query: str) -> dict[str, Any]:
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_run_research_direct(query))
    finally:
        loop.close()


async def gpt_researcher_node(
    state: dict[str, Any],
    progress: Optional[Callable[[str], None]] = None,
) -> dict[str, Any]:
    query = state.get("query", "")
    if not query:
        return {"error": "No query provided for GPT-Researcher"}

    _prog = progress or (lambda _: None)
    celery_task_id: Optional[str] = None

    try:
        from tasks.research_tasks import run_gpt_researcher

        task = run_gpt_researcher.delay(query=query)
        celery_task_id = task.id
        _prog(f"GPT-Researcher: task {celery_task_id[:8]}… enviada")

        while not task.ready():
            status = task.state
            _prog(f"GPT-Researcher: {status} (task {celery_task_id[:8]}…)")
            await asyncio.sleep(0.1)

        result = task.result
        if not result or not result.get("content"):
            raise RuntimeError("GPT-Researcher returned empty result")

        logger.info(
            "GPT-Researcher via Celery OK: %d chars, %d sources",
            len(result["content"]),
            len(result.get("sources", [])),
        )

    except (ImportError, ConnectionError, Exception) as exc:
        logger.warning(
            "Celery/GPT-Researcher unavailable (%s). Falling back to direct call.",
            exc,
        )
        _prog(f"⚠️ Celery no disponible ({exc}). Ejecutando GPT-Researcher directo…")
        result = await _run_research_direct(query)

    report = GroundedReport(
        content=result.get("content", ""),
        sources=result.get("sources", []),
    )

    return {
        "search_results": result.get("content", ""),
        "grounded_report": report,
        "final_report": report,
        "celery_task_id": celery_task_id,
        "error": None,
    }
