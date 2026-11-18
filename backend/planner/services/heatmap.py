"""Corridor weather heat map: hourly frames for 0-48 h after departure on the corridor grid."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np

from planner.domain.corridor import CorridorGrid, GridSpec
from planner.domain.errors import InvalidTripRequest, UpstreamUnavailable
from planner.domain.geo import LatLon
from planner.domain.risk import RiskRules
from planner.domain.weather import HOUR, floor_hour

from .weather import WeatherService, utc_now


@dataclass(frozen=True)
class HeatmapConfig:
    hours: int = 48
    max_cells: int = 400
    max_past: timedelta = timedelta(days=2)
    max_ahead: timedelta = timedelta(days=8)


@dataclass(frozen=True, eq=False)
class Heatmap:
    grid: CorridorGrid
    departure: datetime
    start: datetime  # time of frame 0 (top of the departure hour)
    step: timedelta
    wind_mph: np.ndarray  # (frames, cells) — the wind value the risk rules used
    rain_in_hr: np.ndarray
    snow_in_hr: np.ndarray
    risk: np.ndarray  # int8 levels, -1 = unknown
    warnings: list[str]

    @property
    def frame_count(self) -> int:
        return self.risk.shape[0]


class HeatmapService:
    def __init__(
        self,
        weather: WeatherService,
        rules: RiskRules,
        config: HeatmapConfig | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.weather = weather
        self.rules = rules
        self.config = config or HeatmapConfig()
        self.clock = clock

    def build(
        self, spec: GridSpec, cells: np.ndarray, departure: datetime, load_lbs: float
    ) -> Heatmap:
        cells = np.unique(np.asarray(cells, dtype=np.int64))
        self._validate(spec, cells, departure)
        departure = departure.astimezone(UTC)
        start = floor_hour(departure)
        # Enough frames that departure + `hours` is bracketed for interpolation.
        frames = math.ceil((departure + self.config.hours * HOUR - start) / HOUR) + 1

        grid = CorridorGrid(spec=spec, cells=cells, buffer_m=0.0)
        points = [LatLon(float(lat), float(lon)) for lat, lon in grid.centers()]
        data = self.weather.hourly_frames(points, start, frames)
        if np.isnan(data.wind_mph).all():
            raise UpstreamUnavailable(
                "Weather forecasts are currently unavailable for the corridor.",
                details={"reasons": data.warnings},
            )
        wind = data.wind_mph
        if self.rules.wind_basis == "gust":
            wind = np.where(np.isnan(data.gust_mph), data.wind_mph, data.gust_mph)
        return Heatmap(
            grid=grid,
            departure=departure,
            start=start,
            step=HOUR,
            wind_mph=wind,
            rain_in_hr=data.rain_in,
            snow_in_hr=data.snow_in,
            risk=self.rules.classify_many(wind, data.rain_in, data.snow_in, load_lbs),
            warnings=data.warnings,
        )

    def _validate(self, spec: GridSpec, cells: np.ndarray, departure: datetime) -> None:
        if len(cells) == 0:
            raise InvalidTripRequest("The corridor grid has no cells.")
        if len(cells) > self.config.max_cells:
            raise InvalidTripRequest(
                f"The corridor grid may have at most {self.config.max_cells} cells."
            )
        if cells.min() < 0 or cells.max() >= spec.nx * spec.ny:
            raise InvalidTripRequest("Corridor cell index out of range.")
        now = self.clock()
        if not (now - self.config.max_past <= departure <= now + self.config.max_ahead):
            raise InvalidTripRequest("Departure time is outside the forecast window.")
