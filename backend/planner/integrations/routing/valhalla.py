"""Valhalla routing adapter (truck costing).

Valhalla is the primary provider because it supports a real ``truck`` costing model: truck
speeds, truck restrictions and the vehicle's gross weight (weight-limited bridges/roads), which
ties the user's load weight into route legality, not just weather risk.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import numpy as np

from planner.domain import geo
from planner.domain.errors import NoRouteFound, UpstreamUnavailable
from planner.domain.geo import LatLon
from planner.domain.route import DrivingRoute, IndexSpan, build_route, distribute_span_durations
from planner.domain.units import METERS_PER_KM

from ..http import HttpClient, json_or_raise
from .base import VehicleProfile, normalize_road_name

logger = logging.getLogger(__name__)

# https://valhalla.github.io/valhalla/api/turn-by-turn/api-reference/#http-status-codes-and-conditions
# Only genuine "no path" answers are final. Everything else - notably 154, the public server's
# 1,500 km distance cap - is a limitation of this provider, so the caller may fall back.
NO_ROUTE_ERROR_CODES = {170, 171, 172, 442, 443, 444}


class ValhallaRoutingProvider:
    name = "valhalla"

    def __init__(self, base_url: str, http: HttpClient) -> None:
        self.base_url = base_url.rstrip("/")
        self.http = http

    def route(
        self, waypoints: Sequence[LatLon], vehicle: VehicleProfile, *, alternatives: int = 0
    ) -> list[DrivingRoute]:
        payload = self._payload(waypoints, vehicle, alternatives)
        response = self.http.post(f"{self.base_url}/route", json=payload)
        data = json_or_raise(response, "Valhalla")
        if response.status_code >= 400:
            self._raise_for_error(data)

        trips = [data["trip"], *(alt["trip"] for alt in data.get("alternates", []))]
        return [self._parse_trip(trip) for trip in trips]

    @staticmethod
    def _payload(
        waypoints: Sequence[LatLon], vehicle: VehicleProfile, alternatives: int
    ) -> dict[str, Any]:
        locations = [
            {
                "lat": p.lat,
                "lon": p.lon,
                # "through" = pass-through via point: no U-turn, no extra leg.
                "type": "break" if i in (0, len(waypoints) - 1) else "through",
            }
            for i, p in enumerate(waypoints)
        ]
        payload: dict[str, Any] = {
            "locations": locations,
            "costing": "truck",
            "costing_options": {"truck": {"weight": round(vehicle.gross_weight_kg / 1000, 2)}},
            "units": "kilometers",
            "directions_type": "maneuvers",
        }
        if alternatives > 0 and len(waypoints) == 2:
            payload["alternates"] = alternatives
        return payload

    @staticmethod
    def _raise_for_error(data: dict[str, Any]) -> None:
        code = data.get("error_code")
        message = data.get("error") or "Routing request failed"
        if code in NO_ROUTE_ERROR_CODES:
            raise NoRouteFound(
                "No drivable truck route was found between these locations.",
                details={
                    "provider": "valhalla",
                    "provider_code": code,
                    "provider_message": message,
                },
            )
        logger.warning("Valhalla rejected request: %s (%s)", message, code)
        raise UpstreamUnavailable(f"Valhalla could not serve this request: {message}")

    def _parse_trip(self, trip: dict[str, Any]) -> DrivingRoute:
        coords_parts: list[np.ndarray] = []
        spans: list[IndexSpan] = []
        total = 0
        for leg in trip["legs"]:
            shape = geo.decode_polyline(leg["shape"], precision=6)
            # Consecutive legs share their junction vertex: leg k's shape[0] is the last
            # vertex already collected.
            base = total - 1 if total else 0
            for m in leg.get("maneuvers", []):
                names = m.get("street_names") or []
                spans.append(
                    IndexSpan(
                        start_index=m["begin_shape_index"] + base,
                        end_index=m["end_shape_index"] + base,
                        duration_s=float(m.get("time", 0.0)),
                        name=normalize_road_name(names[0]) if names else None,
                    )
                )
            new_vertices = shape[1:] if total else shape
            coords_parts.append(new_vertices)
            total += len(new_vertices)

        coords = np.concatenate(coords_parts)
        durations = distribute_span_durations(geo.segment_lengths_m(coords), spans)
        # Maneuver times can omit tiny amounts; reconcile with the trip total.
        reported_time = float(trip["summary"]["time"])
        if durations.sum() > 0:
            durations *= reported_time / durations.sum()
        return build_route(
            provider=self.name,
            coords=coords,
            segment_durations_s=durations,
            reported_distance_m=float(trip["summary"]["length"]) * METERS_PER_KM,
            named_spans=spans,
        )
