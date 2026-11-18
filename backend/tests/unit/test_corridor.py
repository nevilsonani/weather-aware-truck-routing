import numpy as np
import pytest

from planner.domain import geo
from planner.domain.corridor import GridSpec, build_corridor_grid, corridor_buffer_m

ROUTE = np.column_stack((np.linspace(39.7, 41.9, 400), np.linspace(-105.0, -87.6, 400)))
LENGTH = float(geo.cumulative_distance_m(ROUTE)[-1])


def build(max_cells=200, buffer_m=50_000):
    return build_corridor_grid([ROUTE], [LENGTH], buffer_m=buffer_m, max_cells=max_cells)


def test_cell_budget_is_respected_and_used():
    grid = build(max_cells=200)
    assert 0.6 * 200 <= len(grid.cells) <= 200


def test_every_cell_is_inside_the_buffer_and_the_route_is_covered():
    grid = build()
    centers = grid.centers()
    nearest = np.min(
        geo.haversine_m(
            centers[:, None, 0], centers[:, None, 1], ROUTE[None, :, 0], ROUTE[None, :, 1]
        ),
        axis=1,
    )
    assert nearest.max() <= grid.buffer_m * 1.02
    # Each route vertex lies in (or right next to) an included cell.
    cell_size = (grid.spec.east - grid.spec.west) / grid.spec.nx
    for lat, lon in ROUTE[::40]:
        gap = np.min(np.hypot(centers[:, 0] - lat, centers[:, 1] - lon))
        assert gap <= cell_size


def test_rows_are_evenly_spaced_in_mercator_space():
    spec = build().spec
    rows = spec.cell_centers(np.arange(0, spec.nx * spec.ny, spec.nx))[:, 0]
    steps = np.diff(geo.mercator_y(rows))
    assert np.allclose(steps, steps[0])
    assert rows[0] > rows[-1]  # row 0 is the northern edge


def test_buffer_scales_with_trip_length_within_bounds():
    kwargs = {"fraction": 0.04, "minimum_m": 30_000, "maximum_m": 80_000}
    assert corridor_buffer_m(100_000, **kwargs) == 30_000
    assert corridor_buffer_m(1_500_000, **kwargs) == 60_000
    assert corridor_buffer_m(5_000_000, **kwargs) == 80_000


def test_grid_spec_validation():
    with pytest.raises(ValueError, match="inverted"):
        GridSpec(west=1, east=0, south=0, north=1, nx=2, ny=2)
    with pytest.raises(ValueError, match="dimensions"):
        GridSpec(west=0, east=1, south=0, north=1, nx=1000, ny=1000)
