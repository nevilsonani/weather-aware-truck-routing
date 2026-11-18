"""Composition root: builds the planner services from Django settings, once per process.

Views only call :func:`get_services`; tests swap the whole graph with :func:`override_services`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from functools import cache

from django.conf import settings
from django.core.cache import caches

from planner.domain.risk import RiskRules
from planner.integrations.geocoding import (
    FallbackGeocoder,
    Geocoder,
    NominatimGeocoder,
    PhotonGeocoder,
)
from planner.integrations.http import HttpClient, HttpConfig
from planner.integrations.routing import (
    OsrmRoutingProvider,
    RoutingProvider,
    ValhallaRoutingProvider,
)
from planner.integrations.timezones import TimezoneResolver
from planner.integrations.weather import OpenMeteoWeatherProvider
from planner.services.cache import Cache
from planner.services.heatmap import HeatmapConfig, HeatmapService
from planner.services.route_options import RouteOptionsService, RouteSearchConfig
from planner.services.trip_planner import PlannerConfig, TripPlanner
from planner.services.weather import WeatherService, WeatherServiceConfig


@dataclass(frozen=True)
class Services:
    planner: TripPlanner
    heatmap: HeatmapService
    geocoder: Geocoder
    timezones: TimezoneResolver
    rules: RiskRules
    cache: Cache

    @property
    def config(self) -> PlannerConfig:
        return self.planner.config


_override: Services | None = None


def get_services() -> Services:
    return _override or _build_services()


@contextmanager
def override_services(services: Services) -> Iterator[Services]:
    global _override
    previous, _override = _override, services
    try:
        yield services
    finally:
        _override = previous


@cache
def _build_services() -> Services:
    cfg = settings.PLANNER

    def http(service: str, timeout_s: float | None = None) -> HttpClient:
        return HttpClient(
            service,
            HttpConfig(
                user_agent=cfg["HTTP_USER_AGENT"],
                read_timeout_s=timeout_s or cfg["HTTP_TIMEOUT_S"],
            ),
        )

    weather = WeatherService(
        OpenMeteoWeatherProvider(
            # Short timeout: a slow batch degrades to "no data" for its cells instead of
            # holding the whole plan hostage.
            http("open-meteo", cfg["WEATHER_TIMEOUT_S"]),
            base_url=cfg["OPEN_METEO_URL"] or None,
            api_key=cfg["OPEN_METEO_API_KEY"],
        ),
        caches["default"],
        WeatherServiceConfig(
            lattice_deg=cfg["WEATHER_LATTICE_DEG"],
            cache_ttl_s=cfg["WEATHER_CACHE_TTL_S"],
            max_workers=cfg["WEATHER_MAX_WORKERS"],
        ),
    )
    route_options = RouteOptionsService(
        _routing_providers(cfg, http),
        caches["routes"],
        RouteSearchConfig(cache_ttl_s=cfg["ROUTE_CACHE_TTL_S"]),
    )
    rules = RiskRules(wind_basis=cfg["WIND_BASIS"])
    timezones = TimezoneResolver()
    planner_config = PlannerConfig(
        max_departure_ahead=timedelta(days=cfg["MAX_DEPARTURE_DAYS"]),
        truck_tare_weight_lbs=cfg["TRUCK_TARE_WEIGHT_LBS"],
        heatmap_max_cells=cfg["HEATMAP_MAX_CELLS"],
    )
    return Services(
        planner=TripPlanner(route_options, weather, rules, timezones, planner_config),
        heatmap=HeatmapService(
            weather,
            rules,
            HeatmapConfig(
                max_cells=max(cfg["HEATMAP_MAX_CELLS"], 1) * 2,
                max_ahead=timedelta(days=cfg["MAX_DEPARTURE_DAYS"] + 1),
            ),
        ),
        geocoder=FallbackGeocoder(
            [
                PhotonGeocoder(cfg["PHOTON_URL"], http("photon")),
                NominatimGeocoder(cfg["NOMINATIM_URL"], http("nominatim")),
            ]
        ),
        timezones=timezones,
        rules=rules,
        cache=caches["default"],
    )


def _routing_providers(cfg: dict, http) -> list[RoutingProvider]:
    factories = {
        "valhalla": lambda: ValhallaRoutingProvider(cfg["VALHALLA_URL"], http("valhalla")),
        "osrm": lambda: OsrmRoutingProvider(
            cfg["OSRM_URL"], http("osrm"), truck_max_speed_mph=cfg["TRUCK_MAX_SPEED_MPH"]
        ),
    }
    unknown = set(cfg["ROUTING_PROVIDERS"]) - factories.keys()
    if unknown:
        raise ValueError(f"Unknown routing provider(s): {', '.join(sorted(unknown))}")
    return [factories[name]() for name in cfg["ROUTING_PROVIDERS"]]
