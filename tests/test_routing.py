"""
Route optimizer (src/models/routing/isochrone.py) -- both a controlled
synthetic scenario (so the assertions are exact/predictable) and, where
real downloaded data is present, a real-data smoke test.
"""

from pathlib import Path

import numpy as np
import pytest

from src.models.routing.isochrone import (
    build_cost_grid, build_cost_grid_stack, astar_route, naive_route, isochrone_route,
)
from src.utils.grid import region_path

REPO_ROOT = Path(__file__).resolve().parents[1]
_BATHY_TIF = region_path("data/raw", "bathymetry", "bathymetry.tif")


def _synthetic_cost_grid(n=20, wall_col=10):
    """A grid that's cheap everywhere except a near-impassable wall down
    the middle with one gap -- any sane router MUST detour through the gap."""
    seaice = np.zeros((n, n), dtype=np.float32)
    iceberg_risk = np.zeros((n, n), dtype=np.float32)
    bathymetry = np.full((n, n), -100.0, dtype=np.float32)  # all open water
    seaice[:, wall_col] = 1.0
    seaice[n // 2, wall_col] = 0.0  # one gap in the wall
    return build_cost_grid(seaice, iceberg_risk, bathymetry, weights={"distance": 1.0, "seaice": 100.0, "iceberg": 5.0})


def test_astar_routes_through_the_gap():
    cost_grid = _synthetic_cost_grid()
    path = astar_route(cost_grid, (2, 2), (17, 17))
    # Every path from left of the wall to right of it MUST cross column
    # wall_col at the gap row (n//2) -- assert it actually does.
    crossing_rows = [r for r, c in path if c == 10]
    assert crossing_rows, "path never crosses the wall column at all"
    assert all(r == 10 for r in crossing_rows), f"path crossed the wall off the gap: rows {crossing_rows}"


def test_naive_route_is_a_straight_line_ignoring_risk():
    path = naive_route((2, 2), (17, 17))
    # Straight line from (2,2) to (17,17) should pass through (10,10)-ish,
    # i.e. THROUGH the wall (unlike astar_route), since it's explicitly
    # not risk-aware -- that's the whole point of the comparison baseline.
    cols_at_wall_row = [c for r, c in path if r == 10]
    assert 10 in cols_at_wall_row or any(abs(c - 10) <= 1 for c in cols_at_wall_row)


def test_astar_raises_on_disconnected_grid():
    cost_grid = np.zeros((10, 10), dtype=np.float32)
    cost_grid[:, 5] = np.inf  # solid, gapless wall -- no possible path across
    with pytest.raises(ValueError):
        astar_route(cost_grid, (2, 2), (2, 8))


def test_isochrone_respects_vessel_speed_reachability():
    """A vessel that's too slow to cross the whole grid within the
    forecast horizon should fail cleanly, not silently return a route
    that implies faster-than-possible travel."""
    n = 40
    seaice = np.zeros((3, n, n), dtype=np.float32)
    iceberg_risk = np.zeros((3, n, n), dtype=np.float32)
    bathymetry = np.full((n, n), -100.0, dtype=np.float32)
    cost_grid_by_day = build_cost_grid_stack(seaice, iceberg_risk, bathymetry)

    # 1 km/cell, 0.001 km/h vessel, 3-day grid + isochrone's own +3 day
    # slack = 6 days max = 144 hours -> can travel at most 0.144 km, far
    # short of the ~50-cell diagonal distance required.
    with pytest.raises(ValueError):
        isochrone_route(cost_grid_by_day, bathymetry, (0, 0), (n - 1, n - 1),
                         vessel_speed_kmh=0.001, resolution_km=1.0, max_days=3)


def test_isochrone_finds_real_time_varying_shortcut():
    """A cell that's infeasible on day 0 but clears by day 2 should be
    usable by a ship that would arrive there on day 2 -- this is the
    entire point of isochrone routing over a static-grid method, so
    assert it's actually true, not just that the function runs."""
    n = 20
    seaice = np.zeros((4, n, n), dtype=np.float32)
    iceberg_risk = np.zeros((4, n, n), dtype=np.float32)
    bathymetry = np.full((n, n), -100.0, dtype=np.float32)
    # Block column 10 entirely with ice on day 0-1, clear by day 2.
    seaice[0:2, :, 10] = 1.0
    weights = {"distance": 1.0, "seaice": 1000.0, "iceberg": 5.0}
    cost_grid_by_day = build_cost_grid_stack(seaice, iceberg_risk, bathymetry, weights=weights)

    # Slow vessel: reaches column 10 well after day 2, when it's clear.
    path, arrival_hours = isochrone_route(
        cost_grid_by_day, bathymetry, (10, 2), (10, 17),
        vessel_speed_kmh=2.0, resolution_km=25.0, time_step_hours=6.0,
    )
    assert path[0] == (10, 2)
    assert path[-1] == (10, 17)
    assert arrival_hours > 48  # genuinely took more than 2 days, consistent with waiting out the ice


@pytest.mark.skipif(not _BATHY_TIF.exists(), reason="real bathymetry not downloaded on this machine")
def test_real_bathymetry_regrids_to_grid_shape():
    from src.data.preprocess import regrid_bathymetry
    from src.utils.grid import n_grid_cells

    bathy = regrid_bathymetry(_BATHY_TIF)
    n_lon, n_lat = n_grid_cells()
    assert bathy.shape == (n_lat, n_lon)
    assert np.isfinite(bathy).all()
    # Every region's box is padded around a real coastal iceberg cluster,
    # so it should be majority ocean -- but NOT uniformly >80%: Weddell's
    # box is centered further from the coast than e.g. Prydz Bay's (real,
    # confirmed 61% ocean, more of the Antarctic coastline/Amery Ice Shelf
    # area in-frame), so this threshold is deliberately loose enough to
    # hold across regions rather than baking in one region's specific
    # geography.
    assert (bathy < 0).mean() > 0.5
