"""OSRM routing adapter (fallback).

The public OSRM server only offers a *car* profile, so per-segment durations are capped at a
configurable truck top speed. It keeps the app usable if the truck-capable provider is down.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

from planner.domain import geo
from planner.domain.errors import NoRouteFound, UpstreamUnavailable
from planner.domain.geo import LatLon
from planner.domain.route import DrivingRoute, IndexSpan, build_route
from planner.domain.units import mph_to_mps

from ..http import HttpClient, json_or_raise
from .base import VehicleProfile, normalize_road_name

NO_ROUTE_CODES = {"NoRoute", "NoSegment", "NoMatch"}


class OsrmRoutingProvider:
    name = "osrm"

    def __init__(
        self, base_url: str, http: HttpClient, *, truck_max_speed_mph: float = 65.0
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.http = http
        self.max_speed_mps = mph_to_mps(truck_max_speed_mph)
        self.truck_max_speed_mph = truck_max_speed_mph

    def route(
        self, waypoints: Sequence[LatLon], vehicle: VehicleProfile, *, alternatives: int = 0
    ) -> list[DrivingRoute]:
        del vehicle  # the public car profile cannot use truck attributes
        coordinates = ";".join(f"{p.lon:.6f},{p.lat:.6f}" for p in waypoints)
        params = {
            "overview": "full",
            "geometries": "polyline6",
            "annotations": "distance,duration",
            "steps": "true",
            "continue_straight": "true",
            "alternatives": str(alternatives) if alternatives and len(waypoints) == 2 else "false",
        }
        response = self.http.get(f"{self.base_url}/route/v1/driving/{coordinates}", params=params)
        data = json_or_raise(response, "OSRM")
        code = data.get("code")
        if code in NO_ROUTE_CODES:
            raise NoRouteFound(
                "No drivable route was found between these locations.",
                details={"provider": self.name, "provider_code": code},
            )
        if code != "Ok":
            raise UpstreamUnavailable(f"OSRM error: {data.get('message') or code}")
        return [self._parse_route(r) for r in data.get("routes", [])]

    def _parse_route(self, raw: dict[str, Any]) -> DrivingRoute:
        coords = geo.decode_polyline(raw["geometry"], precision=6)
        seg_lengths = geo.segment_lengths_m(coords)
        durations = np.array(
            [d for leg in raw["legs"] for d in leg.get("annotation", {}).get("duration", [])],
            dtype=float,
        )
        if len(durations) != len(seg_lengths):  # defensive: spread the total by length
            total = float(raw["duration"])
            durations = seg_lengths / max(seg_lengths.sum(), 1.0) * total
        durations = np.maximum(durations, seg_lengths / self.max_speed_mps)

        return build_route(
            provider=self.name,
            coords=coords,
            segment_durations_s=durations,
            reported_distance_m=float(raw["distance"]),
            named_spans=self._road_spans(raw, seg_lengths),
            notices=(
                "Truck routing was unavailable; using car routing with truck speeds capped at "
                f"{self.truck_max_speed_mph:.0f} mph.",
            ),
        )

    @staticmethod
    def _road_spans(raw: dict[str, Any], seg_lengths: np.ndarray) -> list[IndexSpan]:
        """Map OSRM steps (which carry distances, not vertex indices) onto the geometry."""
        cum = np.concatenate(([0.0], np.cumsum(seg_lengths)))
        scale = cum[-1] / max(float(raw["distance"]), 1.0)
        spans: list[IndexSpan] = []
        travelled = 0.0
        for leg in raw["legs"]:
            for step in leg.get("steps", []):
                start = int(np.searchsorted(cum, travelled * scale, side="right") - 1)
                travelled += float(step.get("distance", 0.0))
                end = int(np.searchsorted(cum, travelled * scale, side="left"))
                name = normalize_road_name(step.get("ref") or step.get("name"))
                spans.append(IndexSpan(max(start, 0), min(end, len(cum) - 1), 0.0, name))
        return spans
