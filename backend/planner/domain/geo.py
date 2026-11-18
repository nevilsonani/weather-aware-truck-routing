"""Geodesy helpers: distances, bearings, interpolation and polyline encoding.

Arrays of coordinates are ``(N, 2)`` float arrays ordered ``[lat, lon]`` in degrees.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

EARTH_RADIUS_M = 6_371_008.8
MAX_MERCATOR_LAT = 85.051_128_78


@dataclass(frozen=True, slots=True)
class LatLon:
    lat: float
    lon: float

    def __post_init__(self) -> None:
        if not (-90.0 <= self.lat <= 90.0) or not (-180.0 <= self.lon <= 180.0):
            raise ValueError(f"Coordinate out of range: {self.lat}, {self.lon}")

    def as_tuple(self) -> tuple[float, float]:
        return (self.lat, self.lon)


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres. Accepts scalars or NumPy arrays (broadcasting)."""
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = phi2 - phi1
    dlmb = np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def distance_m(a: LatLon, b: LatLon) -> float:
    return float(haversine_m(a.lat, a.lon, b.lat, b.lon))


def segment_lengths_m(coords: np.ndarray) -> np.ndarray:
    """Length of each consecutive segment of a polyline, shape ``(N-1,)``."""
    if len(coords) < 2:
        return np.zeros(0)
    return haversine_m(coords[:-1, 0], coords[:-1, 1], coords[1:, 0], coords[1:, 1])


def cumulative_distance_m(coords: np.ndarray) -> np.ndarray:
    """Distance from the first vertex to every vertex, shape ``(N,)``."""
    return np.concatenate(([0.0], np.cumsum(segment_lengths_m(coords))))


def initial_bearing_deg(a: LatLon, b: LatLon) -> float:
    phi1, phi2 = math.radians(a.lat), math.radians(b.lat)
    dlmb = math.radians(b.lon - a.lon)
    x = math.sin(dlmb) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlmb)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def destination_point(origin: LatLon, bearing_deg: float, dist_m: float) -> LatLon:
    """Point reached travelling ``dist_m`` from ``origin`` on an initial ``bearing_deg``."""
    delta = dist_m / EARTH_RADIUS_M
    theta = math.radians(bearing_deg)
    phi1, lmb1 = math.radians(origin.lat), math.radians(origin.lon)
    phi2 = math.asin(
        math.sin(phi1) * math.cos(delta) + math.cos(phi1) * math.sin(delta) * math.cos(theta)
    )
    lmb2 = lmb1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(phi1),
        math.cos(delta) - math.sin(phi1) * math.sin(phi2),
    )
    lon = (math.degrees(lmb2) + 540.0) % 360.0 - 180.0
    return LatLon(max(-90.0, min(90.0, math.degrees(phi2))), lon)


def interpolate_positions(
    cum_m: np.ndarray, coords: np.ndarray, targets_m: np.ndarray
) -> np.ndarray:
    """Positions at the given along-line distances (linear between vertices)."""
    lat = np.interp(targets_m, cum_m, coords[:, 0])
    lon = np.interp(targets_m, cum_m, coords[:, 1])
    return np.column_stack((lat, lon))


def resample(coords: np.ndarray, cum_m: np.ndarray, spacing_m: float) -> np.ndarray:
    """Evenly spaced points along a polyline (always includes both end points)."""
    total = float(cum_m[-1]) if len(cum_m) else 0.0
    if total <= 0 or spacing_m <= 0:
        return coords[:1].copy()
    count = max(2, math.ceil(total / spacing_m) + 1)
    return interpolate_positions(cum_m, coords, np.linspace(0.0, total, count))


def mercator_y(lat_deg):
    """Web-Mercator northing on the unit sphere (radians of 'stretched' latitude)."""
    lat = np.radians(np.clip(lat_deg, -MAX_MERCATOR_LAT, MAX_MERCATOR_LAT))
    return np.log(np.tan(np.pi / 4 + lat / 2))


