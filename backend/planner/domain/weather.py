"""Weather value objects and time-alignment rules.

Hourly forecast semantics (Open-Meteo convention, shared by most NWP products):

* ``wind_mph``  instantaneous value *at* the timestamp, so we interpolate linearly between hours.
* ``gust_mph``, ``rain_in``, ``snow_in``  aggregated over the hour *ending* at the timestamp,
  so the value that applies to an instant ``t`` is the bucket labelled ``ceil(t)``.

Getting this right matters: a truck passing at 10:20 experiences the 10:00-11:00 rain total,
which Open-Meteo labels 11:00, not 10:00.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np

HOUR = timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class WeatherConditions:
    wind_mph: float
    gust_mph: float | None
    rain_in_hr: float
    snow_in_hr: float


@dataclass(frozen=True)
class HourlySeries:
    """Contiguous hourly forecast for one location. ``start`` is a UTC top-of-hour."""

    start: datetime
    wind_mph: np.ndarray
    gust_mph: np.ndarray
    rain_in: np.ndarray
    snow_in: np.ndarray

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.start != floor_hour(self.start):
            raise ValueError("HourlySeries.start must be an aware top-of-hour datetime")

    def __len__(self) -> int:
        return len(self.wind_mph)

    def conditions_at(self, when: datetime) -> WeatherConditions | None:
        """Conditions a vehicle experiences at instant ``when`` (``None`` if not covered)."""
        offset_h = (when - self.start) / HOUR
        lo, hi = math.floor(offset_h), math.ceil(offset_h)
        if lo < 0 or hi >= len(self):
            return None

        frac = offset_h - lo
        wind = (1 - frac) * self.wind_mph[lo] + frac * self.wind_mph[hi]
        rain, snow, gust = self.rain_in[hi], self.snow_in[hi], self.gust_mph[hi]
        if any(math.isnan(v) for v in (wind, rain, snow)):
            return None
        return WeatherConditions(
            wind_mph=float(wind),
            gust_mph=None if math.isnan(gust) else float(gust),
            rain_in_hr=max(0.0, float(rain)),
            snow_in_hr=max(0.0, float(snow)),
        )


def floor_hour(when: datetime) -> datetime:
    return when.replace(minute=0, second=0, microsecond=0)


def ceil_hour(when: datetime) -> datetime:
    floored = floor_hour(when)
    return floored if floored == when else floored + HOUR


def ensure_utc(when: datetime) -> datetime:
    if when.tzinfo is None:
        raise ValueError("Naive datetimes are not allowed inside the planner")
    return when.astimezone(UTC)
