from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from celery import Task

from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=2, acks_late=True, queue="research")
def run_gpt_researcher(
    self: Task,
    query: str,
    report_type: str = "research_report",
    max_sources: int = 15,
    config_path: Optional[str] = None,
) -> dict[str, Any]:
    logger.info("GPT-Researcher task started: query=%s", query[:120])

    async def _run() -> dict[str, Any]:
        from gpt_researcher import GPTResearcher

        researcher = GPTResearcher(
            query=query,
            report_type=report_type,
            config_path=config_path,
        )
        report = await researcher.conduct_research()
        sources = list(researcher.get_source_urls() or [])
        return {"content": report, "sources": sources}

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_run())
        logger.info(
            "GPT-Researcher completed: content=%d chars, sources=%d",
            len(result.get("content", "")),
            len(result.get("sources", [])),
        )
        return result
    except ImportError as exc:
        logger.error("gpt-researcher not installed: %s", exc)
        raise
    except Exception as exc:
        logger.error("GPT-Researcher failed: %s", exc)
        raise
    finally:
        loop.close()
