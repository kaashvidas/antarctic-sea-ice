"""Shared grid: shape consistency and index<->lat/lon round-tripping.
These are the invariants every other module silently depends on."""

from src.utils.grid import (
    DOMAINS, GRID, MAITRI_INDIA_BAY, domain_public_metadata, get_domain,
    lat_lon_mesh, latlon_to_index, index_to_latlon, n_grid_cells,
)


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


def test_named_domains_include_maitri_corridor():
    domain = get_domain("maitri_india_bay")
    assert domain is MAITRI_INDIA_BAY
    assert domain.contains(-70.3166667, 12.3166667)
    assert domain.contains(-70.7661111, 11.7322222)
    assert set(DOMAINS) >= {"weddell_validation", "maitri_india_bay"}


def test_helpers_accept_non_active_domain():
    lats, lons = lat_lon_mesh(MAITRI_INDIA_BAY)
    n_lon, n_lat = n_grid_cells(MAITRI_INDIA_BAY)
    assert (len(lons), len(lats)) == (n_lon, n_lat)
    row, col = latlon_to_index(-70.3166667, 12.3166667, MAITRI_INDIA_BAY)
    lat, lon = index_to_latlon(row, col, MAITRI_INDIA_BAY)
    assert abs(lat - -70.3166667) < MAITRI_INDIA_BAY.resolution_deg
    assert abs(lon - 12.3166667) < MAITRI_INDIA_BAY.resolution_deg


def test_maitri_metadata_distinguishes_station_from_ship_endpoint():
    metadata = domain_public_metadata(MAITRI_INDIA_BAY)
    markers = {marker["id"]: marker for marker in metadata["site_markers"]}
    assert markers["india_bay"]["navigable"] is True
    assert markers["maitri_station"]["navigable"] is False
    assert metadata["default_route"]["goal"]["lat"] == markers["india_bay"]["lat"]
