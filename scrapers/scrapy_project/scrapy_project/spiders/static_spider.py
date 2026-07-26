from __future__ import annotations

from typing import Any, Optional

import scrapy
from scrapy.http import Response

from scrapers.scrapy_project.scrapy_project.items import WebPageItem


class StaticSpider(scrapy.Spider):
    name = "static"

    def __init__(
        self,
        start_urls: Optional[list[str]] = None,
        allowed_domains: Optional[list[str]] = None,
        extract_rules: Optional[list[dict[str, str]]] = None,
        max_pages: int = 50,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        if start_urls:
            self.start_urls = start_urls
        if allowed_domains:
            self.allowed_domains = allowed_domains
        self.extract_rules = extract_rules or []
        self.max_pages = max_pages
        self._pages_seen = 0

    def parse(self, response: Response, **kwargs: Any) -> Any:
        if self._pages_seen >= self.max_pages:
            return
        self._pages_seen += 1

        item = WebPageItem(
            url=response.url,
            title=response.css("title::text").get("").strip(),
            content=" ".join(response.css("p::text, li::text, h1::text, h2::text, h3::text").getall()),
            html=response.text,
            links=response.css("a::attr(href)").getall(),
            headers=dict(response.headers),
            status=response.status,
        )
        yield item

        follow_links = any(
            rule.get("follow", "true").lower() == "true"
            for rule in self.extract_rules
        )
        if follow_links:
            for href in response.css("a::attr(href)").getall():
                yield response.follow(href, callback=self.parse)
