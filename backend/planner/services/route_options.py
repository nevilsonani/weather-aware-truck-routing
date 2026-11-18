"""Find N *distinct, reasonable* route options between two points.

Routing engines frequently return fewer alternatives than requested (OSRM often returns one or
two; Valhalla none for short trips), and sometimes return near-duplicates. To reliably offer
three options we:

1. ask the engine for its own alternatives;
2. if that is not enough, force candidates through via points offset perpendicular to the
   trip axis (midpoint left/right, then third-points, then wider offsets);
3. accept a candidate only if it is not a big detour (within ``max_detour_ratio`` of the fastest
   driving time *or* ``max_detour_extra_s`` longer, whichever is looser, so short trips can still
   have alternatives) and it is genuinely different from every accepted route (shares less than
   ``max_overlap`` of its length with each).

A single provider is used for all options of one plan, so travel times stay comparable (truck
timings are never mixed with car timings). Providers are tried in order only when unavailable.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field

import numpy as np

from planner.domain import geo
from planner.domain.errors import NoRouteFound, PlannerError, UpstreamUnavailable
from planner.domain.geo import LatLon
from planner.domain.route import DrivingRoute, overlap_fraction
from planner.integrations.routing import RoutingProvider, VehicleProfile

from .cache import Cache

logger = logging.getLogger(__name__)
CACHE_VERSION = "v1"


@dataclass(frozen=True)
class RouteSearchConfig:
    target_count: int = 3
    max_detour_ratio: float = 1.5
    max_detour_extra_s: float = 45 * 60
    max_overlap: float = 0.8
    via_offset_fraction: float = 0.2
    min_via_offset_m: float = 15_000.0
    max_via_offset_m: float = 200_000.0
    max_parallel_requests: int = 2
    # Time allowed for forcing extra alternatives; past it the plan goes ahead with the routes
    # found so far (the native ones are always kept).
    via_budget_s: float = 20.0
    cache_ttl_s: int = 60 * 60


@dataclass(frozen=True)
class RouteOptions:
    routes: list[DrivingRoute]
    provider: str
    notices: list[str] = field(default_factory=list)


class RouteOptionsService:
    def __init__(
        self,
        providers: Sequence[RoutingProvider],
        cache: Cache,
        config: RouteSearchConfig | None = None,
    ) -> None:
        if not providers:
            raise ValueError("At least one routing provider is required")
        self.providers = list(providers)
        self.cache = cache
        self.config = config or RouteSearchConfig()

    def find(self, origin: LatLon, destination: LatLon, vehicle: VehicleProfile) -> RouteOptions:
        key = self._cache_key(origin, destination, vehicle)
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        failures: list[UpstreamUnavailable] = []
        for provider in self.providers:
            try:
                options = self._find_with(provider, origin, destination, vehicle)
            except UpstreamUnavailable as exc:
                logger.warning("Routing via %s failed: %s", provider.name, exc.message)
                failures.append(exc)
                continue
            options.notices[:0] = [exc.message for exc in failures]
            self.cache.set(key, options, timeout=self.config.cache_ttl_s)
            return options
        raise failures[-1] if failures else UpstreamUnavailable("No routing provider available")

    def _find_with(
        self,
        provider: RoutingProvider,
        origin: LatLon,
        destination: LatLon,
        vehicle: VehicleProfile,
    ) -> RouteOptions:
        target = self.config.target_count
        native = provider.route([origin, destination], vehicle, alternatives=target - 1)
        if not native:
            raise NoRouteFound("No drivable route was found between these locations.")

        accepted: list[DrivingRoute] = []
        for route in sorted(native, key=lambda r: r.driving_s):
            self._consider(route, accepted)

        deadline = time.monotonic() + self.config.via_budget_s
        for batch in self._via_batches(accepted[0], origin, destination):
            remaining = deadline - time.monotonic()
            if len(accepted) >= target or remaining <= 0:
                break
            for route in self._route_via(provider, origin, destination, vehicle, batch, remaining):
                if len(accepted) >= target:
                    break
                self._consider(route, accepted)

        notices = [notice for route in accepted for notice in route.notices]
        if len(accepted) < target:
            extra_min = (self._max_driving_s(accepted) - accepted[0].driving_s) / 60
            notices.append(
                f"Only {len(accepted)} meaningfully different route(s) exist for this trip: "
                f"alternatives must add at most {extra_min:.0f} min of driving and differ from "
                f"each other by at least {(1 - self.config.max_overlap) * 100:.0f}% of their "
                "length."
            )
        accepted.sort(key=lambda r: r.driving_s)
        return RouteOptions(routes=accepted, provider=provider.name, notices=sorted(set(notices)))

    def _consider(self, candidate: DrivingRoute, accepted: list[DrivingRoute]) -> bool:
        if accepted:
            if candidate.driving_s > self._max_driving_s(accepted):
                return False
            for existing in accepted:
                shared = max(
                    overlap_fraction(candidate, existing), overlap_fraction(existing, candidate)
                )
                if shared >= self.config.max_overlap:
                    return False
        accepted.append(candidate)
        return True

    def _max_driving_s(self, accepted: Sequence[DrivingRoute]) -> float:
        fastest = min(r.driving_s for r in accepted)
        cfg = self.config
        return max(fastest * cfg.max_detour_ratio, fastest + cfg.max_detour_extra_s)

    def _via_batches(
        self, primary: DrivingRoute, origin: LatLon, destination: LatLon
    ) -> list[list[LatLon]]:
        cfg = self.config
        straight = geo.distance_m(origin, destination)
        bearing = geo.initial_bearing_deg(origin, destination)
        offset = float(
            np.clip(straight * cfg.via_offset_fraction, cfg.min_via_offset_m, cfg.max_via_offset_m)
        )

        def via(fraction: float, scale: float, side: int) -> LatLon:
            lat, lon = primary.positions_at(np.array([primary.distance_m * fraction]))[0]
            return geo.destination_point(LatLon(lat, lon), bearing + 90 * side, offset * scale)

        return [
            [via(0.5, 1.0, +1), via(0.5, 1.0, -1)],
            [via(1 / 3, 0.8, +1), via(2 / 3, 0.8, -1), via(1 / 3, 0.8, -1), via(2 / 3, 0.8, +1)],
            [via(0.5, 1.8, +1), via(0.5, 1.8, -1)],
        ]

    def _route_via(
        self,
        provider: RoutingProvider,
        origin: LatLon,
        destination: LatLon,
        vehicle: VehicleProfile,
        vias: list[LatLon],
        timeout_s: float,
    ) -> list[DrivingRoute]:
        def request(via: LatLon) -> DrivingRoute | None:
            try:
                routes = provider.route([origin, via, destination], vehicle)
            except PlannerError as exc:  # unroutable via point or transient failure: skip it
                logger.info("Via candidate %s rejected: %s", via, exc.message)
                return None
            return routes[0] if routes else None

        pool = ThreadPoolExecutor(max_workers=self.config.max_parallel_requests)
        futures = [pool.submit(request, via) for via in vias]
        done, pending = wait(futures, timeout=timeout_s)
        pool.shutdown(wait=False, cancel_futures=True)  # late candidates are simply skipped
        if pending:
            logger.info("%d via candidate(s) skipped: route search budget used up", len(pending))
        results = [f.result() for f in futures if f in done]
        return sorted((r for r in results if r is not None), key=lambda r: r.driving_s)

    def _cache_key(self, origin: LatLon, destination: LatLon, vehicle: VehicleProfile) -> str:
        raw = "|".join(
            [
                CACHE_VERSION,
                ",".join(p.name for p in self.providers),
                f"{origin.lat:.5f},{origin.lon:.5f}",
                f"{destination.lat:.5f},{destination.lon:.5f}",
                f"{round(vehicle.gross_weight_kg / 100)}",
                repr(self.config),
            ]
        )
        return "routes:" + hashlib.sha256(raw.encode()).hexdigest()
