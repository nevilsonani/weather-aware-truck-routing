from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from planner.domain.weather import HourlySeries, ceil_hour, floor_hour

START = datetime(2026, 11, 18, 0, tzinfo=UTC)


def series(**overrides):
    hours = 6
    data = {
        "wind_mph": np.arange(hours, dtype=float) * 10,  # 0, 10, 20, ...
        "gust_mph": np.arange(hours, dtype=float) * 10 + 5,
        "rain_in": np.array([0.0, 0.1, 0.2, 0.3, 0.4, 0.5]),
        "snow_in": np.zeros(hours),
    }
    data.update(overrides)
    return HourlySeries(start=START, **data)


def test_wind_is_interpolated_between_hours():
    cond = series().conditions_at(START + timedelta(hours=1, minutes=30))
    assert cond.wind_mph == pytest.approx(15.0)


def test_precipitation_uses_the_bucket_ending_after_the_instant():
    # 01:20 lies in the 01:00-02:00 bucket, which Open-Meteo labels 02:00.
    cond = series().conditions_at(START + timedelta(hours=1, minutes=20))
    assert cond.rain_in_hr == pytest.approx(0.2)
    assert cond.gust_mph == pytest.approx(25.0)


def test_exact_hour_uses_that_hours_bucket():
    cond = series().conditions_at(START + timedelta(hours=3))
    assert cond.wind_mph == 30.0
    assert cond.rain_in_hr == pytest.approx(0.3)


def test_out_of_range_or_missing_values_return_none():
    s = series()
    assert s.conditions_at(START - timedelta(minutes=1)) is None
    assert s.conditions_at(START + timedelta(hours=5, minutes=1)) is None
    gappy = series(rain_in=np.array([0.0, np.nan, 0.0, 0.0, 0.0, 0.0]))
    assert gappy.conditions_at(START + timedelta(minutes=30)) is None


def test_missing_gust_is_tolerated():
    s = series(gust_mph=np.full(6, np.nan))
    assert s.conditions_at(START + timedelta(hours=2)).gust_mph is None


def test_series_requires_top_of_hour_utc_start():
    with pytest.raises(ValueError, match="top-of-hour"):
        HourlySeries(START + timedelta(minutes=5), *(np.zeros(2),) * 4)


def test_hour_rounding_helpers():
    t = datetime(2026, 1, 1, 10, 20, tzinfo=UTC)
    assert floor_hour(t).hour == 10
    assert ceil_hour(t).hour == 11
    assert ceil_hour(floor_hour(t)) == floor_hour(t)
