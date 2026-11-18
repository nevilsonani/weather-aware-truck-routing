"""Cache port. Django's cache objects satisfy this protocol as-is."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Protocol


class Cache(Protocol):
    def get(self, key: str, default: Any = None) -> Any: ...

    def set(self, key: str, value: Any, timeout: float | None = None) -> None: ...

    def get_many(self, keys: Iterable[str]) -> dict[str, Any]: ...

    def set_many(self, data: Mapping[str, Any], timeout: float | None = None) -> Any: ...


class DictCache:
    """In-process cache without expiry, for tests and scripts."""

    def __init__(self) -> None:
        self.store: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self.store.get(key, default)

    def set(self, key: str, value: Any, timeout: float | None = None) -> None:
        self.store[key] = value

    def get_many(self, keys: Iterable[str]) -> dict[str, Any]:
        return {k: self.store[k] for k in keys if k in self.store}

    def set_many(self, data: Mapping[str, Any], timeout: float | None = None) -> list[str]:
        self.store.update(data)
        return []
