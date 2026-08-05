from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from schemas.deep_research import GroundedReport

logger = logging.getLogger(__name__)


async def _run_research_direct(
    query: str,
    report_type: str = "research_report",
    max_sources: int = 15,
) -> dict[str, Any]:
    try:
        from gpt_researcher import GPTResearcher
    except ImportError as exc:
        raise RuntimeError(
            "GPT-Researcher is not installed. Install the optional research "
            "extra with `pip install -e \".[research]\"`."
        ) from exc

    researcher = GPTResearcher(query=query, report_type=report_type)
    report = await researcher.conduct_research()
    sources = list(researcher.get_source_urls() or [])
    return {"content": report, "sources": sources}


async def gpt_researcher_node(
    state: dict[str, Any],
    progress: Optional[Callable[[str], None]] = None,
) -> dict[str, Any]:
    query = state.get("query", "")
    if not query:
        return {"error": "No query provided for GPT-Researcher"}

    _prog = progress or (lambda _: None)
    _prog("GPT-Researcher: ejecución directa (in-process)…")
    result = await _run_research_direct(query)

    report = GroundedReport(
        content=result.get("content", ""),
        sources=result.get("sources", []),
    )

    return {
        "search_results": result.get("content", ""),
        "grounded_report": report,
        "final_report": report,
        "celery_task_id": None,
        "error": None,
    }