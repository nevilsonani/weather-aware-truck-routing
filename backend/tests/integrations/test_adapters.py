"""Adapter tests against recorded-shape payloads (HTTP mocked with ``responses``)."""

import math
from datetime import UTC, date, datetime

import numpy as np
import pytest
import responses

from planner.domain import geo
from planner.domain.errors import NoRouteFound, UpstreamUnavailable
from planner.domain.geo import LatLon
from planner.domain.units import METERS_PER_KM
from planner.integrations.geocoding import FallbackGeocoder, NominatimGeocoder, PhotonGeocoder
from planner.integrations.http import HttpClient, HttpConfig
from planner.integrations.routing import (
    OsrmRoutingProvider,
    ValhallaRoutingProvider,
    VehicleProfile,
)
from planner.integrations.routing.base import normalize_road_name
from planner.integrations.weather import OpenMeteoWeatherProvider

HTTP = HttpClient("test", HttpConfig(retries=0))
VEHICLE = VehicleProfile(gross_weight_kg=30_000)
A, B = LatLon(39.74, -104.99), LatLon(40.0, -104.0)
SHAPE = np.column_stack((np.linspace(A.lat, B.lat, 5), np.linspace(A.lon, B.lon, 5)))


def valhalla_trip(time_s=3600.0):
    length_km = float(geo.cumulative_distance_m(SHAPE)[-1]) / METERS_PER_KM
    return {
        "summary": {"time": time_s, "length": length_km},
        "legs": [
            {
                "shape": geo.encode_polyline(SHAPE, 6),
                "maneuvers": [
                    {
                        "begin_shape_index": 0,
                        "end_shape_index": 2,
                        "time": time_s * 0.25,
                        "street_names": ["I 76 East"],
                    },
                    {
                        "begin_shape_index": 2,
                        "end_shape_index": 4,
                        "time": time_s * 0.75,
                        "street_names": ["US 34"],
                    },
                    {"begin_shape_index": 4, "end_shape_index": 4, "time": 0.0},
                ],
            }
        ],
    }


@responses.activate
def test_valhalla_parses_trip_and_alternates_and_sends_truck_weight():
    responses.post(
        "https://valhalla.test/route",
        json={"trip": valhalla_trip(3600), "alternates": [{"trip": valhalla_trip(4000)}]},
    )
    routes = ValhallaRoutingProvider("https://valhalla.test", HTTP).route(
        [A, B], VEHICLE, alternatives=2
    )

    assert [r.driving_s for r in routes] == pytest.approx([3600, 4000])
    assert routes[0].road_at(1) == "I-76"
    assert routes[0].road_at(routes[0].distance_m - 1) == "US-34"
    body = responses.calls[0].request.body
    assert (
        b'"costing": "truck"' in body and b'"weight": 30.0' in body and b'"alternates": 2' in body
    )


@responses.activate
@pytest.mark.parametrize(
    ("code", "error"), [(442, NoRouteFound), (171, NoRouteFound), (154, UpstreamUnavailable)]
)
def test_valhalla_error_mapping(code, error):
    responses.post(
        "https://valhalla.test/route",
        status=400,
        json={"error_code": code, "error": "nope", "status_code": 400},
    )
    with pytest.raises(error):
        ValhallaRoutingProvider("https://valhalla.test", HTTP).route([A, B], VEHICLE)


@responses.activate
def test_valhalla_via_points_are_pass_through_locations():
    responses.post("https://valhalla.test/route", json={"trip": valhalla_trip()})
    ValhallaRoutingProvider("https://valhalla.test", HTTP).route(
        [A, LatLon(39.9, -104.5), B], VEHICLE
    )
    body = responses.calls[0].request.body.decode()
    assert '"type": "through"' in body and "alternates" not in body


@responses.activate
def test_osrm_caps_segment_speed_at_truck_maximum():
    seg = geo.segment_lengths_m(SHAPE)
    responses.get(
        "https://osrm.test/route/v1/driving/-104.990000,39.740000;-104.000000,40.000000",
        json={
            "code": "Ok",
            "routes": [
                {
                    "geometry": geo.encode_polyline(SHAPE, 6),
                    "distance": float(seg.sum()),
                    "duration": 1.0,
                    "legs": [
                        {
                            "annotation": {"duration": [1.0] * len(seg), "distance": seg.tolist()},
                            "steps": [{"distance": float(seg.sum()), "ref": "I 76", "name": ""}],
                        }
                    ],
                }
            ],
        },
    )
    provider = OsrmRoutingProvider("https://osrm.test", HTTP, truck_max_speed_mph=60)
    route = provider.route([A, B], VEHICLE)[0]
    assert route.driving_s == pytest.approx(seg.sum() / (60 * 0.44704), rel=1e-6)
    assert route.road_at(10) == "I-76"
    assert "car routing" in route.notices[0]


