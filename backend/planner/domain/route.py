"""Provider-independent representation of a drivable route.

A :class:`DrivingRoute` stores, for every vertex, the cumulative distance *and* cumulative
driving time. Driving time comes from the routing engine per maneuver/segment, so ETAs reflect
slow urban stretches and fast interstates instead of a single average speed.
"""

from __future__ import annotations

import bisect
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from . import geo


@dataclass(frozen=True, slots=True)
class RoadSpan:
    start_m: float
    end_m: float
    name: str


@dataclass(frozen=True, slots=True)
class IndexSpan:
    """A run of polyline vertices ``[start, end]`` with its duration and road name."""

    start_index: int
    end_index: int
    duration_s: float
    name: str | None = None


@dataclass(frozen=True, eq=False)
class DrivingRoute:
    provider: str
    coords: np.ndarray  # (N, 2) [lat, lon]
    cum_distance_m: np.ndarray  # (N,) non-decreasing, starts at 0
    cum_driving_s: np.ndarray  # (N,) non-decreasing, starts at 0
    road_spans: tuple[RoadSpan, ...] = ()
    notices: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        n = len(self.coords)
        if n < 2 or len(self.cum_distance_m) != n or len(self.cum_driving_s) != n:
            raise ValueError("Route arrays must have matching length >= 2")

    @property
    def distance_m(self) -> float:
        return float(self.cum_distance_m[-1])

    @property
    def driving_s(self) -> float:
        return float(self.cum_driving_s[-1])

    def positions_at(self, distances_m: np.ndarray) -> np.ndarray:
        return geo.interpolate_positions(self.cum_distance_m, self.coords, distances_m)

    def driving_time_at(self, distances_m: np.ndarray) -> np.ndarray:
        return np.interp(distances_m, self.cum_distance_m, self.cum_driving_s)

    def distance_at_driving_time(self, driving_s: np.ndarray) -> np.ndarray:
        return np.interp(driving_s, self.cum_driving_s, self.cum_distance_m)

    def road_at(self, distance_m: float) -> str | None:
        starts = [span.start_m for span in self.road_spans]
        i = bisect.bisect_right(starts, distance_m) - 1
        if 0 <= i < len(self.road_spans) and distance_m <= self.road_spans[i].end_m:
            return self.road_spans[i].name
        return None

    def road_lengths(self) -> dict[str, float]:
        totals: dict[str, float] = defaultdict(float)
        for span in self.road_spans:
            totals[span.name] += span.end_m - span.start_m
        return dict(totals)

    def major_roads(self, limit: int = 2, min_share: float = 0.05) -> list[str]:
        """Longest roads on the route, listed in the order they are driven."""
        lengths = self.road_lengths()
        if not lengths:
            return []
        threshold = self.distance_m * min_share
        top = sorted(
            (name for name, length in lengths.items() if length >= threshold),
            key=lambda name: -lengths[name],
        )[:limit]
        first_seen = {span.name: span.start_m for span in reversed(self.road_spans)}
        return sorted(top, key=lambda name: first_seen[name])


def distribute_span_durations(seg_lengths_m: np.ndarray, spans: Sequence[IndexSpan]) -> np.ndarray:
    """Spread each span's duration over its segments proportionally to segment length."""
    durations = np.zeros(len(seg_lengths_m))
    for span in spans:
        lo, hi = span.start_index, min(span.end_index, len(seg_lengths_m))
        if hi <= lo or span.duration_s <= 0:
            continue
        lengths = seg_lengths_m[lo:hi]
        total = lengths.sum()
        if total > 0:
            durations[lo:hi] += span.duration_s * lengths / total
        else:
            durations[lo:hi] += span.duration_s / (hi - lo)
    return durations


def build_route(
    *,
    provider: str,
    coords: np.ndarray,
    segment_durations_s: np.ndarray,
    reported_distance_m: float | None = None,
    named_spans: Sequence[IndexSpan] = (),
    notices: Sequence[str] = (),
) -> DrivingRoute:
    """Assemble a :class:`DrivingRoute` from vertices and per-segment durations.

    Haversine distances are rescaled so the total equals the provider's reported length; this
    keeps checkpoint mile markers consistent with the route summary the user sees.
    """
    coords = np.asarray(coords, dtype=float)
    seg_lengths = geo.segment_lengths_m(coords)
    geometric_total = float(seg_lengths.sum())
    scale = 1.0
    if reported_distance_m and geometric_total > 0:
        scale = reported_distance_m / geometric_total
    cum_distance = np.concatenate(([0.0], np.cumsum(seg_lengths))) * scale
    cum_driving = np.concatenate(([0.0], np.cumsum(np.maximum(segment_durations_s, 0.0))))

    road_spans = tuple(
        RoadSpan(
            start_m=float(cum_distance[span.start_index]),
            end_m=float(cum_distance[min(span.end_index, len(coords) - 1)]),
            name=span.name,
        )
        for span in named_spans
        if span.name and span.end_index > span.start_index
    )
    return DrivingRoute(
        provider=provider,
        coords=coords,
        cum_distance_m=cum_distance,
        cum_driving_s=cum_driving,
        road_spans=road_spans,
        notices=tuple(notices),
    )


def overlap_fraction(a: DrivingRoute, b: DrivingRoute, tolerance_m: float = 400.0) -> float:
    """Share of route ``a``'s length that lies within ~``tolerance_m`` of route ``b``.

    Uses a hashed grid of ``b``'s densified vertices (dilated by one cell), so the cost is
    linear in route length rather than quadratic.
    """
    mean_lat = float(np.mean(np.concatenate((a.coords[:, 0], b.coords[:, 0]))))
    m_per_deg_lat = 110_574.0
    m_per_deg_lon = 111_320.0 * max(np.cos(np.radians(mean_lat)), 0.05)

    def cell_keys(points: np.ndarray) -> np.ndarray:
        ix = np.floor(points[:, 1] * m_per_deg_lon / tolerance_m).astype(np.int64)
        iy = np.floor(points[:, 0] * m_per_deg_lat / tolerance_m).astype(np.int64)
        return ix * 10_000_000 + iy

    b_points = geo.resample(b.coords, b.cum_distance_m, tolerance_m / 2)
    base = cell_keys(b_points)
    neighbours = np.concatenate(
        [base + dx * 10_000_000 + dy for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
    )
    a_points = geo.resample(a.coords, a.cum_distance_m, tolerance_m)
    return float(np.isin(cell_keys(a_points), np.unique(neighbours)).mean())
