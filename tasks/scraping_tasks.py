from __future__ import annotations

import logging
import os
from typing import Any, Optional

from celery import Task

from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, acks_late=True, queue="scrapy")
def run_scrapy_spider(
    self: Task,
    spider_name: str = "static",
    start_urls: Optional[list[str]] = None,
    allowed_domains: Optional[list[str]] = None,
    extract_rules: Optional[list[dict[str, str]]] = None,
    config_overrides: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    from scrapy.crawler import CrawlerRunner
    from scrapy.utils.log import configure_logging
    from scrapy.utils.project import get_project_settings
    from twisted.internet import reactor

    settings = get_project_settings()
    if config_overrides:
        settings.update(dict(config_overrides))

    os.environ.setdefault(
        "SCRAPY_SETTINGS_MODULE",
        "scrapers.scrapy_project.scrapy_project.settings",
    )

    configure_logging(settings)

    runner = CrawlerRunner(settings)
    crawl_kwargs: dict[str, Any] = {}
    if start_urls:
        crawl_kwargs["start_urls"] = start_urls
    if allowed_domains:
        crawl_kwargs["allowed_domains"] = allowed_domains
    if extract_rules:
        crawl_kwargs["extract_rules"] = extract_rules

    deferred = runner.crawl(spider_name, **crawl_kwargs)
    deferred.addBoth(lambda _: reactor.stop())
    if not reactor.running:
        reactor.run()
    else:
        reactor.crash()
        reactor.stop()

    items = getattr(runner, "items", [])
    return {"spider": spider_name, "items_count": len(items), "items": items}


@celery_app.task(bind=True, max_retries=2, acks_late=True, queue="default")
def run_selenium_scrape(
    self: Task,
    url: str,
    wait_for_selector: Optional[str] = None,
    screenshot: bool = False,
    extract_links: bool = False,
    page_load_timeout: float = 30,
) -> dict[str, Any]:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    from tools.selenium_driver import headless_chromium

    with headless_chromium(page_load_timeout=page_load_timeout) as driver:
        driver.get(url)
        if wait_for_selector:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, wait_for_selector))
            )
        result: dict[str, Any] = {
            "url": url,
            "title": driver.title,
            "html": driver.page_source,
        }
        if screenshot:
            png = driver.get_screenshot_as_base64()
            result["screenshot_b64"] = png
        if extract_links:
            links = [
                e.get_attribute("href")
                for e in driver.find_elements(By.CSS_SELECTOR, "a[href]")
            ]
            result["links"] = [l for l in links if l]
        return result


@celery_app.task(bind=True, max_retries=2, acks_late=True, queue="scrapy")
def run_bulk_scrape(
    self: Task,
    urls: list[str],
    strategy: str = "scrapy",
    allowed_domains: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for url in urls:
        try:
            if strategy == "selenium":
                res = run_selenium_scrape.delay(url=url).get(timeout=120)
            else:
                res = run_scrapy_spider.delay(
                    start_urls=[url],
                    allowed_domains=allowed_domains or [],
                ).get(timeout=120)
            results.append(res)
        except Exception as exc:
            logger.error("Bulk scrape failed for %s: %s", url, exc)
            results.append({"url": url, "error": str(exc)})
    return results
