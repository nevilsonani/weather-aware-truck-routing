import numpy as np
import pytest

from planner.domain import geo
from planner.domain.geo import LatLon
from planner.domain.route import IndexSpan, build_route, distribute_span_durations, overlap_fraction
from tests.fakes import straight_route


def test_span_durations_are_spread_by_segment_length():
    durations = distribute_span_durations(
        np.array([100.0, 300.0, 50.0, 50.0]), [IndexSpan(0, 2, 40.0), IndexSpan(2, 4, 10.0)]
    )
    assert durations.tolist() == pytest.approx([10.0, 30.0, 5.0, 5.0])


def test_build_route_scales_distance_to_provider_length_and_maps_roads():
    coords = np.column_stack((np.linspace(39, 40, 11), np.full(11, -105.0)))
    geometric = float(geo.cumulative_distance_m(coords)[-1])
    route = build_route(
        provider="t",
        coords=coords,
        segment_durations_s=np.full(10, 60.0),
        reported_distance_m=geometric * 1.01,
        named_spans=[
            IndexSpan(0, 4, 0, "US-6"),
            IndexSpan(4, 10, 0, "I-25"),
            IndexSpan(3, 3, 0, "x"),
        ],
    )
    assert route.distance_m == pytest.approx(geometric * 1.01)
    assert route.driving_s == 600
    assert route.road_at(route.distance_m * 0.1) == "US-6"
    assert route.road_at(route.distance_m * 0.9) == "I-25"
    assert route.major_roads(2) == ["US-6", "I-25"]  # listed in driving order


def test_time_and_distance_interpolation_are_inverse():
    route = straight_route([LatLon(40, -100), LatLon(40, -99)], speed_mps=20)
    d = np.array([0.0, 1234.0, route.distance_m])
    assert route.distance_at_driving_time(route.driving_time_at(d)) == pytest.approx(d)


def test_overlap_fraction_identical_disjoint_and_partial():
    a = straight_route([LatLon(40, -100), LatLon(40, -98)])
    far = straight_route([LatLon(41, -100), LatLon(41, -98)])
    half = straight_route([LatLon(40, -100), LatLon(40, -99), LatLon(41, -99)])
    assert overlap_fraction(a, a) == pytest.approx(1.0)
    assert overlap_fraction(a, far) == 0.0
    assert overlap_fraction(a, half) == pytest.approx(0.5, abs=0.05)
