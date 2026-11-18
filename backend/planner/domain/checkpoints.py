"""Checkpoint sampling along a route.

Checkpoints sit at mile 0, every ``interval`` miles, and at the destination. Each checkpoint
"owns" the stretch of road that is closer to it than to any other checkpoint (midpoint rule),
so the per-level mileage of a route always sums exactly to the route length.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from .geo import LatLon
from .hos import DrivingSchedule
from .route import DrivingRoute
from .units import miles_to_meters

# Drop a regular checkpoint that would sit within this distance of the destination marker.
MIN_FINAL_GAP_M = miles_to_meters(1.0)


@dataclass(frozen=True, slots=True)
class Checkpoint:
    index: int
    distance_m: float
    position: LatLon
    driving_s: float
    elapsed_s: float
    eta: datetime
    coverage_start_m: float
    coverage_end_m: float
    road: str | None

    @property
    def coverage_m(self) -> float:
        return self.coverage_end_m - self.coverage_start_m


def checkpoint_distances(total_m: float, interval_m: float) -> np.ndarray:
    if total_m <= 0 or interval_m <= 0:
        raise ValueError("Route length and interval must be positive")
    regular = np.arange(0.0, total_m, interval_m)
    regular = regular[(regular == 0.0) | (total_m - regular >= MIN_FINAL_GAP_M)]
    return np.append(regular, total_m)


def coverage_bounds(distances_m: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    midpoints = (distances_m[:-1] + distances_m[1:]) / 2
    starts = np.concatenate(([distances_m[0]], midpoints))
    ends = np.concatenate((midpoints, [distances_m[-1]]))
    return starts, ends


def sample_checkpoints(
    route: DrivingRoute,
    interval_m: float,
    departure_utc: datetime,
    schedule: DrivingSchedule,
) -> list[Checkpoint]:
    distances = checkpoint_distances(route.distance_m, interval_m)
    positions = route.positions_at(distances)
    driving = route.driving_time_at(distances)
    elapsed = schedule.elapsed_at(driving)
    starts, ends = coverage_bounds(distances)

    return [
        Checkpoint(
            index=i,
            distance_m=float(distances[i]),
            position=LatLon(float(positions[i, 0]), float(positions[i, 1])),
            driving_s=float(driving[i]),
            elapsed_s=float(elapsed[i]),
            eta=departure_utc + timedelta(seconds=float(elapsed[i])),
            coverage_start_m=float(starts[i]),
            coverage_end_m=float(ends[i]),
            road=route.road_at(float(distances[i])),
        )
        for i in range(len(distances))
    ]
