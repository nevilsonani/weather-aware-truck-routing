"""Trip planning use case.

routes → checkpoints with truck ETAs → weather at each ETA → risk → recommendation → corridor.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np

from planner.domain import geo
from planner.domain.checkpoints import Checkpoint, sample_checkpoints
from planner.domain.corridor import CorridorGrid, build_corridor_grid, corridor_buffer_m
from planner.domain.errors import InvalidTripRequest, UpstreamUnavailable
from planner.domain.geo import LatLon
from planner.domain.hos import DrivingSchedule, HosPolicy, StopKind
from planner.domain.recommendation import (
    Recommendation,
    RiskProfile,
    RouteCandidate,
    build_profile,
    recommend,
)
from planner.domain.risk import RiskAssessment, RiskRules
from planner.domain.route import DrivingRoute
from planner.domain.units import KG_PER_LB, meters_to_miles, miles_to_meters
from planner.domain.weather import WeatherConditions
from planner.integrations.routing import VehicleProfile
from planner.integrations.timezones import TimezoneResolver

from .route_options import RouteOptionsService
from .weather import WeatherService, utc_now

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlannerConfig:
    sample_intervals_mi: tuple[int, ...] = (10, 25, 50)
    max_departure_ahead: timedelta = timedelta(days=7)
    departure_grace: timedelta = timedelta(hours=1)
    truck_tare_weight_lbs: float = 35_000.0
    legal_gross_weight_lbs: float = 80_000.0
    min_trip_distance_m: float = miles_to_meters(1.0)
    max_checkpoints_per_route: int = 400
    timeline_step_m: float = miles_to_meters(5.0)
    corridor_buffer_fraction: float = 0.04
    corridor_buffer_min_m: float = 30_000.0
    corridor_buffer_max_m: float = 80_000.0
    heatmap_max_cells: int = 220
    hos_policy: HosPolicy = field(default_factory=HosPolicy)


@dataclass(frozen=True)
class Endpoint:
    position: LatLon
    label: str


@dataclass(frozen=True)
class TripRequest:
    origin: Endpoint
    destination: Endpoint
    load_weight_lbs: float
    sample_interval_mi: int
    departure: datetime | None = None  # naive = origin-local wall time; None = now
    apply_hos: bool = True


@dataclass(frozen=True)
class RestStop:
    kind: StopKind
    start: datetime
    end: datetime
    distance_m: float
    position: LatLon


@dataclass(frozen=True, eq=False)
class RouteAnalysis:
    id: str
    label: str
    name: str
    route: DrivingRoute
    schedule: DrivingSchedule
    checkpoints: list[Checkpoint]
    conditions: list[WeatherConditions | None]
    assessments: list[RiskAssessment | None]
    reasons: list[list[str]]
    timezones: list[str]
    profile: RiskProfile
    rest_stops: list[RestStop]
    timeline: np.ndarray  # (K, 2) [elapsed_s, distance_m], non-decreasing in both
    departure: datetime
    arrival: datetime


@dataclass(frozen=True, eq=False)
class TripPlan:
    request: TripRequest
    origin_timezone: str
    departure: datetime
    gross_weight_lbs: float
    provider: str
    routes: list[RouteAnalysis]
    recommendation: Recommendation
    corridor: CorridorGrid
    warnings: list[str]
    generated_at: datetime


class TripPlanner:
    def __init__(
        self,
        routes: RouteOptionsService,
        weather: WeatherService,
        rules: RiskRules,
        timezones: TimezoneResolver,
        config: PlannerConfig | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.routes = routes
        self.weather = weather
        self.rules = rules
        self.timezones = timezones
        self.config = config or PlannerConfig()
        self.clock = clock

    def plan(self, request: TripRequest) -> TripPlan:
        cfg = self.config
        self._validate(request)
        origin_tz = self.timezones.timezone_at(
            request.origin.position.lat, request.origin.position.lon
        )
        departure = self.resolve_departure(request.departure, origin_tz)
        gross_lbs = cfg.truck_tare_weight_lbs + request.load_weight_lbs
        vehicle = VehicleProfile(gross_weight_kg=gross_lbs * KG_PER_LB)

        options = self.routes.find(request.origin.position, request.destination.position, vehicle)
        interval_m = miles_to_meters(request.sample_interval_mi)
        self._check_checkpoint_budget(options.routes, request.sample_interval_mi)

        policy = cfg.hos_policy if request.apply_hos else HosPolicy.disabled()
        schedules = [DrivingSchedule(r.driving_s, policy) for r in options.routes]
        checkpoint_sets = [
            sample_checkpoints(route, interval_m, departure, schedule)
            for route, schedule in zip(options.routes, schedules, strict=True)
        ]

        flat = [cp for cps in checkpoint_sets for cp in cps]
        lookup = self.weather.conditions_at([(cp.position, cp.eta) for cp in flat])
        if flat and all(c is None for c in lookup.conditions):
            raise UpstreamUnavailable(
                "Weather forecasts are currently unavailable, so route risk cannot be assessed.",
                details={"reasons": lookup.warnings},
            )

        analyses = []
        cursor = 0
        names = route_names(options.routes)
        for i, (route, schedule, cps) in enumerate(
            zip(options.routes, schedules, checkpoint_sets, strict=True)
        ):
            conditions = lookup.conditions[cursor : cursor + len(cps)]
            cursor += len(cps)
            analyses.append(
                self._analyse(
                    chr(ord("A") + i),
                    names[i],
                    route,
                    schedule,
                    cps,
                    conditions,
                    departure,
                    request.load_weight_lbs,
                )
            )

        recommendation = recommend(
            [RouteCandidate(a.id, a.label, a.profile, a.schedule.total_elapsed_s) for a in analyses]
        )
        longest = max(r.distance_m for r in options.routes)
        corridor = build_corridor_grid(
            [r.coords for r in options.routes],
            [r.distance_m for r in options.routes],
            buffer_m=corridor_buffer_m(
                longest,
                fraction=cfg.corridor_buffer_fraction,
                minimum_m=cfg.corridor_buffer_min_m,
                maximum_m=cfg.corridor_buffer_max_m,
            ),
            max_cells=cfg.heatmap_max_cells,
        )
        return TripPlan(
            request=request,
            origin_timezone=origin_tz,
            departure=departure,
            gross_weight_lbs=gross_lbs,
            provider=options.provider,
            routes=analyses,
            recommendation=recommendation,
            corridor=corridor,
            warnings=self._warnings(options.notices, lookup.warnings, analyses, gross_lbs),
            generated_at=self.clock(),
        )

    # --- validation ---------------------------------------------------------------------

    def _validate(self, request: TripRequest) -> None:
        cfg = self.config
        if request.sample_interval_mi not in cfg.sample_intervals_mi:
            raise InvalidTripRequest(
                "Sample interval must be one of "
                f"{', '.join(map(str, cfg.sample_intervals_mi))} miles."
            )
        if request.load_weight_lbs < 0:
            raise InvalidTripRequest("Load weight cannot be negative.")
        if (
            geo.distance_m(request.origin.position, request.destination.position)
            < cfg.min_trip_distance_m
        ):
            raise InvalidTripRequest("Origin and destination must be at least 1 mile apart.")

    def resolve_departure(self, departure: datetime | None, origin_tz: str) -> datetime:
        """Naive departure times are wall-clock times at the origin (what a driver means)."""
        now = self.clock().astimezone(UTC)
        if departure is None:
            return now.replace(second=0, microsecond=0)
        if departure.tzinfo is None:
            departure = departure.replace(tzinfo=ZoneInfo(origin_tz))
        departure = departure.astimezone(UTC)
        if departure < now - self.config.departure_grace:
            raise InvalidTripRequest("Departure time is in the past.")
        if departure > now + self.config.max_departure_ahead:
            days = self.config.max_departure_ahead.days
            raise InvalidTripRequest(
                f"Departure must be within the next {days} days, where forecasts are reliable."
            )
        return departure

    def _check_checkpoint_budget(self, routes: Sequence[DrivingRoute], interval_mi: int) -> None:
        limit = self.config.max_checkpoints_per_route
        longest_mi = meters_to_miles(max(r.distance_m for r in routes))
        if longest_mi / interval_mi > limit:
            raise InvalidTripRequest(
                f"A {longest_mi:,.0f}-mile trip sampled every {interval_mi} miles exceeds the "
                f"{limit}-checkpoint limit per route; choose a larger sampling interval.",
                details={"route_miles": round(longest_mi), "max_checkpoints": limit},
            )

    # --- assembly -----------------------------------------------------------------------

    def _analyse(
        self,
        route_id: str,
        name: str,
        route: DrivingRoute,
        schedule: DrivingSchedule,
        checkpoints: list[Checkpoint],
        conditions: Sequence[WeatherConditions | None],
        departure: datetime,
        load_lbs: float,
    ) -> RouteAnalysis:
        assessments: list[RiskAssessment | None] = []
        reasons: list[list[str]] = []
        for cond in conditions:
            if cond is None:
                assessments.append(None)
                reasons.append(["No forecast available for this time and place"])
            else:
                assessment = self.rules.assess(cond, load_lbs)
                assessments.append(assessment)
                reasons.append(self.rules.explain(assessment, cond, load_lbs))

        return RouteAnalysis(
            id=route_id,
            label=f"Route {route_id}",
            name=name,
            route=route,
            schedule=schedule,
            checkpoints=checkpoints,
            conditions=list(conditions),
            assessments=assessments,
            reasons=reasons,
            timezones=[
                self.timezones.timezone_at(cp.position.lat, cp.position.lon) for cp in checkpoints
            ],
            profile=build_profile(checkpoints, assessments),
            rest_stops=self._rest_stops(route, schedule, departure),
            timeline=build_timeline(route, schedule, self.config.timeline_step_m),
            departure=departure,
            arrival=departure + timedelta(seconds=schedule.total_elapsed_s),
        )

    @staticmethod
    def _rest_stops(
        route: DrivingRoute, schedule: DrivingSchedule, departure: datetime
    ) -> list[RestStop]:
        stops = []
        for stop in schedule.stops:
            distance = float(route.distance_at_driving_time(np.array([stop.driving_s]))[0])
            lat, lon = route.positions_at(np.array([distance]))[0]
            stops.append(
                RestStop(
                    kind=stop.kind,
                    start=departure + timedelta(seconds=stop.elapsed_start_s),
                    end=departure + timedelta(seconds=stop.elapsed_end_s),
                    distance_m=distance,
                    position=LatLon(float(lat), float(lon)),
                )
            )
        return stops

    def _warnings(
        self,
        notices: Sequence[str],
        weather_warnings: Sequence[str],
        analyses: Sequence[RouteAnalysis],
        gross_lbs: float,
    ) -> list[str]:
        warnings = [*notices, *weather_warnings]
        unknown = sum(a.assessments.count(None) for a in analyses)
        if unknown:
            warnings.append(
                f"{unknown} checkpoint(s) have no forecast data and are excluded from risk scoring."
            )
        legal = self.config.legal_gross_weight_lbs
        if gross_lbs > legal:
            warnings.append(
                f"Estimated gross weight {gross_lbs:,.0f} lb (load + "
                f"{self.config.truck_tare_weight_lbs:,.0f} lb tractor-trailer) exceeds the "
                f"{legal:,.0f} lb federal limit; an overweight permit is required."
            )
        return warnings


def build_timeline(route: DrivingRoute, schedule: DrivingSchedule, step_m: float) -> np.ndarray:
    """Knots mapping wall-clock elapsed time to distance driven, including stationary stops.

    Lets the client place the truck on the map for any forecast hour with linear interpolation.
    """
    distances = np.append(np.arange(0.0, route.distance_m, step_m), route.distance_m)
    elapsed = schedule.elapsed_at(route.driving_time_at(distances))
    knots = [*zip(elapsed.tolist(), distances.tolist(), strict=True)]
    for stop in schedule.stops:
        at = float(route.distance_at_driving_time(np.array([stop.driving_s]))[0])
        knots += [(stop.elapsed_start_s, at), (stop.elapsed_end_s, at)]
    ordered = np.array(sorted(set(knots)))
    return ordered


def route_names(routes: Sequence[DrivingRoute]) -> list[str]:
    """ "via I-76 · I-80", with a distinguishing road appended when two names would collide."""
    majors = [r.major_roads(2) for r in routes]
    names = []
    for i, route in enumerate(routes):
        roads = list(majors[i])
        collides = not roads or any(majors[j] == majors[i] for j in range(len(routes)) if j != i)
        if collides:
            elsewhere = {
                name
                for j, other in enumerate(routes)
                if j != i
                for name, length in other.road_lengths().items()
                if length >= 0.02 * other.distance_m
            }
            lengths = route.road_lengths()
            distinctive = sorted(
                (
                    n
                    for n, length in lengths.items()
                    if n not in elsewhere and n not in roads and length >= 0.02 * route.distance_m
                ),
                key=lambda n: -lengths[n],
            )
            roads += distinctive[:1]
        names.append(f"via {' · '.join(roads)}" if roads else "Local roads")
    return names
