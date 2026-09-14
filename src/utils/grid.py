"""
Shared spatial grid definition — LOCKED. Every function that produces or
consumes a gridded array anywhere in this project imports its grid
parameters from here instead of hard-coding them locally.

Why this file exists: Layers 2a (sea-ice forecast) and 2b (iceberg drift)
must output on the *same* spatial grid and the *same* forecast timestamps,
or Phase 5 integration turns into a regridding nightmare the night before
the deadline.

How the bounds below were chosen (2026-09-12): A23a, the README's original
validation-case iceberg, has genuinely disintegrated (BAS/NASA Worldview
reporting through early-mid 2026 — it lost ~99% of its area and dropped
off the tracked list). Pulling the live USNIC Antarctic iceberg feed
(src/data/download_icebergs.py) on this date instead shows a real cluster
of six tracked bergs in the Weddell Sea — D32, D33A, D33B, D33C, D33D,
D35 — clustered at lon -55.6 to -39.1, lat -64.0 to -58.0. The box below
is that cluster's real bounding extent padded by ~4 degrees on each side
for open-water routing margin, rounded to clean numbers. This keeps the
README's own "Weddell Sea is the best-studied sector" framing while being
driven by an actual live data pull rather than a guess.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DomainGrid:
    """Defines the bounded Southern Ocean sector every module operates on."""

    lon_min: float = -60.0
    lon_max: float = -35.0
    lat_min: float = -68.0
    lat_max: float = -54.0

    resolution_deg: float = 0.25   # ~25km at these latitudes, matches native NSIDC CDR grid
    # NOTE (in progress): raising this to 0.125deg (~14km) -- AMSR2 Bremen's
    # own native resolution is 6.25km, so regridding straight down to 25km
    # discards real sub-grid ice-edge structure. Staged as one atomic swap
    # together with rebuilding data/processed/*.nc and retraining, once the
    # extended (2012-present) AMSR2 download finishes -- flipping this
    # alone first would break the live app (shape mismatch against the
    # still-0.25deg cached history files) for however long the rebuild
    # takes, which is avoidable by doing it all in one pass instead.

    forecast_horizon_days: int = 7  # within README's 5-10 day recommended range

    # preprocess.py regrids every source onto a plain lat/lon grid at
    # (resolution_deg) instead of native polar-stereographic meters —
    # xesmf/conservative regridding is a fragile install without
    # conda+ESMF on Windows, and .interp()-based lat/lon regridding is a
    # disclosed, deliberate MVP simplification (see preprocess.py).
    native_crs: str = "EPSG:4326"  # analysis grid is plain lat/lon
    source_crs: str = "EPSG:3412"  # NSIDC's native South polar stereographic CRS


# Import this instance everywhere instead of re-instantiating DomainGrid
# with different numbers in different files.
GRID = DomainGrid()

# The live-tracked iceberg cluster this build's demo scenario centers on
# (see docstring above for provenance/date). Update this list if you
# re-run download_icebergs.py later and the tracked set has changed.
DEMO_ICEBERG_IDS = ["D32", "D33A", "D33B", "D33C", "D33D", "D35"]


def lat_lon_bounds():
    """Convenience accessor: (lon_min, lat_min, lon_max, lat_max) tuple,
    matching the (west, south, east, north) order earthaccess/cdsapi expect
    for bounding_box / area arguments."""
    return (GRID.lon_min, GRID.lat_min, GRID.lon_max, GRID.lat_max)


def n_grid_cells():
    """Rough sanity-check helper: how many grid cells does this domain
    contain at the chosen resolution? Useful for eyeballing whether a
    ConvLSTM input tensor size is reasonable before you start training."""
    n_lon = int((GRID.lon_max - GRID.lon_min) / GRID.resolution_deg)
    n_lat = int((GRID.lat_max - GRID.lat_min) / GRID.resolution_deg)
    return n_lon, n_lat


def latlon_to_index(lat: float, lon: float):
    """Nearest (row, col) grid index for a lat/lon point, where row indexes
    lat_lon_mesh()'s lats (ascending south->north) and col indexes lons —
    the convention routing/isochrone.py's cost grids use."""
    lats, lons = lat_lon_mesh()
    row = int(round((lat - lats[0]) / GRID.resolution_deg))
    col = int(round((lon - lons[0]) / GRID.resolution_deg))
    row = min(max(row, 0), len(lats) - 1)
    col = min(max(col, 0), len(lons) - 1)
    return row, col


def index_to_latlon(row: int, col: int):
    """Inverse of latlon_to_index: (row, col) grid index -> (lat, lon)."""
    lats, lons = lat_lon_mesh()
    return float(lats[row]), float(lons[col])


def lat_lon_mesh():
    """1-D lat/lon coordinate arrays for the shared analysis grid (plain
    lat/lon at GRID.resolution_deg) — the common target every source
    gets regridded onto in preprocess.py, and what every downstream
    module (forecaster, drift engine, router) indexes into."""
    import numpy as np

    n_lon, n_lat = n_grid_cells()
    lons = GRID.lon_min + (np.arange(n_lon) + 0.5) * GRID.resolution_deg
    lats = GRID.lat_min + (np.arange(n_lat) + 0.5) * GRID.resolution_deg
    return lats, lons


if __name__ == "__main__":
    print(GRID)
    print("Bounding box (west, south, east, north):", lat_lon_bounds())
    print("Approx grid shape (n_lon, n_lat):", n_grid_cells())
