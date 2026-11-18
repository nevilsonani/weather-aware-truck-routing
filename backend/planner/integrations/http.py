"""Shared HTTP plumbing for third-party adapters: pooled sessions, retries, timeouts, logging."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from planner.domain.errors import UpstreamUnavailable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HttpConfig:
    user_agent: str = "weather-aware-truck-routing/1.0"
    connect_timeout_s: float = 5.0
    read_timeout_s: float = 30.0
    retries: int = 2
    backoff_factor: float = 0.4
    pool_size: int = 16


class HttpClient:
    """Thin wrapper over a pooled ``requests.Session``.

    Connection failures and 502/503/504 are retried with exponential backoff. Read timeouts
    are *not* retried (a slow upstream would only multiply the wait), and neither is 429:
    rate limits need a longer pause than a request should block for, so callers degrade.
    """

    def __init__(self, service: str, config: HttpConfig | None = None) -> None:
        self.service = service
        self.config = config or HttpConfig()
        retry = Retry(
            total=self.config.retries,
            read=0,
            backoff_factor=self.config.backoff_factor,
            status_forcelist=(502, 503, 504),
            allowed_methods=frozenset({"GET", "POST"}),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(
            max_retries=retry,
            pool_connections=self.config.pool_size,
            pool_maxsize=self.config.pool_size,
        )
        self.session = requests.Session()
        self.session.headers["User-Agent"] = self.config.user_agent
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", (self.config.connect_timeout_s, self.config.read_timeout_s))
        started = time.perf_counter()
        try:
            response = self.session.request(method, url, **kwargs)
        except requests.RequestException as exc:
            logger.warning("%s request failed: %s", self.service, exc)
            raise UpstreamUnavailable(f"{self.service} is unreachable") from exc
        logger.info(
            "%s %s %s -> %s in %.0f ms",
            self.service,
            method,
            url.split("?")[0],
            response.status_code,
            (time.perf_counter() - started) * 1000,
        )
        return response

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("POST", url, **kwargs)


def json_or_raise(response: requests.Response, service: str) -> Any:
    if response.status_code == 429:
        raise UpstreamUnavailable(f"{service} rate limit reached, please retry shortly")
    if response.status_code >= 500:
        raise UpstreamUnavailable(f"{service} returned HTTP {response.status_code}")
    try:
        return response.json()
    except ValueError as exc:
        raise UpstreamUnavailable(f"{service} returned an invalid response") from exc
