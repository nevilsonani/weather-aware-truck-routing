import numpy as np
import pytest

from planner.domain import geo
from planner.domain.geo import LatLon


def test_decode_reference_polyline():
    # Example from Google's polyline algorithm documentation (precision 5).
    coords = geo.decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@", precision=5)
    expected = [[38.5, -120.2], [40.7, -120.95], [43.252, -126.453]]
    assert np.allclose(coords, expected)


def test_encode_decode_roundtrip_precision_6():
    rng = np.random.default_rng(1)
    coords = np.column_stack((rng.uniform(-60, 60, 200), rng.uniform(-179, 179, 200)))
    decoded = geo.decode_polyline(geo.encode_polyline(coords, 6), 6)
    assert np.allclose(decoded, coords, atol=1e-6)


def test_truncated_polyline_raises():
    with pytest.raises(ValueError, match="Truncated"):
        geo.decode_polyline("_p~iF~ps|U_", precision=5)


def test_haversine_known_distance():
    denver, chicago = LatLon(39.7392, -104.9903), LatLon(41.8781, -87.6298)
    assert geo.distance_m(denver, chicago) == pytest.approx(1_480_000, rel=0.01)


def test_destination_point_inverts_bearing_and_distance():
    origin = LatLon(39.0, -105.0)
    target = geo.destination_point(origin, 75.0, 120_000)
    assert geo.distance_m(origin, target) == pytest.approx(120_000, rel=1e-6)
    assert geo.initial_bearing_deg(origin, target) == pytest.approx(75.0, abs=1e-6)


def test_latlon_validates_ranges():
    with pytest.raises(ValueError, match="out of range"):
        LatLon(91, 0)


def test_resample_includes_endpoints_and_is_evenly_spaced():
    line = np.array([[0.0, 0.0], [0.0, 1.0]])
    cum = geo.cumulative_distance_m(line)
    points = geo.resample(line, cum, 10_000)
    steps = geo.segment_lengths_m(points)
    assert points[0].tolist() == [0, 0] and points[-1].tolist() == [0, 1]
    assert steps.max() <= 10_000 and np.allclose(steps, steps[0])


def test_mercator_roundtrip():
    lats = np.array([-80.0, -33.3, 0.0, 45.5, 84.0])
    assert np.allclose(geo.inverse_mercator_y(geo.mercator_y(lats)), lats)


def _reference_douglas_peucker(coords, tolerance):
    n = len(coords)
    lat0 = np.radians(coords[:, 0].mean())
    xy = np.column_stack((np.radians(coords[:, 1]) * np.cos(lat0), np.radians(coords[:, 0])))
    xy *= geo.EARTH_RADIUS_M
    keep = np.zeros(n, bool)
    keep[[0, n - 1]] = True
    stack = [(0, n - 1)]
    while stack:
        s, e = stack.pop()
        if e - s < 2:
            continue
        chord, rel = xy[e] - xy[s], xy[s + 1 : e] - xy[s]
        length = np.hypot(*chord)
        d = (
            np.abs(chord[0] * rel[:, 1] - chord[1] * rel[:, 0]) / length
            if length
            else np.hypot(rel[:, 0], rel[:, 1])
        )
        i = int(np.argmax(d))
        if d[i] > tolerance:
            keep[s + 1 + i] = True
            stack += [(s, s + 1 + i), (s + 1 + i, e)]
    return coords[keep]


@pytest.mark.parametrize("tolerance", [5, 25, 200])
def test_vectorised_simplify_matches_classic_douglas_peucker(tolerance):
    rng = np.random.default_rng(7)
    walk = rng.normal(0, 0.002, (3_000, 2)).cumsum(axis=0) + [39.7, -104.9]
    assert np.array_equal(
        geo.simplify(walk, tolerance), _reference_douglas_peucker(walk, tolerance)
    )


def test_simplify_collapses_straight_line_and_keeps_endpoints():
    line = np.column_stack((np.linspace(39, 40, 500), np.linspace(-105, -104, 500)))
    simplified = geo.simplify(line, 1.0)
    assert simplified.tolist() == [line[0].tolist(), line[-1].tolist()]
