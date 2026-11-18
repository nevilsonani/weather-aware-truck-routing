import pytest

from planner.domain.errors import NoRouteFound, UpstreamUnavailable
from planner.domain.geo import LatLon
from planner.integrations.routing import VehicleProfile
from planner.services.cache import DictCache
from planner.services.route_options import RouteOptionsService, RouteSearchConfig
from tests.fakes import FakeRoutingProvider, straight_route

ORIGIN, DEST = LatLon(39.74, -104.99), LatLon(41.88, -87.63)
VEHICLE = VehicleProfile(30_000)


def service(*providers, **config):
    return RouteOptionsService(list(providers), DictCache(), RouteSearchConfig(**config))


def test_native_alternatives_are_used_when_sufficient():
    provider = FakeRoutingProvider(native_alternatives=2)
    options = service(provider).find(ORIGIN, DEST, VEHICLE)
    assert len(options.routes) == 3
    assert len(provider.calls) == 1  # no via-point requests needed
    assert [r.driving_s for r in options.routes] == sorted(r.driving_s for r in options.routes)


def test_via_points_fill_up_missing_alternatives():
    provider = FakeRoutingProvider(native_alternatives=0)
    options = service(provider).find(ORIGIN, DEST, VEHICLE)
    assert len(options.routes) == 3
    via_calls = [waypoints for waypoints, _ in provider.calls if len(waypoints) == 3]
    assert via_calls, "expected forced via-point requests"
    assert options.notices == []


def test_detours_beyond_limits_are_rejected_with_a_notice():
    provider = FakeRoutingProvider(native_alternatives=0)
    options = service(provider, max_detour_ratio=1.0001, max_detour_extra_s=1).find(
        ORIGIN, DEST, VEHICLE
    )
    assert len(options.routes) == 1
    assert "Only 1 meaningfully different route" in options.notices[0]


def test_near_duplicate_routes_are_not_offered_twice():
    class DuplicateProvider(FakeRoutingProvider):
        def route(self, waypoints, vehicle, *, alternatives=0):
            self.calls.append((list(waypoints), alternatives))
            same = straight_route([ORIGIN, DEST])
            return [same, straight_route([ORIGIN, DEST])] if len(waypoints) == 2 else [same]

    options = service(DuplicateProvider()).find(ORIGIN, DEST, VEHICLE)
    assert len(options.routes) == 1


def test_falls_back_to_next_provider_only_when_unavailable():
    down = FakeRoutingProvider(name="down", fail_with=UpstreamUnavailable("Valhalla down"))
    backup = FakeRoutingProvider(name="backup", native_alternatives=2)
    options = service(down, backup).find(ORIGIN, DEST, VEHICLE)
    assert options.provider == "backup"
    assert "Valhalla down" in options.notices

    no_route = FakeRoutingProvider(name="primary", fail_with=NoRouteFound("ocean"))
    untouched = FakeRoutingProvider(name="secondary")
    with pytest.raises(NoRouteFound):
        service(no_route, untouched).find(ORIGIN, DEST, VEHICLE)
    assert untouched.calls == []  # a definitive "no route" is not retried elsewhere


def test_results_are_cached():
    provider = FakeRoutingProvider(native_alternatives=2)
    svc = service(provider)
    svc.find(ORIGIN, DEST, VEHICLE)
    svc.find(ORIGIN, DEST, VEHICLE)
    assert len(provider.calls) == 1


def test_all_providers_down_raises_last_error():
    svc = service(FakeRoutingProvider(fail_with=UpstreamUnavailable("down")))
    with pytest.raises(UpstreamUnavailable, match="down"):
        svc.find(ORIGIN, DEST, VEHICLE)


def test_via_point_search_respects_its_time_budget():
    import time

    class SlowVias(FakeRoutingProvider):
        def route(self, waypoints, vehicle, *, alternatives=0):
            if len(waypoints) == 3:
                time.sleep(1.5)
            return super().route(waypoints, vehicle, alternatives=alternatives)

    started = time.perf_counter()
    options = service(SlowVias(native_alternatives=0), via_budget_s=0.2).find(ORIGIN, DEST, VEHICLE)
    assert time.perf_counter() - started < 1.2
    assert len(options.routes) == 1  # the native route is kept; slow candidates are skipped