def inverse_mercator_y(y):
    return np.degrees(2 * np.arctan(np.exp(y)) - np.pi / 2)


def simplify(coords: np.ndarray, tolerance_m: float) -> np.ndarray:
    """Douglas-Peucker simplification, processed breadth-first.

    Instead of recursing one segment at a time (thousands of tiny NumPy calls), every open
    segment is examined in a single vectorised pass per iteration, so a 30k-vertex route takes
    ~20 passes. Only used for the geometry sent to the browser: all distance/time calculations
    run on the full-resolution route.
    """
    n = len(coords)
    if n <= 2 or tolerance_m <= 0:
        return coords.copy()
    # Local equirectangular projection to metres is accurate enough for perpendicular offsets.
    lat0 = np.radians(coords[:, 0].mean())
    xy = np.column_stack((np.radians(coords[:, 1]) * np.cos(lat0), np.radians(coords[:, 0])))
    xy *= EARTH_RADIUS_M

    keep = np.zeros(n, dtype=bool)
    keep[[0, n - 1]] = True
    settled = keep.copy()  # kept, or proven within tolerance of their segment
    while True:
        open_pts = np.flatnonzero(~settled)
        if len(open_pts) == 0:
            break
        anchors = np.flatnonzero(keep)
        seg = np.searchsorted(anchors, open_pts) - 1
        a, b = xy[anchors[seg]], xy[anchors[seg + 1]]
        chord = b - a
        rel = xy[open_pts] - a
        length = np.hypot(chord[:, 0], chord[:, 1])
        cross = np.abs(chord[:, 0] * rel[:, 1] - chord[:, 1] * rel[:, 0])
        dist = np.where(
            length > 0, cross / np.maximum(length, 1e-9), np.hypot(rel[:, 0], rel[:, 1])
        )

        group_start = np.flatnonzero(np.r_[True, seg[1:] != seg[:-1]])
        group_max = np.maximum.reduceat(dist, group_start)
        group_of = np.repeat(np.arange(len(group_start)), np.diff(np.r_[group_start, len(seg)]))
        # The first maximum of each segment becomes a vertex if it exceeds the tolerance;
        # segments whose maximum is within tolerance are finished.
        candidates = np.flatnonzero(dist == group_max[group_of])
        _, first_idx = np.unique(group_of[candidates], return_index=True)
        winners = candidates[first_idx]
        split = winners[group_max[group_of[winners]] > tolerance_m]
        done = group_max[group_of] <= tolerance_m
        settled[open_pts[done]] = True
        keep[open_pts[split]] = True
        settled[open_pts[split]] = True
        if len(split) == 0:
            break
    return coords[keep]


# --- Google encoded polyline algorithm ----------------------------------------------------


def decode_polyline(encoded: str, precision: int = 6) -> np.ndarray:
    """Decode an encoded polyline into an ``(N, 2)`` ``[lat, lon]`` array."""
    factor = 10.0**precision
    coords: list[tuple[float, float]] = []
    index = lat = lon = 0
    length = len(encoded)
    while index < length:
        deltas = []
        for _ in range(2):
            result = shift = 0
            while True:
                if index >= length:
                    raise ValueError("Truncated polyline")
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lon += deltas[1]
        coords.append((lat / factor, lon / factor))
    return np.array(coords, dtype=float).reshape(-1, 2)


def encode_polyline(coords: np.ndarray, precision: int = 6) -> str:
    factor = 10**precision
    out: list[str] = []
    prev_lat = prev_lon = 0
    for lat_f, lon_f in coords:
        lat, lon = round(lat_f * factor), round(lon_f * factor)
        for delta in (lat - prev_lat, lon - prev_lon):
            value = ~(delta << 1) if delta < 0 else delta << 1
            while value >= 0x20:
                out.append(chr((0x20 | (value & 0x1F)) + 63))
                value >>= 5
            out.append(chr(value + 63))
        prev_lat, prev_lon = lat, lon
    return "".join(out)
