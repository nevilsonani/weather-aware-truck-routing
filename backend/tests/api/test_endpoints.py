"""HTTP contract tests: the whole Django stack with in-memory providers."""

import pytest
from django.core.cache import caches
from rest_framework.test import APIClient

from api.container import Services, override_services
from planner.domain.risk import RiskRules
from planner.integrations.timezones import TimezoneResolver
from planner.services.cache import DictCache
from planner.services.heatmap import HeatmapService
from planner.services.route_options import RouteOptionsService
from planner.services.trip_planner import TripPlanner
from planner.services.weather import WeatherService
from tests.fakes import FIXED_NOW, FakeGeocoder, FakeRoutingProvider, FakeWeatherProvider

PLAN_BODY = {
    "origin": {"lat": 39.7392, "lon": -104.9903, "label": "Denver, CO"},
    "destination": {"lat": 41.8781, "lon": -87.6298, "label": "Chicago, IL"},
    "load_weight_lbs": 42_000,
    "sample_interval_mi": 50,
}


@pytest.fixture(autouse=True)
def services():
    for alias in ("default", "routes"):
        caches[alias].clear()
    cache = DictCache()
    weather = WeatherService(FakeWeatherProvider(), cache, clock=lambda: FIXED_NOW)
    rules = RiskRules()
    timezones = TimezoneResolver()
    planner = TripPlanner(
        RouteOptionsService([FakeRoutingProvider(native_alternatives=2)], cache),
        weather,
        rules,
        timezones,
        clock=lambda: FIXED_NOW,
    )
    fake = Services(
        planner=planner,
        heatmap=HeatmapService(weather, rules, clock=lambda: FIXED_NOW),
        geocoder=FakeGeocoder(),
        timezones=timezones,
        rules=rules,
        cache=cache,
    )
    with override_services(fake):
        yield fake


@pytest.fixture
def client():
    return APIClient()


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_meta_exposes_rules_from_the_backend(client):
    body = client.get("/api/v1/meta").json()
    assert body["sample_intervals_mi"] == [10, 25, 50]
    wind = body["conditions"]["wind"]["thresholds"]
    assert [t["value"] for t in wind] == [25, 35, 45, 55]
    assert body["conditions"]["rain"]["thresholds"][-1] == {
        "level": "no_travel",
        "value": 1.0,
        "inclusive": False,
    }
    assert body["ranking_criteria"][:2] == ["weather_coverage", "no_travel_miles"]


def test_plan_contract(client):
    response = client.post("/api/v1/trips/plan", PLAN_BODY, format="json")
    assert response.status_code == 200, response.content
    body = response.json()

    assert body["trip"]["origin"]["timezone"] == "America/Denver"
    assert body["trip"]["destination"]["timezone"] == "America/Chicago"
    assert body["trip"]["gross_weight_lbs"] == 77_000
    assert len(body["routes"]) == 3
    assert sum(r["recommended"] for r in body["routes"]) == 1
    assert sorted(r["rank"] for r in body["routes"]) == [1, 2, 3]

    route = body["routes"][0]
    checkpoint = route["checkpoints"][1]
    assert checkpoint["distance_mi"] == 50.0
    assert checkpoint["eta_utc"].endswith("Z")
    assert set(checkpoint["weather"]) == {"wind_mph", "gust_mph", "rain_in_hr", "snow_in_hr"}
    assert checkpoint["risk"]["level"] == "low"
    assert set(route["summary"]["miles_by_level"]) == {
        "low",
        "moderate",
        "high",
        "severe",
        "no_travel",
        "unknown",
    }
    assert route["timeline"][0] == [0, 0.0]
    assert isinstance(route["geometry"], str)
    assert body["corridor"]["cells"]


def test_validation_errors_use_the_error_envelope(client):
    response = client.post(
        "/api/v1/trips/plan",
        {**PLAN_BODY, "load_weight_lbs": -1, "sample_interval_mi": 30},
        format="json",
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert set(error["details"]) == {"load_weight_lbs", "sample_interval_mi"}


def test_domain_errors_map_to_422(client):
    body = {**PLAN_BODY, "destination": PLAN_BODY["origin"]}
    response = client.post("/api/v1/trips/plan", body, format="json")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_trip"


def test_heatmap_roundtrip_from_plan(client):
    plan = client.post("/api/v1/trips/plan", PLAN_BODY, format="json").json()
    response = client.post(
        "/api/v1/trips/heatmap",
        {
            "grid": plan["corridor"],
            "departure": plan["trip"]["departure_utc"],
            "load_weight_lbs": 42_000,
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    body = response.json()
    cells = len(plan["corridor"]["cells"])
    assert body["frame_count"] >= 49
    for layer in ("risk", "wind_mph", "rain_in_hr", "snow_in_hr"):
        assert len(body["layers"][layer]) == body["frame_count"]
        assert len(body["layers"][layer][0]) == cells


def test_heatmap_rejects_naive_departure_and_bad_cells(client):
    grid = {"west": -105, "east": -104, "south": 39, "north": 40, "nx": 2, "ny": 2, "cells": [9]}
    response = client.post(
        "/api/v1/trips/heatmap",
        {"grid": grid, "departure": "2026-11-18T12:00", "load_weight_lbs": 0},
        format="json",
    )
    assert response.status_code == 400
    assert "departure" in response.json()["error"]["details"]

    response = client.post(
        "/api/v1/trips/heatmap",
        {"grid": grid, "departure": "2026-11-18T12:00:00Z", "load_weight_lbs": 0},
        format="json",
    )
    assert response.status_code == 422  # cell index 9 is outside a 2x2 grid


def test_place_search_adds_timezone_and_caches(client, services):
    first = client.get("/api/v1/places/search", {"q": "denver"}).json()
    client.get("/api/v1/places/search", {"q": "denver"})
    assert first["results"][0]["timezone"] == "America/Denver"
    assert services.geocoder.queries == ["denver"]


def test_place_search_requires_a_query(client):
    assert client.get("/api/v1/places/search", {"q": "x"}).status_code == 400


@pytest.mark.parametrize("host", ["10.0.4.7", "internal-probe"])
def test_health_ignores_unknown_hosts(client, host):
    # Platform probes may use an internal host that is not in ALLOWED_HOSTS.
    response = client.get("/api/health", HTTP_HOST=host)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_preflight_for_configured_origin(client, settings):
    settings.CORS_ALLOWED_ORIGIN_REGEXES = [r"^https://wx-.*\.vercel\.app$"]
    response = client.options(
        "/api/v1/trips/plan",
        HTTP_ORIGIN="https://wx-git-main.vercel.app",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type",
    )
    assert response["access-control-allow-origin"] == "https://wx-git-main.vercel.app"


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_numbers_are_rejected(client, value):
    # Review finding: DRF FloatField accepts "NaN", which then slips past min/max checks.
    plan = client.post("/api/v1/trips/plan", {**PLAN_BODY, "load_weight_lbs": value}, format="json")
    assert plan.status_code == 400
    assert "load_weight_lbs" in plan.json()["error"]["details"]

    grid = {"west": -105, "east": -104, "south": 39, "north": 40, "nx": 2, "ny": 2, "cells": [0]}
    heat = client.post(
        "/api/v1/trips/heatmap",
        {"grid": grid, "departure": "2026-11-18T12:00:00Z", "load_weight_lbs": value},
        format="json",
    )
    assert heat.status_code == 400
