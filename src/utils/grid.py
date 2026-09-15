"""
Shared spatial grid definition — LOCKED. Every function that produces or
consumes a gridded array anywhere in this project imports its grid
parameters from here instead of hard-coding them locally.

Why this file exists: Layers 2a (sea-ice forecast) and 2b (iceberg drift)
must output on the *same* spatial grid and the *same* forecast timestamps,
or Phase 5 integration turns into a regridding nightmare the night before
the deadline.

--- Multi-region support (added 2026-09-15) ---

This project started Weddell-Sea-only. `REGIONS` below is a registry of
named `DomainGrid`s so multiple people can work on different Antarctic
sectors without stepping on each other's files: `GRID` and
`DEMO_ICEBERG_IDS` still resolve to a single "active" region (selected via
the `REGION` environment variable, default `weddell`), so every existing
import of `GRID`/`DEMO_ICEBERG_IDS` elsewhere in the codebase keeps working
completely unchanged — nothing outside this file needs to know a registry
exists. What DOES need to change elsewhere: any hardcoded `data/raw/...`
or `data/processed/...` path must switch to `region_path()` below so two
regions' processed files/checkpoints don't collide. See PROJECT_STATUS.md
for the full regional-expansion plan and why this was the blocking item.

Known real limitation: `DomainGrid` assumes `lon_min < lon_max` (a simple
non-wrapping box) — a region whose natural box crosses the antimeridian
(180°/-180°) isn't representable without extending `lat_lon_mesh()` etc.
to handle wraparound, which hasn't been done. `ross_sea` below is scoped
to avoid crossing it (see that entry's comment) rather than fix this
properly — a real simplification, not a silent bug, but worth knowing if
you pick a region near the dateline.
"""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DomainGrid:
    """Defines a bounded Southern Ocean sector every module operates on."""

    lon_min: float
    lon_max: float
    lat_min: float
    lat_max: float

    resolution_deg: float = 0.25   # ~25km at these latitudes, matches native NSIDC CDR grid
    # NOTE (deferred 2026-09-15): raising this to 0.125deg (~14km) -- AMSR2
    # Bremen's own native resolution is 6.25km, so regridding straight down
    # to 25km discards real sub-grid ice-edge structure. Deferred because a
    # combined "more data + higher resolution" run wasn't affordable in one
    # pass (~4x training compute) -- do it as its own dedicated run, per
    # region, once there's spare compute budget. See PROJECT_STATUS.md.

    forecast_horizon_days: int = 7  # within README's 5-10 day recommended range

    # preprocess.py regrids every source onto a plain lat/lon grid at
    # (resolution_deg) instead of native polar-stereographic meters —
    # xesmf/conservative regridding is a fragile install without
    # conda+ESMF on Windows, and .interp()-based lat/lon regridding is a
    # disclosed, deliberate MVP simplification (see preprocess.py).
    native_crs: str = "EPSG:4326"  # analysis grid is plain lat/lon
    source_crs: str = "EPSG:3412"  # NSIDC's native South polar stereographic CRS


# --- Region registry -------------------------------------------------------
#
# Bounding boxes below follow the same convention as the original Weddell
# Sea box: pad a real, currently-tracked iceberg cluster's extent by ~4-5
# degrees for open-water routing margin, rounded to clean numbers. Provenance
# for each is in that region's comment -- don't add a region here without a
# real data check (a live USNIC pull + a look at the BYU/NIC historical
# database) backing the bounding box and iceberg list, per this project's
# own no-guessing rule.

