"""Open-Meteo forecast adapter (https://open-meteo.com/en/docs).

Variable choices matter:

* rain = ``rain`` + ``showers`` (liquid only). ``precipitation`` also contains the water
  equivalent of snowfall, so using it as "rain" would double count snow as rain.
* snow = ``snowfall`` in inches of snow per hour (not water equivalent), which is what the
  in/hr snowfall thresholds in the risk table refer to.
* units are requested in mph / inches, and times as UTC unix timestamps.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any

from planner.domain.errors import UpstreamUnavailable
from planner.domain.geo import LatLon

from ..http import HttpClient, json_or_raise
from .base import HOURS_PER_DAY, DayForecast

HOURLY_VARIABLES = ("wind_speed_10m", "wind_gusts_10m", "rain", "showers", "snowfall")
PUBLIC_URL = "https://api.open-meteo.com/v1/forecast"
CUSTOMER_URL = "https://customer-api.open-meteo.com/v1/forecast"


class OpenMeteoWeatherProvider:
    name = "open-meteo"
    max_forecast_days = 16

    def __init__(self, http: HttpClient, *, base_url: str | None = None, api_key: str = "") -> None:
        self.http = http
        self.api_key = api_key
        self.url = base_url or (CUSTOMER_URL if api_key else PUBLIC_URL)

    def fetch_days(
        self, points: Sequence[LatLon], start: date, end: date
    ) -> list[dict[date, DayForecast]]:
        if not points:
            return []
        params: dict[str, Any] = {
            "latitude": ",".join(f"{p.lat:.4f}" for p in points),
            "longitude": ",".join(f"{p.lon:.4f}" for p in points),
            "hourly": ",".join(HOURLY_VARIABLES),
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timezone": "GMT",
            "timeformat": "unixtime",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        }
        if self.api_key:
            params["apikey"] = self.api_key

        response = self.http.get(self.url, params=params)
        payload = json_or_raise(response, "Open-Meteo")
        if response.status_code >= 400 or (isinstance(payload, dict) and payload.get("error")):
            reason = payload.get("reason", "unknown error") if isinstance(payload, dict) else ""
            raise UpstreamUnavailable(f"Open-Meteo rejected the request: {reason}")

        locations = payload if isinstance(payload, list) else [payload]
        if len(locations) != len(points):
            raise UpstreamUnavailable("Open-Meteo returned an unexpected number of locations")
        return [self._parse_location(loc, start, end) for loc in locations]

    @staticmethod
    def _parse_location(
        location: dict[str, Any], start: date, end: date
    ) -> dict[date, DayForecast]:
        hourly = location.get("hourly") or {}
        series = {name: hourly.get(name) or [] for name in HOURLY_VARIABLES}
        columns: dict[date, dict[str, list[float]]] = {}
        nan_day = [math.nan] * HOURS_PER_DAY

        def value(name: str, i: int) -> float:
            values = series[name]
            v = values[i] if i < len(values) else None
            return math.nan if v is None else float(v)

        for i, ts in enumerate(hourly.get("time", [])):
            moment = datetime.fromtimestamp(ts, tz=UTC)
            day = moment.date()
            if not (start <= day <= end):
                continue
            cols = columns.setdefault(
                day, {k: list(nan_day) for k in ("wind", "gust", "rain", "snow")}
            )
            rain, showers = value("rain", i), value("showers", i)
            cols["wind"][moment.hour] = value("wind_speed_10m", i)
            cols["gust"][moment.hour] = value("wind_gusts_10m", i)
            cols["rain"][moment.hour] = (
                rain if math.isnan(showers) else (showers if math.isnan(rain) else rain + showers)
            )
            cols["snow"][moment.hour] = value("snowfall", i)

        return {
            day: DayForecast(
                wind_mph=tuple(c["wind"]),
                gust_mph=tuple(c["gust"]),
                rain_in=tuple(c["rain"]),
                snow_in=tuple(c["snow"]),
            )
            for day, c in columns.items()
        }