@responses.activate
def test_osrm_no_route():
    responses.get(
        "https://osrm.test/route/v1/driving/-104.990000,39.740000;-104.000000,40.000000",
        status=400,
        json={"code": "NoRoute", "message": "Impossible route"},
    )
    with pytest.raises(NoRouteFound):
        OsrmRoutingProvider("https://osrm.test", HTTP).route([A, B], VEHICLE)


def open_meteo_location(start_ts, hours, rain, showers, snow):
    return {
        "hourly": {
            "time": [start_ts + 3600 * h for h in range(hours)],
            "wind_speed_10m": [10.0] * hours,
            "wind_gusts_10m": [15.0] * hours,
            "rain": rain,
            "showers": showers,
            "snowfall": snow,
        }
    }


@responses.activate
def test_open_meteo_multi_location_parsing():
    start = int(datetime(2026, 11, 18, tzinfo=UTC).timestamp())
    responses.get(
        "https://api.open-meteo.com/v1/forecast",
        json=[
            open_meteo_location(start, 24, [0.1] * 24, [0.05] * 24, [0.0] * 24),
            open_meteo_location(start, 24, [None] * 24, [0.2] * 24, [1.5] * 24),
        ],
    )
    provider = OpenMeteoWeatherProvider(HTTP)
    day = date(2026, 11, 18)
    first, second = provider.fetch_days([A, B], day, day)

    assert first[day].rain_in[0] == pytest.approx(0.15)  # rain + showers (liquid only)
    assert second[day].rain_in[0] == pytest.approx(0.2)  # missing rain, showers present
    assert second[day].snow_in[5] == 1.5
    params = responses.calls[0].request.params
    assert params["wind_speed_unit"] == "mph" and params["precipitation_unit"] == "inch"
    assert "precipitation" not in params["hourly"].split(",")


@responses.activate
def test_open_meteo_missing_hours_are_nan_and_errors_raise():
    start = int(datetime(2026, 11, 18, tzinfo=UTC).timestamp())
    responses.get(
        "https://api.open-meteo.com/v1/forecast",
        json=open_meteo_location(start, 3, [0.0] * 3, [0.0] * 3, [0.0] * 3),
    )
    day = date(2026, 11, 18)
    (only,) = OpenMeteoWeatherProvider(HTTP).fetch_days([A], day, day)
    assert math.isnan(only[day].wind_mph[5])

    responses.get("https://api.open-meteo.com/v1/forecast", status=429, json={"reason": "limit"})
    with pytest.raises(UpstreamUnavailable, match="rate limit"):
        OpenMeteoWeatherProvider(HTTP).fetch_days([A], day, day)


@responses.activate
def test_api_key_switches_to_customer_endpoint():
    responses.get("https://customer-api.open-meteo.com/v1/forecast", json={"hourly": {}})
    OpenMeteoWeatherProvider(HTTP, api_key="secret").fetch_days(
        [A], date(2026, 1, 1), date(2026, 1, 1)
    )
    assert responses.calls[0].request.params["apikey"] == "secret"


@responses.activate
def test_photon_labels_dedupes_and_falls_back_to_nominatim():
    feature = {
        "geometry": {"coordinates": [-104.98, 39.74]},
        "properties": {
            "osm_type": "R",
            "osm_id": 1,
            "name": "Denver",
            "state": "Colorado",
            "country": "United States",
            "countrycode": "us",
            "type": "city",
        },
    }
    responses.get("https://photon.test/api/", json={"features": [feature, feature]})
    places = PhotonGeocoder("https://photon.test", HTTP).search("denver", limit=5)
    assert [p.label for p in places] == ["Denver, Colorado, United States"]
    assert places[0].country_code == "US"

    responses.replace(responses.GET, "https://photon.test/api/", status=503)
    responses.get(
        "https://nominatim.test/search",
        json=[
            {
                "place_id": 9,
                "lat": "39.7",
                "lon": "-104.9",
                "name": "Denver",
                "address": {"city": "Denver", "state": "Colorado", "country": "United States"},
            }
        ],
    )
    geocoder = FallbackGeocoder(
        [
            PhotonGeocoder("https://photon.test", HTTP),
            NominatimGeocoder("https://nominatim.test", HTTP),
        ]
    )
    assert geocoder.search("denver", limit=5)[0].id == "nominatim:9"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("I 76 East", "I-76"),
        ("US 34", "US-34"),
        ("CO 470", "CO-470"),
        ("Main Street", "Main Street"),
        (None, None),
        ("", None),
    ],
)
def test_road_name_normalisation(raw, expected):
    assert normalize_road_name(raw) == expected
