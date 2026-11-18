from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from planner.domain.checkpoints import checkpoint_distances, coverage_bounds, sample_checkpoints
from planner.domain.geo import LatLon
from planner.domain.hos import DrivingSchedule, HosPolicy
from planner.domain.units import METERS_PER_MILE, meters_to_miles
from tests.fakes import straight_route

MI = METERS_PER_MILE


def miles(values):
    return [round(meters_to_miles(v), 3) for v in values]


def test_checkpoints_every_interval_plus_destination():
    assert miles(checkpoint_distances(100.4 * MI, 25 * MI)) == [0, 25, 50, 75, 100.4]
    assert miles(checkpoint_distances(110 * MI, 25 * MI)) == [0, 25, 50, 75, 100, 110]


def test_regular_checkpoint_too_close_to_destination_is_dropped():
    # 100 and 100.5 would be two overlapping markers; keep only the destination.
    assert miles(checkpoint_distances(100.5 * MI, 25 * MI)) == [0, 25, 50, 75, 100.5]


def test_route_shorter_than_interval_has_origin_and_destination():
    assert miles(checkpoint_distances(8 * MI, 25 * MI)) == [0, 8]


def test_exact_multiple_does_not_duplicate_destination():
    assert miles(checkpoint_distances(50 * MI, 10 * MI)) == [0, 10, 20, 30, 40, 50]


def test_invalid_inputs_are_rejected():
    with pytest.raises(ValueError, match="positive"):
        checkpoint_distances(0, 10)


def test_coverage_uses_midpoints_and_sums_to_route_length():
    distances = np.array([0, 25, 50, 60]) * MI
    starts, ends = coverage_bounds(distances)
    assert miles(starts) == [0, 12.5, 37.5, 55]
    assert miles(ends) == [12.5, 37.5, 55, 60]
    assert (ends - starts).sum() == pytest.approx(60 * MI)


def test_sampled_checkpoints_carry_position_eta_and_road():
    route = straight_route([LatLon(39.0, -105.0), LatLon(39.0, -100.0)], speed_mps=25.0)
    departure = datetime(2026, 11, 18, 8, tzinfo=UTC)
    schedule = DrivingSchedule(route.driving_s, HosPolicy())
    checkpoints = sample_checkpoints(route, 50 * MI, departure, schedule)

    assert checkpoints[0].distance_m == 0
    assert checkpoints[0].eta == departure
    assert checkpoints[-1].distance_m == pytest.approx(route.distance_m)
    assert checkpoints[1].eta == departure + timedelta(seconds=50 * MI / 25.0)
    assert all(cp.road == "I-80" for cp in checkpoints)
    assert sum(cp.coverage_m for cp in checkpoints) == pytest.approx(route.distance_m)
    # positions advance eastwards along the straight line
    lons = [cp.position.lon for cp in checkpoints]
    assert lons == sorted(lons)


def test_checkpoint_etas_include_hos_stops():
    # 40 mph over ~600 miles: ~15 h of driving, so later checkpoints sit behind a 10 h rest.
    route = straight_route([LatLon(40.0, -110.0), LatLon(40.0, -98.7)], speed_mps=17.88)
    departure = datetime(2026, 11, 18, 0, tzinfo=UTC)
    with_hos = sample_checkpoints(
        route, 50 * MI, departure, DrivingSchedule(route.driving_s, HosPolicy())
    )
    without = sample_checkpoints(
        route, 50 * MI, departure, DrivingSchedule(route.driving_s, HosPolicy.disabled())
    )
    gap = (with_hos[-1].eta - without[-1].eta).total_seconds() / 3600
    assert gap == pytest.approx(10.5)
    assert with_hos[1].eta == without[1].eta  # before any stop the ETAs agree
