"""
Phase 5 — integration/orchestration.

One script chaining Layer 2 -> Layer 3: sea-ice forecast -> iceberg drift
(coupled to that forecast) -> route optimization -> GeoJSON/PNG output for
the dashboard.

Data honesty note (2026-09-12): the iceberg cluster (real USNIC positions
+ sizes), the bathymetry (real NCEI DEM export), and the drift physics
(real WDE17 port) are genuine. Sea-ice concentration and wind/current
forcing are NOT yet real — NSIDC/CDS downloads are blocked on Earthdata
and CDS credentials not being present on this machine (see
src/data/download_seaice.py / download_era5.py). Until those land, this
pipeline runs on clearly-labeled synthetic placeholders for those two
inputs specifically (see `PLACEHOLDER_INPUTS` below and each function's
docstring) so the rest of the system — drift, routing, GeoJSON, dashboard
— is demonstrably complete and trivial to re-run once real forcing data
exists. Swap point: `placeholder_seaice_concentration()` and
`placeholder_forcing_fields()` below are the only two functions that need
replacing with real regridded NSIDC/ERA5 data.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[2]))
from src.utils.grid import (  # noqa: E402
    GRID, DEMO_ICEBERG_IDS, lat_lon_mesh, latlon_to_index, index_to_latlon, n_grid_cells,
)
from src.data.preprocess import regrid_bathymetry  # noqa: E402
from src.models.iceberg_drift.wagner_model import IcebergState, step  # noqa: E402
from src.models.routing.isochrone import build_cost_grid, astar_route, naive_route  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "outputs"
ICEBERG_CSV = Path(__file__).resolve().parents[2] / "data" / "raw" / "icebergs" / "antarctic_icebergs_latest.csv"
BATHY_TIF = Path(__file__).resolve().parents[2] / "data" / "raw" / "bathymetry" / "weddell_bathymetry.tif"

NM_TO_M = 1852.0
ASSUMED_THICKNESS_M = 250.0  # typical Antarctic tabular iceberg draft/thickness range (200-300m); not measured
N_ENSEMBLE = 8               # perturbed drift members per iceberg, for the uncertainty cone
DT_SECONDS = 24 * 3600

PLACEHOLDER_INPUTS = ["sea_ice_concentration", "wind_field", "current_field"]


def load_iceberg_cluster(iceberg_ids=None, csv_path: Path = ICEBERG_CSV) -> list:
    """Real USNIC positions/sizes for this build's demo cluster (see
    grid.py's DEMO_ICEBERG_IDS docstring for provenance). Thickness isn't
    in USNIC's table -- ASSUMED_THICKNESS_M is a disclosed literature-range
    assumption, not a measurement."""
    iceberg_ids = iceberg_ids or DEMO_ICEBERG_IDS
    if not csv_path.exists():
        raise FileNotFoundError(f"{csv_path} not found — run src/data/download_icebergs.py first.")

    df = pd.read_csv(csv_path)
    df.columns = [c.strip() for c in df.columns]
    df["Iceberg"] = df["Iceberg"].str.strip()
    cluster = df[df["Iceberg"].isin(iceberg_ids)]
    missing = set(iceberg_ids) - set(cluster["Iceberg"])
    if missing:
        print(f"WARNING: {missing} not found in the latest USNIC pull — "
              "they may have merged, broken up, or dropped off tracking "
              "since grid.py's DEMO_ICEBERG_IDS was locked. Continuing "
              "with whatever's still tracked.")

    states = []
    for _, row in cluster.iterrows():
        states.append({
            "id": row["Iceberg"],
            "state": IcebergState(
                lat=float(row["Latitude"]), lon=float(row["Longitude"]),
                length_m=float(row["Length (NM)"]) * NM_TO_M,
                width_m=float(row["Width (NM)"]) * NM_TO_M,
                thickness_m=ASSUMED_THICKNESS_M,
            ),
        })
    return states


def placeholder_seaice_concentration() -> np.ndarray:
    """
    SYNTHETIC PLACEHOLDER pending real NSIDC data (blocked on Earthdata
    credentials — see module docstring). Returns a (n_lat, n_lon) array,
    0-1, shaped only to be directionally plausible for the Weddell Sea in
    September (austral winter / near seasonal-maximum ice extent): higher
    concentration toward the ice shelf in the south, lower toward the
    open Scotia Sea in the north, with a smooth marginal ice zone between
    -- NOT a forecast, don't present it as one.
    """
    lats, lons = lat_lon_mesh()
    lat_grid, _ = np.meshgrid(lats, lons, indexing="ij")
    # linear ramp: near-total cover at the southern edge, open water north
    frac_south_to_north = (lat_grid - GRID.lat_min) / (GRID.lat_max - GRID.lat_min)
    conc = np.clip(0.95 - 0.85 * frac_south_to_north, 0.0, 1.0)
    return conc.astype(np.float32)


def placeholder_forcing_fields():
    """
    SYNTHETIC PLACEHOLDER pending real ERA5/CMEMS data (see module
    docstring). Returns constant (wind_u, wind_v, current_u, current_v)
    in m/s, loosely representative of the Weddell Gyre's mean clockwise
    circulation and the prevailing westerlies at these latitudes -- NOT a
    real forecast.
    """
    wind_u, wind_v = 6.0, -2.0        # m/s, westerly-dominant
    current_u, current_v = -0.03, 0.05  # m/s, weak clockwise gyre component
    return wind_u, wind_v, current_u, current_v


def run_drift_ensemble(iceberg_cluster, horizon_days: int = GRID.forecast_horizon_days,
                        n_ensemble: int = N_ENSEMBLE, seed: int = 0):
    """
    For each tracked iceberg, run the real WDE17 physics (deterministic
    center member + n_ensemble perturbed members with randomized
    wind/current forcing) forward `horizon_days`, coupled to the
    (currently placeholder) sea-ice concentration field. This is what
    produces the drift PROBABILITY CONE, not a single deterministic line
    — per the README's uncertainty-first rule.

    Returns {iceberg_id: [ [ (lat,lon) per day, for member 0 ], ... ]}
    """
    rng = np.random.default_rng(seed)
    seaice_conc = placeholder_seaice_concentration()
    base_wind_u, base_wind_v, base_current_u, base_current_v = placeholder_forcing_fields()

    tracks = {}
    for entry in iceberg_cluster:
        iceberg_id, base_state = entry["id"], entry["state"]
        member_tracks = []
        for m in range(n_ensemble + 1):
            if m == 0:
                wind_u, wind_v = base_wind_u, base_wind_v
                current_u, current_v = base_current_u, base_current_v
            else:
                wind_u = base_wind_u * (1 + rng.normal(0, 0.2))
                wind_v = base_wind_v * (1 + rng.normal(0, 0.2))
                current_u = base_current_u * (1 + rng.normal(0, 0.3))
                current_v = base_current_v * (1 + rng.normal(0, 0.3))

            state = IcebergState(**vars(base_state))
            track = [(state.lat, state.lon)]
            for _ in range(horizon_days):
                row, col = latlon_to_index(state.lat, state.lon)
                local_conc = float(seaice_conc[row, col])
                state = step(
                    state, DT_SECONDS,
                    wind_uv=(wind_u, wind_v), current_uv=(current_u, current_v),
                    seaice_uv=(current_u, current_v),  # no separate ice-motion product yet -> approximate with current
                    seaice_concentration=local_conc,
                )
                track.append((state.lat, state.lon))
            member_tracks.append(track)
        tracks[iceberg_id] = member_tracks
    return tracks


def rasterize_iceberg_risk(tracks: dict) -> np.ndarray:
    """
    Turn the drift ensembles into a single (n_lat, n_lon) risk grid,
    0-1: for every ensemble member's position on every forecast day,
    deposit a Gaussian blob (sigma ~ a couple grid cells) and take the
    per-cell max across all icebergs/members/days, then normalize. Max
    (not sum) so a route is penalized for entering ANY iceberg's swept
    area, not artificially double-penalized where cones overlap.
    """
    n_lon, n_lat = n_grid_cells()
    risk = np.zeros((n_lat, n_lon), dtype=np.float32)
    lats, lons = lat_lon_mesh()
    lat_grid, lon_grid = np.meshgrid(lats, lons, indexing="ij")

    sigma_deg = 2 * GRID.resolution_deg
    for member_tracks in tracks.values():
        for track in member_tracks:
            for lat, lon in track:
                d2 = (lat_grid - lat) ** 2 + (lon_grid - lon) ** 2
                blob = np.exp(-d2 / (2 * sigma_deg ** 2))
                risk = np.maximum(risk, blob)
    return risk


def find_open_water(bathymetry: np.ndarray, near_lat: float, near_lon: float, max_radius_cells: int = 20):
    """Snap a rough (lat, lon) to the nearest real open-water cell (depth
    < -10m, matching isochrone.build_cost_grid's own feasibility cutoff)
    by expanding a search box outward -- avoids picking a start/goal that
    build_cost_grid would mark infeasible."""
    row0, col0 = latlon_to_index(near_lat, near_lon)
    n_lat, n_lon = bathymetry.shape
    for radius in range(max_radius_cells + 1):
        for dr in range(-radius, radius + 1):
            for dc in range(-radius, radius + 1):
                r, c = row0 + dr, col0 + dc
                if 0 <= r < n_lat and 0 <= c < n_lon and bathymetry[r, c] < -10:
                    return r, c
    raise ValueError(f"No open water found within {max_radius_cells} cells of ({near_lat}, {near_lon})")


def run_pipeline(forecast_date: str = None):
    """
    Chain: real iceberg cluster -> real drift physics ensemble -> risk
    raster -> real bathymetry -> cost grid -> A*/naive routes -> GeoJSON.
    See module docstring for which inputs are still placeholders.
    """
    print(f"Domain grid: {GRID}")
    forecast_date = forecast_date or pd.Timestamp.today().strftime("%Y-%m-%d")

    iceberg_cluster = load_iceberg_cluster()
    print(f"Loaded {len(iceberg_cluster)} real tracked icebergs: {[e['id'] for e in iceberg_cluster]}")

    tracks = run_drift_ensemble(iceberg_cluster)
    iceberg_risk = rasterize_iceberg_risk(tracks)

    if not BATHY_TIF.exists():
        raise FileNotFoundError(f"{BATHY_TIF} not found — run src/data/download_bathymetry.py first.")
    bathymetry = regrid_bathymetry(BATHY_TIF)

    seaice_forecast = placeholder_seaice_concentration()
    cost_grid = build_cost_grid(seaice_forecast, iceberg_risk, bathymetry)

    # Start/goal: real open-water points bracketing the tracked cluster --
    # a southern approach near D33A/D33D and a northern approach near D32,
    # snapped onto real bathymetry-confirmed open water.
    start = find_open_water(bathymetry, -65.5, -57.0)
    goal = find_open_water(bathymetry, -56.5, -37.0)
    print(f"start grid idx={start} ({index_to_latlon(*start)}), goal grid idx={goal} ({index_to_latlon(*goal)})")

    optimized_path = astar_route(cost_grid, start, goal)
    naive_path = naive_route(start, goal)

    optimized_latlon = [index_to_latlon(r, c)[::-1] for r, c in optimized_path]  # (lon, lat) for GeoJSON
    naive_latlon = [index_to_latlon(r, c)[::-1] for r, c in naive_path]

    geojson_path = routes_to_geojson(optimized_latlon, naive_latlon, iceberg_cluster, tracks)
    seaice_paths = write_seaice_images(seaice_forecast)
    manifest_path = write_manifest(forecast_date, iceberg_cluster, seaice_paths)
    print(f"Pipeline complete. Optimized route: {len(optimized_path)} pts, "
          f"naive route: {len(naive_path)} pts. Outputs: {geojson_path}, {manifest_path}")
    return geojson_path


def write_seaice_images(seaice_forecast: np.ndarray, out_subdir: str = "seaice") -> list:
    """
    Render one georeferenced PNG per forecast day for the dashboard's
    Leaflet ImageOverlay layer (lighter than emitting ~5600 GeoJSON
    polygons per day). Currently all days render the same placeholder
    field (see module docstring) — once real day-by-day NSIDC/ConvLSTM
    output exists, pass a (day, lat, lon) array here instead and this
    loop needs no other changes.
    """
    import matplotlib.cm as cm

    out_dir = OUTPUT_DIR / out_subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    rgba = (cm.Blues(seaice_forecast) * 255).astype(np.uint8)

    from PIL import Image
    paths = []
    for day in range(GRID.forecast_horizon_days + 1):
        img = Image.fromarray(rgba[::-1, :, :], mode="RGBA")  # flip: image row 0 = north
        out_path = out_dir / f"day_{day:02d}.png"
        img.save(out_path)
        paths.append(out_path.relative_to(OUTPUT_DIR).as_posix())  # forward slashes for URLs, even on Windows
    print(f"Saved {len(paths)} sea-ice overlay images to {out_dir}")
    return paths


def routes_to_geojson(optimized_route, naive_route_pts, iceberg_cluster, tracks,
                       out_name: str = "routes.geojson") -> Path:
    """Convert routes + iceberg tracks/cones into a GeoJSON FeatureCollection
    the dashboard can drop straight into a Leaflet layer. All coordinates
    are [lon, lat] per the GeoJSON spec."""
    features = [
        {"type": "Feature", "properties": {"route_type": "optimized"},
         "geometry": {"type": "LineString", "coordinates": optimized_route}},
        {"type": "Feature", "properties": {"route_type": "naive"},
         "geometry": {"type": "LineString", "coordinates": naive_route_pts}},
    ]

    for entry in iceberg_cluster:
        iceberg_id, state = entry["id"], entry["state"]
        member_tracks = tracks.get(iceberg_id, [])
        if not member_tracks:
            continue

        features.append({
            "type": "Feature",
            "properties": {"feature_type": "iceberg_current", "iceberg_id": iceberg_id,
                            "length_m": state.length_m, "width_m": state.width_m},
            "geometry": {"type": "Point", "coordinates": [state.lon, state.lat]},
        })

        center_track = member_tracks[0]
        features.append({
            "type": "Feature",
            "properties": {"feature_type": "iceberg_predicted_track", "iceberg_id": iceberg_id},
            "geometry": {"type": "LineString", "coordinates": [[lon, lat] for lat, lon in center_track]},
        })

        final_positions = [track[-1] for track in member_tracks]
        lats = [p[0] for p in final_positions]
        lons = [p[1] for p in final_positions]
        features.append({
            "type": "Feature",
            "properties": {"feature_type": "iceberg_drift_cone", "iceberg_id": iceberg_id,
                            "n_ensemble_members": len(member_tracks)},
            "geometry": {"type": "MultiPoint", "coordinates": [[lon, lat] for lat, lon in zip(lats, lons)]},
        })

    geojson = {"type": "FeatureCollection", "features": features}
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / out_name
    out_path.write_text(json.dumps(geojson, indent=2))
    print(f"Saved {out_path}")
    return out_path


def write_manifest(forecast_date: str, iceberg_cluster, seaice_image_paths=None,
                    out_name: str = "manifest.json") -> Path:
    """Metadata the dashboard needs but that doesn't belong in the
    GeoJSON: domain bounds, forecast horizon, sea-ice overlay image
    bounds/paths, and an explicit list of which inputs are still
    placeholders so the frontend can show an honest disclosure badge
    instead of silently implying everything is a real forecast."""
    manifest = {
        "forecast_date": forecast_date,
        "forecast_horizon_days": GRID.forecast_horizon_days,
        "bounds": {"lon_min": GRID.lon_min, "lon_max": GRID.lon_max,
                   "lat_min": GRID.lat_min, "lat_max": GRID.lat_max},
        "iceberg_ids": [e["id"] for e in iceberg_cluster],
        "seaice_images": seaice_image_paths or [],
        "placeholder_inputs": PLACEHOLDER_INPUTS,
        "generated_at": pd.Timestamp.now().isoformat(),
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / out_name
    out_path.write_text(json.dumps(manifest, indent=2))
    print(f"Saved {out_path}")
    return out_path


if __name__ == "__main__":
    run_pipeline()
