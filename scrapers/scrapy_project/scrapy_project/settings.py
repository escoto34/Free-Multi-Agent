BOT_NAME = "scrapy_project"

SPIDER_MODULES = ["scrapers.scrapy_project.scrapy_project.spiders"]
NEWSPIDER_MODULE = "scrapers.scrapy_project.scrapy_project.spiders"

ROBOTSTXT_OBEY = False
CONCURRENT_REQUESTS = 16
DOWNLOAD_DELAY = 0.5
RANDOMIZE_DOWNLOAD_DELAY = True

DOWNLOADER_MIDDLEWARES = {
    "scrapers.scrapy_project.scrapy_project.middlewares.RotateUserAgentMiddleware": 543,
}

ITEM_PIPELINES = {
    "scrapers.scrapy_project.scrapy_project.pipelines.ScrapingPipeline": 300,
}

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
