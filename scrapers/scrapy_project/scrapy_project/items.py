from __future__ import annotations

import scrapy
from scrapy.item import Field, Item


class WebPageItem(Item):
    url = Field()
    title = Field()
    content = Field()
    html = Field()
    links = Field()
    headers = Field()
    status = Field()
