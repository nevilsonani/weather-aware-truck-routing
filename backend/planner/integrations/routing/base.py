from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from planner.domain.geo import LatLon
from planner.domain.route import DrivingRoute


@dataclass(frozen=True)
class VehicleProfile:
    """What the routing engine needs to know about the truck."""

    gross_weight_kg: float


class RoutingProvider(Protocol):
    name: str

    def route(
        self, waypoints: Sequence[LatLon], vehicle: VehicleProfile, *, alternatives: int = 0
    ) -> list[DrivingRoute]:
        """Return the best route through ``waypoints`` plus up to ``alternatives`` others.

        Alternatives are only requested for two-point (origin/destination) queries.

        Raises:
            NoRouteFound: the provider answered but there is no drivable route.
            UpstreamUnavailable: the provider could not be reached or failed.
        """
        ...


_ROAD_REF = re.compile(r"^(I|US|SR|[A-Z]{2})[ -](\d+[A-Z]?)(?: (?:North|South|East|West))?$")


def normalize_road_name(name: str | None) -> str | None:
    """``"I 76 East"`` -> ``"I-76"``; other names are returned trimmed."""
    if not name:
        return None
    name = name.strip()
    match = _ROAD_REF.match(name)
    return f"{match.group(1)}-{match.group(2)}" if match else name
