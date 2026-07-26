from __future__ import annotations

import logging

from itemadapter import ItemAdapter

logger = logging.getLogger(__name__)


class ScrapingPipeline:
    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        url = adapter.get("url", "?")
        logger.debug("Pipeline processed %s", url)
        return item
