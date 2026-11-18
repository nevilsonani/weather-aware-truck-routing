from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from planner.domain.geo import LatLon
from planner.services.cache import DictCache
from planner.services.weather import WeatherService, WeatherServiceConfig
from tests.fakes import FIXED_NOW, FakeWeatherProvider


def hourly_wind(lat, lon, when):
    """Wind equals the UTC hour, so time alignment is observable."""
    return (float(when.hour), float(when.hour) + 5, 0.0, 0.0)


def make(provider=None, cache=None):
    return WeatherService(
        provider or FakeWeatherProvider(hourly_wind), cache or DictCache(), clock=lambda: FIXED_NOW
    )


def test_conditions_are_sampled_at_each_query_time():
    svc = make()
    when = datetime(2026, 11, 18, 14, 30, tzinfo=UTC)
    (cond,) = svc.conditions_at([(LatLon(39.7, -104.9), when)]).conditions
    assert cond.wind_mph == pytest.approx(14.5)  # interpolated between 14:00 and 15:00


def test_query_spanning_midnight_loads_both_days():
    svc = make()
    when = datetime(2026, 11, 18, 23, 30, tzinfo=UTC)
    (cond,) = svc.conditions_at([(LatLon(39.7, -104.9), when)]).conditions
    assert cond.wind_mph == pytest.approx(11.5)  # halfway between 23 and next day's 0


def test_nearby_points_share_a_lattice_cell_and_cache_is_reused():
    provider = FakeWeatherProvider(hourly_wind)
    cache = DictCache()
    svc = make(provider, cache)
    when = FIXED_NOW + timedelta(hours=1)
    svc.conditions_at([(LatLon(39.701, -104.901), when), (LatLon(39.702, -104.902), when)])
    assert provider.requests == [(1, when.date(), when.date())]

    make(provider, cache).conditions_at([(LatLon(39.701, -104.901), when)])
    assert len(provider.requests) == 1  # served from cache


def test_requests_are_batched_by_date_range():
    provider = FakeWeatherProvider(hourly_wind)
    svc = WeatherService(
        provider, DictCache(), WeatherServiceConfig(batch_size=2), lambda: FIXED_NOW
    )
    when = FIXED_NOW + timedelta(hours=2)
    points = [LatLon(30 + i, -100) for i in range(5)]
    svc.conditions_at([(p, when) for p in points])
    assert sorted(n for n, _, _ in provider.requests) == [1, 2, 2]


def test_points_beyond_forecast_horizon_are_unknown_with_warning():
    provider = FakeWeatherProvider(hourly_wind)
    svc = make(provider)
    far = FIXED_NOW + timedelta(days=20)
    lookup = svc.conditions_at([(LatLon(39.7, -104.9), far)])
    assert lookup.conditions == [None]
    assert "forecast horizon" in lookup.warnings[0]
    assert provider.requests == []


def test_provider_failure_degrades_to_unknown_with_warning():
    svc = make(FakeWeatherProvider(fail=True))
    lookup = svc.conditions_at([(LatLon(39.7, -104.9), FIXED_NOW)])
    assert lookup.conditions == [None]
    assert "fake weather outage" in lookup.warnings[0]


def test_hourly_frames_cover_requested_window():
    svc = make()
    start = datetime(2026, 11, 18, 22, 0, tzinfo=UTC)
    frames = svc.hourly_frames([LatLon(39.7, -104.9), LatLon(41.8, -87.6)], start, 5)
    assert frames.wind_mph.shape == (5, 2)
    assert frames.wind_mph[:, 0].tolist() == [22, 23, 0, 1, 2]
    assert not np.isnan(frames.rain_in).any()


def test_non_utc_instants_are_normalised():
    from zoneinfo import ZoneInfo

    svc = make()
    local = datetime(2026, 11, 18, 7, 30, tzinfo=ZoneInfo("America/Denver"))  # 14:30 UTC
    (cond,) = svc.conditions_at([(LatLon(39.7, -104.9), local)]).conditions
    assert cond.wind_mph == pytest.approx(14.5)


def test_slow_provider_is_cut_off_at_the_deadline():
    import time

    class SlowProvider(FakeWeatherProvider):
        def fetch_days(self, points, start, end):
            time.sleep(2)
            return super().fetch_days(points, start, end)

    svc = WeatherService(
        SlowProvider(hourly_wind),
        DictCache(),
        WeatherServiceConfig(deadline_s=0.2),
        lambda: FIXED_NOW,
    )
    started = time.perf_counter()
    lookup = svc.conditions_at([(LatLon(39.7, -104.9), FIXED_NOW)])
    assert time.perf_counter() - started < 1.5
    assert lookup.conditions == [None]
    assert "too slowly" in lookup.warnings[0]
