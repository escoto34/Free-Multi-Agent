from __future__ import annotations

from celery import Celery

celery_app = Celery(
    "free_multi_agent",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    task_routes={
        "tasks.scraping_tasks.run_scrapy_spider": {"queue": "scrapy"},
        "tasks.scraping_tasks.run_selenium_scrape": {"queue": "default"},
        "tasks.scraping_tasks.run_bulk_scrape": {"queue": "scrapy"},
        "tasks.research_tasks.run_gpt_researcher": {"queue": "research"},
    },
)

import tasks.scraping_tasks  # noqa: E402, F401
import tasks.research_tasks  # noqa: E402, F401
