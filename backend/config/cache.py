"""Redis cache that degrades to "cache miss" instead of failing requests.

The cache is an optimisation: if Redis restarts, is unreachable or times out, trip planning
and rate limiting must keep working (slower, uncached), never return a 500. Django's built-in
Redis backend raises on every connection error, so each operation is guarded here.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.core.cache.backends.redis import RedisCache
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)
T = TypeVar("T")


class ResilientRedisCache(RedisCache):
    @staticmethod
    def _guard(operation: str, call: Callable[[], T], fallback: T) -> T:
        try:
            return call()
        except (RedisError, OSError) as exc:
            logger.warning("Cache %s failed; continuing without cache: %s", operation, exc)
            return fallback

    def get(self, key, default=None, version=None) -> Any:
        return self._guard("get", lambda: RedisCache.get(self, key, default, version), default)

    def get_many(self, keys, version=None) -> dict[str, Any]:
        return self._guard("get_many", lambda: RedisCache.get_many(self, keys, version), {})

    def set(self, key, value, timeout=DEFAULT_TIMEOUT, version=None) -> None:
        self._guard("set", lambda: RedisCache.set(self, key, value, timeout, version), None)

    def set_many(self, data, timeout=DEFAULT_TIMEOUT, version=None) -> list:
        return self._guard(
            "set_many", lambda: RedisCache.set_many(self, data, timeout, version), []
        )

    def add(self, key, value, timeout=DEFAULT_TIMEOUT, version=None) -> bool:
        return self._guard("add", lambda: RedisCache.add(self, key, value, timeout, version), False)

    def delete(self, key, version=None) -> bool:
        return self._guard("delete", lambda: RedisCache.delete(self, key, version), False)

    def has_key(self, key, version=None) -> bool:
        return self._guard("has_key", lambda: RedisCache.has_key(self, key, version), False)