REGIONS = {
    # Original region. Bounds chosen 2026-09-12 from a live USNIC pull: a
    # real cluster of six tracked bergs (D32, D33A-D, D35) at lon -55.6 to
    # -39.1, lat -64.0 to -58.0, padded ~4 degrees each side.
    "weddell": DomainGrid(lon_min=-60.0, lon_max=-35.0, lat_min=-68.0, lat_max=-54.0),

    # Prydz Bay / Larsemann Hills, near India's Bharati station (69.41S
    # 76.19E). Bounds chosen 2026-09-15 from a live USNIC pull: real
    # tracked bergs D15A/B/C/D, D23, D34 at lon 74.7-82.1E, lat -69.44 to
    # -66.63, padded to comfortably include Bharati itself. Several of
    # these bergs have deep real historical tracks in the BYU/NIC database
    # (D15A: 3,392 rows, D15B: 3,682 rows) -- likely as strong a drift-
    # validation case as the Weddell cluster. Highest-priority expansion
    # region -- see PROJECT_STATUS.md section 6.
    "prydz_bay": DomainGrid(lon_min=66.0, lon_max=90.0, lat_min=-73.0, lat_max=-60.0),

    # Queen Maud Land, near India's Maitri station (70.77S 11.73E). Bounds
    # centered on Maitri itself, padded to a similar box size as the other
    # regions. Real iceberg presence here is thinner than Prydz Bay as of
    # the 2026-09-15 check -- only D37 (36.36E, -69.21) was found nearby,
    # outside this box. RE-CHECK the live USNIC feed and BYU database for
    # this region's actual iceberg cluster before relying on
    # REGION_ICEBERG_IDS["queen_maud_land"] below -- it's a provisional
    # placeholder, not a verified cluster like the other two regions.
    "queen_maud_land": DomainGrid(lon_min=-5.0, lon_max=25.0, lat_min=-75.0, lat_max=-62.0),

    # Ross Sea / McMurdo Sound (77.85S 166.67E) -- not an Indian station,
    # but a globally significant, heavily-trafficked research hub (US
    # McMurdo, NZ Scott Base). Bounds chosen 2026-09-15 from a live USNIC
    # pull: real tracked bergs B22A (164.79E, -69.88) and B22H (163.70E,
    # -70.21) fall inside; a third real nearby berg, B22F (-176.55E, i.e.
    # ~183E), was EXCLUDED because it's on the far side of the antimeridian
    # from McMurdo and this simple bounding-box grid can't represent a
    # region that wraps 180 degrees (see module docstring). If this
    # region's iceberg cluster needs B22F, the grid math needs a real
    # wraparound fix first, not a bounding-box hack.
    "ross_sea": DomainGrid(lon_min=150.0, lon_max=179.9, lat_min=-78.0, lat_max=-65.0),
}

# Per-region tracked iceberg cluster, same provenance as each region's
# bounding box above. Re-verify against a live USNIC pull before starting
# real work on a region -- positions/tracked-set membership drift over
# months (this is exactly why grid.py's original docstring says the same
# about the Weddell cluster).
REGION_ICEBERG_IDS = {
    "weddell": ["D32", "D33A", "D33B", "D33C", "D33D", "D35"],
    "prydz_bay": ["D15A", "D15B", "D15C", "D15D", "D23", "D34"],
    "queen_maud_land": ["D37"],  # provisional -- see REGIONS["queen_maud_land"]'s comment
    "ross_sea": ["B22A", "B22H"],  # B22F excluded, see REGIONS["ross_sea"]'s comment
}

# Active region for this process: set the REGION env var to switch (e.g.
# `REGION=prydz_bay python -m src.integration.pipeline`). Defaults to the
# original region so nothing changes for anyone not using this yet.
ACTIVE_REGION = os.environ.get("REGION", "weddell")
if ACTIVE_REGION not in REGIONS:
    raise ValueError(f"Unknown REGION '{ACTIVE_REGION}' -- choose one of {list(REGIONS)}")

# Import these two everywhere, exactly as before the region registry
# existed -- they now resolve to whichever region is active for this
# process instead of always being the Weddell Sea.
GRID = REGIONS[ACTIVE_REGION]
DEMO_ICEBERG_IDS = REGION_ICEBERG_IDS[ACTIVE_REGION]

_REPO_ROOT = Path(__file__).resolve().parents[2]


def region_path(top: str, *parts, region: str = None) -> Path:
    """Region-scoped path under a given top-level dir, e.g.
    `region_path("data/processed", "seaice_history.nc")` ->
    `data/processed/<region>/seaice_history.nc`, or
    `region_path("outputs", "manifest.json")` ->
    `outputs/<region>/manifest.json`. Use this for any new per-region file
    instead of a hardcoded path, so two regions' data/checkpoints/outputs
    never collide. Pass `region=` to build a path for a region other than
    the currently-active one (e.g. a script that compares two regions'
    results). Iceberg positions/tracks and raw AMSR2 sea-ice tiles are
    intentionally NOT region-scoped -- those sources are circumpolar and
    genuinely shared across every region, only the *processed/regridded*
    output, trained checkpoints, and demo outputs differ."""
    region = region or ACTIVE_REGION
    base = _REPO_ROOT / Path(top) / region
    return base / Path(*parts) if parts else base


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
    print(f"Active region: {ACTIVE_REGION}")
    print(GRID)
    print("Bounding box (west, south, east, north):", lat_lon_bounds())
    print("Approx grid shape (n_lon, n_lat):", n_grid_cells())
