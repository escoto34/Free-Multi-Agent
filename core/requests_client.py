from __future__ import annotations

import logging
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = (30, 90)
_MAX_RETRIES = 3
_BACKOFF_FACTOR = 0.5
_RETRY_STATUSES = {429, 502, 503, 504}


class RequestsClient:
    def __init__(self, timeout: tuple[int, int] = _DEFAULT_TIMEOUT) -> None:
        self._session = requests.Session()
        retry = Retry(
            total=_MAX_RETRIES,
            read=_MAX_RETRIES,
            connect=_MAX_RETRIES,
            backoff_factor=_BACKOFF_FACTOR,
            status_forcelist=_RETRY_STATUSES,
            allowed_methods={"GET", "POST", "PUT", "DELETE", "HEAD"},
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=40)
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)
        self._timeout = timeout

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", self._timeout)
        return self._session.get(url, **kwargs)

    def post(
        self, url: str, json: Optional[dict] = None, **kwargs: Any
    ) -> requests.Response:
        kwargs.setdefault("timeout", self._timeout)
        return self._session.post(url, json=json, **kwargs)

    def close(self) -> None:
        self._session.close()


_client: Optional[RequestsClient] = None


def get_client() -> RequestsClient:
    global _client
    if _client is None:
        _client = RequestsClient()
    return _client


def quick_webhook(url: str, payload: dict, *, timeout: int = 15) -> bool:
    try:
        resp = get_client().post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        logger.info("Webhook %s delivered (status=%d)", url, resp.status_code)
        return True
    except requests.RequestException as exc:
        logger.warning("Webhook %s failed: %s", url, exc)
        return False


def reset_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
