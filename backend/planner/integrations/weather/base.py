from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from planner.domain.geo import LatLon

HOURS_PER_DAY = 24


@dataclass(frozen=True, slots=True)
class DayForecast:
    """Hourly values for one location on one UTC date (index = UTC hour, NaN = missing).

    Units: wind & gust in mph; rain & snow are the accumulation of the *preceding* hour in
    inches, i.e. the average rate in in/hr over that hour.
    """

    wind_mph: tuple[float, ...]
    gust_mph: tuple[float, ...]
    rain_in: tuple[float, ...]
    snow_in: tuple[float, ...]


class WeatherProvider(Protocol):
    name: str
    max_forecast_days: int  # days ahead (including today, UTC) the provider can serve

    def fetch_days(
        self, points: Sequence[LatLon], start: date, end: date
    ) -> list[dict[date, DayForecast]]:
        """Hourly forecasts for every point and every UTC date in ``[start, end]``.

        Returns one mapping per input point, in input order.

        Raises:
            UpstreamUnavailable: the provider failed or rate limited the request.
        """
        ...
