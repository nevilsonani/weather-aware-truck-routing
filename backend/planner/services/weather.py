"""Weather lookups with lattice snapping, per-day caching, batching and graceful degradation.

Cost model: weather APIs bill (and rate limit) per location. A trip can need hundreds of
checkpoint forecasts plus a corridor grid, so this service:

1. snaps points to a ``lattice_deg`` grid (0.05° ≈ 5 km, finer than most forecast models), so
   overlapping routes, repeated plans and the heat map share forecast cells;
2. caches each ``(cell, UTC date)`` independently, so a later plan only fetches missing days;
3. groups missing cells by date range and fetches them in multi-location batches, in parallel;
4. degrades per batch: a failed batch yields ``None`` values plus a warning instead of failing
   the whole trip.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import numpy as np

from planner.domain.errors import UpstreamUnavailable
from planner.domain.geo import LatLon
from planner.domain.weather import HOUR, HourlySeries, WeatherConditions, ceil_hour, floor_hour
from planner.integrations.weather import DayForecast, WeatherProvider

from .cache import Cache

logger = logging.getLogger(__name__)

Cell = tuple[int, int]
DAY = timedelta(days=1)


@dataclass(frozen=True)
class WeatherServiceConfig:
    lattice_deg: float = 0.05
    cache_ttl_s: int = 30 * 60  # forecast models refresh roughly hourly
    batch_size: int = 100
    max_workers: int = 4


@dataclass
class _LoadResult:
    days: dict[tuple[Cell, date], DayForecast] = field(default_factory=dict)
    warnings: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class WeatherLookup:
    conditions: list[WeatherConditions | None]
    warnings: list[str]


@dataclass(frozen=True)
class WeatherFrames:
    """Hourly frames for many points; arrays are ``(hours, points)`` with NaN for missing."""

    start: datetime
    wind_mph: np.ndarray
    gust_mph: np.ndarray
    rain_in: np.ndarray
    snow_in: np.ndarray
    warnings: list[str]


def utc_now() -> datetime:
    return datetime.now(UTC)


class WeatherService:
    def __init__(
        self,
        provider: WeatherProvider,
        cache: Cache,
        config: WeatherServiceConfig | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.provider = provider
        self.cache = cache
        self.config = config or WeatherServiceConfig()
        self.clock = clock

    # --- public API ----------------------------------------------------------------------

    def conditions_at(self, queries: Sequence[tuple[LatLon, datetime]]) -> WeatherLookup:
        """Conditions at each ``(point, instant)``; ``None`` where no forecast is available."""
        queries = [(point, when.astimezone(UTC)) for point, when in queries]
        needs: dict[Cell, set[date]] = defaultdict(set)
        cells = [self._cell(point) for point, _ in queries]
        for cell, (_, when) in zip(cells, queries, strict=True):
            needs[cell].update({floor_hour(when).date(), ceil_hour(when).date()})
        loaded = self._load(needs)

        conditions = []
        for cell, (_, when) in zip(cells, queries, strict=True):
            first, last = floor_hour(when).date(), ceil_hour(when).date()
            series = self._series(loaded.days, cell, first, last)
            conditions.append(series.conditions_at(when))
        return WeatherLookup(conditions, sorted(loaded.warnings))

    def hourly_frames(self, points: Sequence[LatLon], start: datetime, hours: int) -> WeatherFrames:
        """Hourly values from ``start`` (top of hour, UTC) for ``hours`` frames at each point."""
        start = floor_hour(start.astimezone(UTC))
        end = start + (hours - 1) * HOUR
        dates = _date_range(start.date(), end.date())
        cells = [self._cell(p) for p in points]
        loaded = self._load({cell: set(dates) for cell in cells})

        offset = start.hour
        shape = (hours, len(points))
        arrays = {name: np.full(shape, np.nan) for name in ("wind", "gust", "rain", "snow")}
        series_cache: dict[Cell, HourlySeries] = {}
        for column, cell in enumerate(cells):
            if cell not in series_cache:
                series_cache[cell] = self._series(loaded.days, cell, dates[0], dates[-1])
            series = series_cache[cell]
            arrays["wind"][:, column] = series.wind_mph[offset : offset + hours]
            arrays["gust"][:, column] = series.gust_mph[offset : offset + hours]
            arrays["rain"][:, column] = series.rain_in[offset : offset + hours]
            arrays["snow"][:, column] = series.snow_in[offset : offset + hours]
        return WeatherFrames(
            start=start,
            wind_mph=arrays["wind"],
            gust_mph=arrays["gust"],
            rain_in=np.clip(arrays["rain"], 0, None),
            snow_in=np.clip(arrays["snow"], 0, None),
            warnings=sorted(loaded.warnings),
        )

    # --- internals -----------------------------------------------------------------------

    def _cell(self, point: LatLon) -> Cell:
        step = self.config.lattice_deg
        return (round(point.lat / step), round(point.lon / step))

    def _cell_point(self, cell: Cell) -> LatLon:
        step = self.config.lattice_deg
        lat = max(-90.0, min(90.0, cell[0] * step))
        lon = ((cell[1] * step + 180.0) % 360.0) - 180.0
        return LatLon(lat, lon)

    def _cache_key(self, cell: Cell, day: date) -> str:
        return f"wx:{self.provider.name}:{self.config.lattice_deg}:{cell[0]}:{cell[1]}:{day:%Y%m%d}"

    def _series(
        self, days: Mapping[tuple[Cell, date], DayForecast], cell: Cell, first: date, last: date
    ) -> HourlySeries:
        parts = {"wind": [], "gust": [], "rain": [], "snow": []}
        for day in _date_range(first, last):
            record = days.get((cell, day))
            for name, attr in (
                ("wind", "wind_mph"),
                ("gust", "gust_mph"),
                ("rain", "rain_in"),
                ("snow", "snow_in"),
            ):
                parts[name].append(getattr(record, attr) if record else (np.nan,) * 24)
        return HourlySeries(
            start=datetime.combine(first, datetime.min.time(), tzinfo=UTC),
            wind_mph=np.concatenate(parts["wind"]).astype(float),
            gust_mph=np.concatenate(parts["gust"]).astype(float),
            rain_in=np.concatenate(parts["rain"]).astype(float),
            snow_in=np.concatenate(parts["snow"]).astype(float),
        )

    def _load(self, needs: Mapping[Cell, set[date]]) -> _LoadResult:
        result = _LoadResult()
        today = self.clock().astimezone(UTC).date()
        horizon = today + timedelta(days=self.provider.max_forecast_days - 1)

        wanted: dict[tuple[Cell, date], str] = {}
        for cell, dates in needs.items():
            for day in dates:
                if day > horizon:
                    result.warnings.add(
                        "Some checkpoints fall beyond the forecast horizon and have no "
                        "weather data."
                    )
                    continue
                wanted[(cell, day)] = self._cache_key(cell, day)

        cached = self.cache.get_many(list(wanted.values()))
        missing: dict[Cell, list[date]] = defaultdict(list)
        for (cell, day), key in wanted.items():
            if key in cached:
                result.days[(cell, day)] = cached[key]
            else:
                missing[cell].append(day)
        if not missing:
            return result

        jobs = self._plan_jobs(missing)
        logger.info(
            "Weather: %d cell-days cached, fetching %d cells in %d request(s)",
            len(cached),
            len(missing),
            len(jobs),
        )
        to_cache: dict[str, DayForecast] = {}
        with ThreadPoolExecutor(max_workers=min(self.config.max_workers, len(jobs))) as pool:
            futures = [(job, pool.submit(self._fetch, *job)) for job in jobs]
            for (cells, _start, _end), future in futures:
                try:
                    responses = future.result()
                except UpstreamUnavailable as exc:
                    result.warnings.add(f"Weather data partially unavailable: {exc.message}")
                    continue
                for cell, by_day in zip(cells, responses, strict=True):
                    for day, record in by_day.items():
                        result.days[(cell, day)] = record
                        to_cache[self._cache_key(cell, day)] = record
        if to_cache:
            self.cache.set_many(to_cache, timeout=self.config.cache_ttl_s)
        return result

    def _plan_jobs(self, missing: Mapping[Cell, list[date]]) -> list[tuple[list[Cell], date, date]]:
        by_range: dict[tuple[date, date], list[Cell]] = defaultdict(list)
        for cell, days in missing.items():
            by_range[(min(days), max(days))].append(cell)
        size = self.config.batch_size
        return [
            (cells[i : i + size], start, end)
            for (start, end), cells in by_range.items()
            for i in range(0, len(cells), size)
        ]

    def _fetch(self, cells: list[Cell], start: date, end: date) -> list[dict[date, DayForecast]]:
        return self.provider.fetch_days([self._cell_point(c) for c in cells], start, end)


def _date_range(first: date, last: date) -> list[date]:
    return [first + i * DAY for i in range((last - first).days + 1)]
