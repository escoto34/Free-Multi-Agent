from __future__ import annotations

import contextlib
import logging
from typing import Any, Iterator, Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.remote.webdriver import WebDriver

logger = logging.getLogger(__name__)

_DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


@contextlib.contextmanager
def headless_chromium(
    *,
    user_agent: Optional[str] = None,
    proxy: Optional[str] = None,
    page_load_timeout: float = 30,
    window_size: tuple[int, int] = (1920, 1080),
) -> Iterator[WebDriver]:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument(f"--user-agent={user_agent or _DEFAULT_UA}")
    options.add_argument(f"--window-size={window_size[0]}x{window_size[1]}")
    if proxy:
        options.add_argument(f"--proxy-server={proxy}")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    prefs = {
        "profile.default_content_setting_values.notifications": 2,
        "credentials_enable_service": False,
    }
    options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(page_load_timeout)
    try:
        yield driver
    finally:
        try:
            driver.quit()
        except Exception:
            logger.exception("Selenium driver cleanup failed")


def render_page(url: str, **kwargs: Any) -> str:
    with headless_chromium(**kwargs) as driver:
        driver.get(url)
        return driver.page_source
