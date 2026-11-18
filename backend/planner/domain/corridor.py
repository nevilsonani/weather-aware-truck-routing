"""Trip-corridor sampling grid for the weather heat map.

Why a grid and not a KDE heat map: density heat maps (Leaflet.heat, MapLibre ``heatmap``)
encode *how many points* are nearby, so overlapping corridors would look "hotter" regardless of
the weather. We instead sample the forecast on a regular grid and colour each cell by its
value; the frontend paints it as a smoothly interpolated raster.

Rows are spaced evenly in **Web-Mercator Y** (not latitude) so the grid maps linearly onto the
map's pixel space and can be drawn as a single image overlay without distortion.

Only cells within ``buffer_m`` of any route are kept, and the cell size adapts so the corridor
never needs more than ``max_cells`` forecast locations (keeps weather API usage bounded).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from . import geo

M_PER_DEG_LAT = 110_574.0
M_PER_DEG_LON_EQ = 111_320.0
MAX_GRID_CELLS = 40_000  # bounding-box cells, protects the client renderer


@dataclass(frozen=True)
class GridSpec:
    west: float
    east: float
    south: float
    north: float
    nx: int
    ny: int

    def __post_init__(self) -> None:
        if self.nx < 1 or self.ny < 1 or self.nx * self.ny > MAX_GRID_CELLS:
            raise ValueError("Grid dimensions out of range")
        if not (self.west < self.east and self.south < self.north):
            raise ValueError("Grid bounds are inverted")
        if not (self.south >= -geo.MAX_MERCATOR_LAT and self.north <= geo.MAX_MERCATOR_LAT):
            raise ValueError("Grid latitude outside Web-Mercator range")

    def cell_centers(self, flat_indices: np.ndarray | None = None) -> np.ndarray:
        """``(K, 2)`` ``[lat, lon]`` of cell centres. Row 0 is the northern edge."""
        if flat_indices is None:
            flat_indices = np.arange(self.nx * self.ny)
        rows, cols = np.divmod(np.asarray(flat_indices), self.nx)
        y_north, y_south = geo.mercator_y(self.north), geo.mercator_y(self.south)
        y = y_north - (rows + 0.5) * (y_north - y_south) / self.ny
        lon = self.west + (cols + 0.5) * (self.east - self.west) / self.nx
        return np.column_stack((geo.inverse_mercator_y(y), lon))


@dataclass(frozen=True)
class CorridorGrid:
    spec: GridSpec
    cells: np.ndarray  # flat, row-major indices of cells inside the corridor
    buffer_m: float

    def centers(self) -> np.ndarray:
        return self.spec.cell_centers(self.cells)


def corridor_buffer_m(
    longest_route_m: float, *, fraction: float, minimum_m: float, maximum_m: float
) -> float:
    return float(np.clip(longest_route_m * fraction, minimum_m, maximum_m))


def build_corridor_grid(
    routes: Sequence[np.ndarray],
    route_lengths_m: Sequence[float],
    *,
    buffer_m: float,
    max_cells: int,
    min_cell_m: float = 4_000.0,
) -> CorridorGrid:
    """Choose a cell size so the corridor holds at most ``max_cells`` cells (and close to it)."""
    if not routes:
        raise ValueError("At least one route is required")
    spine = _route_spine(routes, buffer_m)
    approx_area = sum(route_lengths_m) * 2 * buffer_m + math.pi * buffer_m**2
    cell_m = max(min_cell_m, math.sqrt(approx_area / max_cells))

    best: CorridorGrid | None = None
    for _ in range(8):
        grid = _grid_for_cell_size(spine, buffer_m, cell_m)
        count = len(grid.cells)
        if count <= max_cells:
            if best is None or count > len(best.cells):
                best = grid
            if count >= 0.8 * max_cells or cell_m <= min_cell_m:
                break
            cell_m = max(min_cell_m, cell_m * math.sqrt(count / max_cells) * 0.97)
        else:
            cell_m *= math.sqrt(count / max_cells) * 1.03
    if best is None:  # pathological geometry: fall back to a guaranteed-small grid
        while True:
            cell_m *= 1.25
            best = _grid_for_cell_size(spine, buffer_m, cell_m)
            if len(best.cells) <= max_cells:
                break
    return best


def _route_spine(routes: Sequence[np.ndarray], buffer_m: float) -> np.ndarray:
    """Densified route vertices; spacing <= buffer/4 bounds the distance error to ~12 %."""
    spacing = max(buffer_m / 4, 500.0)
    parts = [geo.resample(r, geo.cumulative_distance_m(r), spacing) for r in routes if len(r) >= 2]
    return np.unique(np.round(np.concatenate(parts), 5), axis=0)


def _grid_for_cell_size(spine: np.ndarray, buffer_m: float, cell_m: float) -> CorridorGrid:
    lat_pad = buffer_m / M_PER_DEG_LAT
    south = max(float(spine[:, 0].min()) - lat_pad, -geo.MAX_MERCATOR_LAT + 0.01)
    north = min(float(spine[:, 0].max()) + lat_pad, geo.MAX_MERCATOR_LAT - 0.01)
    max_abs_lat = max(abs(south), abs(north))
    lon_pad = buffer_m / (M_PER_DEG_LON_EQ * max(math.cos(math.radians(max_abs_lat)), 0.05))
    west = max(float(spine[:, 1].min()) - lon_pad, -180.0)
    east = min(float(spine[:, 1].max()) + lon_pad, 180.0)

    # One Mercator unit (radian) spans R*cos(lat) metres on the ground; size cells at mid-lat.
    mid_lat = (south + north) / 2
    cell_merc = cell_m / (geo.EARTH_RADIUS_M * max(math.cos(math.radians(mid_lat)), 0.05))
    width_merc = math.radians(east - west)
    y_south, y_north = float(geo.mercator_y(south)), float(geo.mercator_y(north))
    nx = max(1, math.ceil(width_merc / cell_merc))
    ny = max(1, math.ceil((y_north - y_south) / cell_merc))
    while nx * ny > MAX_GRID_CELLS:
        cell_merc *= 1.1
        nx = max(1, math.ceil(width_merc / cell_merc))
        ny = max(1, math.ceil((y_north - y_south) / cell_merc))

    # Grow the bounds symmetrically so cells are exactly square in Mercator space.
    extra_x = (nx * cell_merc - width_merc) / 2
    extra_y = (ny * cell_merc - (y_north - y_south)) / 2
    spec = GridSpec(
        west=max(-180.0, west - math.degrees(extra_x)),
        east=min(180.0, east + math.degrees(extra_x)),
        south=max(-geo.MAX_MERCATOR_LAT, float(geo.inverse_mercator_y(y_south - extra_y))),
        north=min(geo.MAX_MERCATOR_LAT, float(geo.inverse_mercator_y(y_north + extra_y))),
        nx=nx,
        ny=ny,
    )
    centers = spec.cell_centers()
    inside = _min_distance_m(centers, spine) <= buffer_m
    return CorridorGrid(spec=spec, cells=np.flatnonzero(inside), buffer_m=buffer_m)


def _min_distance_m(points: np.ndarray, spine: np.ndarray, chunk: int = 2048) -> np.ndarray:
    """Equirectangular nearest-vertex distance; accurate to <1 % at corridor scales."""
    out = np.empty(len(points))
    spine_x = np.radians(spine[:, 1])
    spine_y = np.radians(spine[:, 0])
    for start in range(0, len(points), chunk):
        block = points[start : start + chunk]
        lat = np.radians(block[:, 0])[:, None]
        lon = np.radians(block[:, 1])[:, None]
        cos_mid = np.cos((lat + spine_y[None, :]) / 2)
        dx = (lon - spine_x[None, :]) * cos_mid
        dy = lat - spine_y[None, :]
        out[start : start + chunk] = np.sqrt(dx * dx + dy * dy).min(axis=1) * geo.EARTH_RADIUS_M
    return out
