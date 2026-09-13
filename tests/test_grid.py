"""Shared grid: shape consistency and index<->lat/lon round-tripping.
These are the invariants every other module silently depends on."""

from src.utils.grid import GRID, lat_lon_mesh, latlon_to_index, index_to_latlon, n_grid_cells


def test_grid_shape_consistency():
    lats, lons = lat_lon_mesh()
    n_lon, n_lat = n_grid_cells()
    assert len(lats) == n_lat
    assert len(lons) == n_lon


def test_grid_bounds_sane():
    # Locked per grid.py's own docstring -- catches an accidental edit.
    assert GRID.lon_min < GRID.lon_max
    assert GRID.lat_min < GRID.lat_max
    assert GRID.resolution_deg > 0
    assert GRID.forecast_horizon_days > 0


def test_index_latlon_roundtrip():
    lats, lons = lat_lon_mesh()
    mid_lat, mid_lon = float(lats[len(lats) // 2]), float(lons[len(lons) // 2])
    row, col = latlon_to_index(mid_lat, mid_lon)
    back_lat, back_lon = index_to_latlon(row, col)
    assert abs(back_lat - mid_lat) < GRID.resolution_deg
    assert abs(back_lon - mid_lon) < GRID.resolution_deg


def test_latlon_to_index_clamps_out_of_bounds():
    # A point far outside the domain shouldn't raise or return a
    # negative/overflowing index -- it should clamp to the nearest edge.
    row, col = latlon_to_index(-90.0, -180.0)
    assert 0 <= row < len(lat_lon_mesh()[0])
    assert 0 <= col < len(lat_lon_mesh()[1])
