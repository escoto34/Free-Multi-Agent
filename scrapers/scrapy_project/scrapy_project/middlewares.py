from __future__ import annotations

import logging

from scrapy import signals
from scrapy.http import HtmlResponse

logger = logging.getLogger(__name__)


class RotateUserAgentMiddleware:
    _DEFAULT_UA = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )

    def process_request(self, request, spider):
        ua = getattr(spider, "user_agent", self._DEFAULT_UA)
        request.headers["User-Agent"] = ua
        return None
