"""Offline coordinate -> IANA time-zone lookup (no network call, ~2 µs per lookup)."""

from __future__ import annotations

import threading
from functools import cached_property

from timezonefinder import TimezoneFinder


class TimezoneResolver:
    def __init__(self, default: str = "UTC") -> None:
        self.default = default
        self._lock = threading.Lock()

    @cached_property
    def _finder(self) -> TimezoneFinder:
        return TimezoneFinder()

    def timezone_at(self, lat: float, lon: float) -> str:
        with self._lock:
            name = self._finder.timezone_at(lat=lat, lng=lon)
        return name or self.default
