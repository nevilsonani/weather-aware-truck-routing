"""In-memory test doubles for the integration ports."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta

import numpy as np

from planner.domain import geo
from planner.domain.errors import UpstreamUnavailable
from planner.domain.geo import LatLon
from planner.domain.route import DrivingRoute, IndexSpan, build_route
from planner.integrations.geocoding import Place
from planner.integrations.routing import VehicleProfile
from planner.integrations.weather import DayForecast

FIXED_NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)


def straight_route(
    points: Sequence[LatLon],
    *,
    speed_mps: float = 26.8,  # ~60 mph
    vertices_per_leg: int = 50,
    provider: str = "fake",
    road: str = "I-80",
) -> DrivingRoute:
    """A route through ``points`` along straight lines at constant speed."""
    legs = [
        np.column_stack(
            (
                np.linspace(a.lat, b.lat, vertices_per_leg),
                np.linspace(a.lon, b.lon, vertices_per_leg),
            )
        )
        for a, b in zip(points[:-1], points[1:], strict=True)
    ]
    coords = np.concatenate([legs[0], *[leg[1:] for leg in legs[1:]]])
    seg = geo.segment_lengths_m(coords)
    return build_route(
        provider=provider,
        coords=coords,
        segment_durations_s=seg / speed_mps,
        named_spans=[IndexSpan(0, len(coords) - 1, 0.0, road)],
    )


class FakeRoutingProvider:
    """Returns straight-line routes; ``native_alternatives`` controls how many it offers."""

    def __init__(
        self,
        *,
        name: str = "fake",
        native_alternatives: int = 0,
        fail_with: Exception | None = None,
        speed_mps: float = 26.8,
    ) -> None:
        self.name = name
        self.native_alternatives = native_alternatives
        self.fail_with = fail_with
        self.speed_mps = speed_mps
        self.calls: list[tuple[list[LatLon], int]] = []

    def route(
        self, waypoints: Sequence[LatLon], vehicle: VehicleProfile, *, alternatives: int = 0
    ) -> list[DrivingRoute]:
        self.calls.append((list(waypoints), alternatives))
        if self.fail_with:
            raise self.fail_with
        routes = [straight_route(waypoints, speed_mps=self.speed_mps, provider=self.name)]
        if len(waypoints) == 2:
            a, b = waypoints
            for k in range(min(alternatives, self.native_alternatives)):
                bend = geo.destination_point(
                    LatLon((a.lat + b.lat) / 2, (a.lon + b.lon) / 2), 0, 40_000 * (k + 1)
                )
                routes.append(
                    straight_route(
                        [a, bend, b],
                        speed_mps=self.speed_mps,
                        provider=self.name,
                        road=f"US-{k + 1}",
                    )
                )
        return routes


WeatherFn = Callable[[float, float, datetime], tuple[float, float, float, float]]


def calm_weather(lat: float, lon: float, when: datetime) -> tuple[float, float, float, float]:
    return (5.0, 8.0, 0.0, 0.0)


class FakeWeatherProvider:
    """Serves hourly values from ``fn(lat, lon, utc_time) -> (wind, gust, rain, snow)``."""

    name = "fake-weather"
    max_forecast_days = 16

    def __init__(self, fn: WeatherFn = calm_weather, *, fail: bool = False) -> None:
        self.fn = fn
        self.fail = fail
        self.requests: list[tuple[int, date, date]] = []

    def fetch_days(
        self, points: Sequence[LatLon], start: date, end: date
    ) -> list[dict[date, DayForecast]]:
        self.requests.append((len(points), start, end))
        if self.fail:
            raise UpstreamUnavailable("fake weather outage")
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        out = []
        for p in points:
            per_day = {}
            for day in days:
                values = [
                    self.fn(p.lat, p.lon, datetime(day.year, day.month, day.day, h, tzinfo=UTC))
                    for h in range(24)
                ]
                per_day[day] = DayForecast(
                    wind_mph=tuple(v[0] for v in values),
                    gust_mph=tuple(v[1] for v in values),
                    rain_in=tuple(v[2] for v in values),
                    snow_in=tuple(v[3] for v in values),
                )
            out.append(per_day)
        return out


class FakeGeocoder:
    name = "fake-geocoder"

    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, query: str, *, limit: int, bias: LatLon | None = None) -> list[Place]:
        self.queries.append(query)
        return [
            Place(
                id="1",
                name=query.title(),
                label=f"{query.title()}, Colorado, United States",
                position=LatLon(39.7392, -104.9903),
                kind="city",
                country_code="US",
            )
        ][:limit]
