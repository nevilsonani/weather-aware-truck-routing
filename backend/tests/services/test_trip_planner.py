from datetime import UTC, datetime, timedelta

import pytest

from planner.domain.errors import InvalidTripRequest, UpstreamUnavailable
from planner.domain.geo import LatLon
from planner.domain.risk import RiskLevel, RiskRules
from planner.integrations.timezones import TimezoneResolver
from planner.services.cache import DictCache
from planner.services.heatmap import HeatmapService
from planner.services.route_options import RouteOptionsService
from planner.services.trip_planner import Endpoint, PlannerConfig, TripPlanner, TripRequest
from planner.services.weather import WeatherService
from tests.fakes import FIXED_NOW, FakeRoutingProvider, FakeWeatherProvider, calm_weather

DENVER = Endpoint(LatLon(39.7392, -104.9903), "Denver")
CHICAGO = Endpoint(LatLon(41.8781, -87.6298), "Chicago")


def windy_north(lat, lon, when):
    """Severe wind north of 40.2°N: pushes the ranking towards southern alternatives."""
    return (48.0 if lat > 40.2 else 5.0, 60.0, 0.0, 0.0)


def build(weather_fn=calm_weather, *, weather_fail=False, alternatives=2):
    cache = DictCache()
    weather = WeatherService(
        FakeWeatherProvider(weather_fn, fail=weather_fail), cache, clock=lambda: FIXED_NOW
    )
    routes = RouteOptionsService([FakeRoutingProvider(native_alternatives=alternatives)], cache)
    planner = TripPlanner(routes, weather, RiskRules(), TimezoneResolver(), clock=lambda: FIXED_NOW)
    return planner, HeatmapService(weather, RiskRules(), clock=lambda: FIXED_NOW)


def request(**overrides):
    values = {
        "origin": DENVER,
        "destination": CHICAGO,
        "load_weight_lbs": 20_000,
        "sample_interval_mi": 25,
        "departure": None,
    }
    values.update(overrides)
    return TripRequest(**values)


def test_plan_produces_three_scored_routes_and_a_recommendation():
    planner, _ = build()
    plan = planner.plan(request())
    assert [r.label for r in plan.routes] == ["Route A", "Route B", "Route C"]
    assert plan.recommendation.route_id == "A"  # calm weather: fastest wins
    assert plan.recommendation.status.value == "clear"
    for analysis in plan.routes:
        covered = sum(analysis.profile.miles_by_level.values())
        assert covered == pytest.approx(analysis.route.distance_m / 1609.344)
        assert analysis.arrival > plan.departure
        assert analysis.timeline[0].tolist() == [0.0, 0.0]


def test_load_rule_turns_severe_wind_into_no_travel_and_drives_the_ranking():
    planner, _ = build(windy_north)

    def no_travel(route):
        return route.profile.miles(RiskLevel.NO_TRAVEL)

    light = planner.plan(request(load_weight_lbs=20_000))  # 48 mph: Severe
    assert all(no_travel(r) == 0 for r in light.routes)

    heavy = planner.plan(request(load_weight_lbs=35_000))  # 45-54 mph + >30k lb: No Travel
    recommended = next(r for r in heavy.routes if r.id == heavy.recommendation.route_id)
    assert no_travel(recommended) == min(no_travel(r) for r in heavy.routes) > 0
    assert heavy.recommendation.status.value == "no_safe_route"


def test_hos_toggle_changes_long_trip_arrival():
    planner, _ = build()
    with_hos = planner.plan(request()).routes[0]
    without = planner.plan(request(apply_hos=False)).routes[0]
    assert with_hos.rest_stops and not without.rest_stops
    assert (with_hos.arrival - without.arrival) >= timedelta(hours=10)


def test_naive_departure_is_interpreted_at_origin_local_time():
    planner, _ = build()
    plan = planner.plan(request(departure=datetime(2026, 11, 19, 8, 0)))
    assert plan.origin_timezone == "America/Denver"
    assert plan.departure == datetime(2026, 11, 19, 15, 0, tzinfo=UTC)  # 08:00 MST


def test_aware_departure_is_respected():
    planner, _ = build()
    departure = datetime(2026, 11, 19, 8, 0, tzinfo=UTC)
    assert planner.plan(request(departure=departure)).departure == departure


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"destination": DENVER}, "at least 1 mile"),
        ({"sample_interval_mi": 7}, "Sample interval"),
        ({"departure": FIXED_NOW - timedelta(hours=3)}, "in the past"),
        ({"departure": FIXED_NOW + timedelta(days=9)}, "within the next 7 days"),
    ],
)
def test_invalid_requests(overrides, message):
    planner, _ = build()
    with pytest.raises(InvalidTripRequest, match=message):
        planner.plan(request(**overrides))


def test_checkpoint_budget_protects_very_long_trips():
    planner, _ = build()
    small_budget = TripPlanner(
        planner.routes,
        planner.weather,
        planner.rules,
        planner.timezones,
        PlannerConfig(max_checkpoints_per_route=50),
        clock=lambda: FIXED_NOW,
    )
    with pytest.raises(InvalidTripRequest, match="checkpoint limit"):
        small_budget.plan(request(sample_interval_mi=10))  # ~900 mi / 10 mi > 50


def test_total_weather_outage_is_an_error_not_a_silent_low_risk():
    planner, _ = build(weather_fail=True)
    with pytest.raises(UpstreamUnavailable, match="Weather forecasts are currently unavailable"):
        planner.plan(request())


def test_overweight_load_is_flagged():
    planner, _ = build()
    plan = planner.plan(request(load_weight_lbs=60_000))
    assert any("exceeds the 80,000 lb federal limit" in w for w in plan.warnings)


def test_heatmap_frames_cover_48_hours_after_departure():
    planner, heatmap_service = build(windy_north)
    plan = planner.plan(request(load_weight_lbs=35_000))
    heatmap = heatmap_service.build(plan.corridor.spec, plan.corridor.cells, plan.departure, 35_000)
    assert heatmap.start <= plan.departure
    assert heatmap.start + (heatmap.frame_count - 1) * heatmap.step >= plan.departure + timedelta(
        hours=48
    )
    assert heatmap.risk.shape == (heatmap.frame_count, len(plan.corridor.cells))
    assert {0, 4} <= set(heatmap.risk.ravel().tolist())  # calm south, No Travel north
