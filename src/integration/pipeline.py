"""
Phase 5 — integration/orchestration.

One script chaining Layer 2 -> Layer 3: sea-ice forecast -> iceberg drift
(coupled to that forecast) -> route optimization -> GeoJSON/PNG output for
the dashboard.

Data honesty note (updated 2026-09-13): NSIDC (Earthdata) and CDS (ERA5)
are still blocked on missing credentials on this build machine. Real,
NO-LOGIN alternatives are now wired in instead:
  - Sea-ice concentration: University of Bremen AMSR2 (real satellite
    observation, ~1-2 day lag), persisted across the forecast horizon —
    a real PERSISTENCE forecast (same method as baseline.py's
    persistence_forecast, applied to real current-day data), not a
    trained multi-day forecast. See get_seaice_concentration().
  - Wind + ocean current: Open-Meteo (GFS wind model + marine/wave
    model), a genuine multi-day forecast, sampled at ~70 real points
    across the domain and interpolated onto the shared grid. See
    get_forcing_fields().
The original synthetic placeholders (placeholder_seaice_concentration,
placeholder_forcing_fields) are kept as a last-resort fallback if the
real-data files haven't been downloaded yet — every function that can
fall back to them says so loudly (printed warning + a `source`/
`is_real_data` field in its return value), never silently.

Still not wired in: a TRAINED ConvLSTM forecast (src/models/seaice_forecast/)
— that needs real multi-year NSIDC history to train on, which is still
credential-blocked. get_seaice_concentration() has the swap point ready
(checks for a checkpoint file first) but there is no checkpoint yet, so
it falls through to the real-persistence path above.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[2]))
from src.utils.grid import (  # noqa: E402
    GRID, DEMO_ICEBERG_IDS, lat_lon_mesh, latlon_to_index, index_to_latlon, n_grid_cells, region_path,
)
from src.data.preprocess import regrid_bathymetry, regrid_seaice_bremen, interpolate_weather_samples  # noqa: E402
from src.models.iceberg_drift.wagner_model import IcebergState, step  # noqa: E402
from src.models.routing.isochrone import build_cost_grid, astar_route, naive_route  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
# Circumpolar/shared sources -- same for every region, not region-scoped.
ICEBERG_CSV = DATA_DIR / "raw" / "icebergs" / "antarctic_icebergs_latest.csv"
SEAICE_BREMEN_DIR = DATA_DIR / "raw" / "seaice_bremen"
# Region-scoped: cropped/regridded to the active region's GRID, or a
# per-region demo-output/checkpoint, so two regions' files must not
# collide. See src/utils/grid.py's region_path().
OUTPUT_DIR = region_path("outputs")
BATHY_TIF = region_path("data/raw", "bathymetry", "bathymetry.tif")
WEATHER_DIR = region_path("data/raw", "weather")
CONVLSTM_CHECKPOINT = region_path("data/processed", "convlstm_checkpoint.pt")

NM_TO_M = 1852.0
N_ENSEMBLE = 8               # perturbed drift members per iceberg, for the uncertainty cone
DT_SECONDS = 24 * 3600

# Kept for any external caller still importing this name; prefer the
# `is_real_data` flag in get_seaice_concentration()/get_forcing_fields()'s
# returned info dict, which is accurate per-run rather than a fixed list.
PLACEHOLDER_INPUTS = ["sea_ice_concentration", "wind_field", "current_field"]

# Real WDE17 drift physics (wagner_model.py) needs IcebergState.thickness_m
# as a field, but never actually reads it unless real SST is passed into
# step() (for melt_rates()) -- which nothing in this live pipeline does.
# No public dataset gives real per-iceberg thickness for this build's
# tracked cluster (an exhaustive real ICESat-2 ATL10 search came up empty
# -- see src/data/lookup_iceberg_thickness_icesat2.py's docstring), and a
# literature-based estimate isn't real data either, so this is a fixed
# internal placeholder -- never surfaced via the API or UI, not treated
# as a measurement anywhere.
_UNUSED_THICKNESS_M = 0.0


def load_iceberg_cluster(iceberg_ids=None, csv_path: Path = ICEBERG_CSV) -> list:
    """Real USNIC positions/sizes for this build's demo cluster (see
    grid.py's DEMO_ICEBERG_IDS docstring for provenance)."""
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
        length_m = float(row["Length (NM)"]) * NM_TO_M
        states.append({
            "id": row["Iceberg"],
            "state": IcebergState(
                lat=float(row["Latitude"]), lon=float(row["Longitude"]),
                length_m=length_m,
                width_m=float(row["Width (NM)"]) * NM_TO_M,
                thickness_m=_UNUSED_THICKNESS_M,
            ),
        })
    return states


def placeholder_seaice_concentration() -> np.ndarray:
    """
    Synthetic fallback, used ONLY if no real AMSR2 file has been
    downloaded yet (see get_seaice_concentration()). Directionally
    plausible for Weddell Sea winter (higher near the shelf, lower
    toward open water) but not observed data -- NOT a forecast.
    """
    lats, lons = lat_lon_mesh()
    lat_grid, _ = np.meshgrid(lats, lons, indexing="ij")
    frac_south_to_north = (lat_grid - GRID.lat_min) / (GRID.lat_max - GRID.lat_min)
    conc = np.clip(0.95 - 0.85 * frac_south_to_north, 0.0, 1.0)
    return conc.astype(np.float32)


def placeholder_forcing_fields():
    """Synthetic fallback constant, used ONLY if no real Open-Meteo pull
    exists yet (see get_forcing_fields())."""
    wind_u, wind_v = 6.0, -2.0
    current_u, current_v = -0.03, 0.05
    return wind_u, wind_v, current_u, current_v


def _run_convlstm_forecast(horizon_days: int):
    """
    Real autoregressive ConvLSTM inference: load the trained checkpoint,
    feed it the most recent `input_seq_len` real days of history, and
    roll it forward day by day -- each day's PREDICTED concentration
    becomes the newest concentration frame for the next step, per
    convlstm.py's own docstring. Returns a (horizon_days+1, n_lat, n_lon)
    array (day 0 = the last real observation, days 1..horizon_days =
    genuine model predictions), or raises if the checkpoint/history
    aren't usable, so the caller can fall back cleanly.

    If the checkpoint was trained with extra channels (checkpoint's
    `extra_vars`, e.g. wind_u/wind_v/current_u/current_v -- see
    src/data/merge_weather_into_history.py and train.py's --extra-vars),
    those channels are reconstructed from REAL data at every step, not
    guessed: real historical values for the input tail, real Open-Meteo
    FORECAST values (get_forcing_fields(), the same real forecast the
    rest of the app already uses) for the future days as the
    autoregressive window slides into them. Only the concentration
    channel is ever the model's own prediction feeding back in.
    """
    import torch
    from src.models.seaice_forecast.convlstm import SeaIceConvLSTM

    checkpoint = torch.load(CONVLSTM_CHECKPOINT, map_location="cpu")
    extra_vars = checkpoint.get("extra_vars", [])
    input_seq_len = checkpoint.get("input_seq_len", 7)
    # Architecture hyperparams: default to the original fixed values for
    # checkpoints saved before these were swept/exposed, so old checkpoints
    # keep loading correctly.
    hidden_dim = checkpoint.get("hidden_dim", 32)
    num_layers = checkpoint.get("num_layers", 2)
    kernel_size = checkpoint.get("kernel_size", 3)

    history_name = "seaice_history_with_weather.nc" if extra_vars else "seaice_history.nc"
    history_path = region_path("data/processed", history_name)
    if not history_path.exists():
        raise FileNotFoundError(
            f"{history_path} not found — run src/data/build_seaice_history.py "
            "(and src/data/merge_weather_into_history.py if this checkpoint uses extra_vars) first."
        )

    import xarray as xr
    ds = xr.open_dataset(history_path)
    if ds.sizes["time"] < input_seq_len:
        raise ValueError(f"History has only {ds.sizes['time']} days, need >= {input_seq_len}.")

    def _build_model():
        m = SeaIceConvLSTM(
            input_dim=1 + len(extra_vars), hidden_dim=hidden_dim,
            kernel_size=kernel_size, num_layers=num_layers,
        )
        m.eval()
        return m

    # Ensemble checkpoints (src/models/seaice_forecast/train_ensemble.py) carry
    # several real independently-trained state_dicts (different seeds, same
    # architecture) instead of one -- averaging their predictions at each
    # autoregressive step is a real, cheap accuracy improvement over any
    # single member, not a synthetic uncertainty display.
    ensemble_state_dicts = checkpoint.get("ensemble_state_dicts")
    if ensemble_state_dicts:
        models = []
        for sd in ensemble_state_dicts:
            m = _build_model()
            m.load_state_dict(sd)
            models.append(m)
    else:
        model = _build_model()
        model.load_state_dict(checkpoint["model_state_dict"] if "model_state_dict" in checkpoint else checkpoint)
        models = [model]

    conc_window = ds["cdr_seaice_conc"].isel(time=slice(-input_seq_len, None)).values.astype(np.float32)
    last_obs_date = str(ds["time"].values[-1])[:10]

    extra_seq = {}
    if extra_vars:
        hist_tail = {v: ds[v].isel(time=slice(-input_seq_len, None)).values.astype(np.float32) for v in extra_vars}
        wind_u_f, wind_v_f, current_u_f, current_v_f, _ = get_forcing_fields(horizon_days)
        future_map = {"wind_u": wind_u_f, "wind_v": wind_v_f, "current_u": current_u_f, "current_v": current_v_f}
        for v in extra_vars:
            # [real historical tail] + [real forecast days 1..horizon] -- day 0 of the
            # forecast is dropped since it duplicates "today", already the tail's last frame.
            extra_seq[v] = np.concatenate([hist_tail[v], future_map[v][1:horizon_days + 1]], axis=0)

    frames = [conc_window[-1]]  # day 0 = last real observation
    channel_window = conc_window  # (input_seq_len, H, W), concentration only -- this is what autoregresses

    with torch.no_grad():
        for step in range(horizon_days):
            if extra_vars:
                x_np = np.stack([channel_window] + [extra_seq[v][step:step + input_seq_len] for v in extra_vars],
                                 axis=1)  # (seq, channels, H, W)
            else:
                x_np = channel_window[:, np.newaxis]  # (seq, 1, H, W)
            x_seq = torch.from_numpy(x_np).unsqueeze(0)  # (1, seq, C, H, W)
            member_preds = [m(x_seq).squeeze(0).squeeze(0).numpy() for m in models]
            pred = np.mean(member_preds, axis=0)  # (H, W) -- real ensemble average when len(models) > 1
            frames.append(pred)
            channel_window = np.concatenate([channel_window[1:], pred[np.newaxis]], axis=0)

    return np.stack(frames, axis=0), last_obs_date


def get_seaice_concentration(horizon_days: int = None):
    """
    Real-data-first swap chain for sea-ice concentration. Returns
    (grid_stack, info) where grid_stack is ALWAYS (n_days, n_lat, n_lon)
    in [0, 1] -- one field per forecast day, matching get_forcing_fields()'s
    shape -- and info documents exactly what was used and why:
      1. Trained ConvLSTM checkpoint + real processed history: genuine
         autoregressive multi-day forecast (`is_true_forecast: True`).
      2. Real AMSR2 satellite observation (download_seaice_bremen.py),
         broadcast across every forecast day. Real data, but a
         PERSISTENCE forecast, not a trained one
         (`is_true_forecast: False`).
      3. Last resort: the synthetic placeholder gradient, broadcast the
         same way.
    """
    horizon_days = horizon_days if horizon_days is not None else GRID.forecast_horizon_days

    if CONVLSTM_CHECKPOINT.exists():
        try:
            import torch
            ckpt_meta = torch.load(CONVLSTM_CHECKPOINT, map_location="cpu")
            extra_vars = ckpt_meta.get("extra_vars", [])
            input_seq_len = ckpt_meta.get("input_seq_len", 7)
            held_out_skill = ckpt_meta.get("held_out_skill")

            # Real per-lead-day skill (evaluate_multiday.py) -- distinct
            # from held_out_skill above, which is 1-day-ahead only. Error
            # genuinely compounds across the autoregressive rollout, so a
            # single number would overstate day-7 confidence; this lets
            # every forecast day disclose its own real, measured accuracy.
            multiday_skill_path = region_path("data/processed", "convlstm_multiday_skill.json")
            mae_by_lead_day = None
            if multiday_skill_path.exists():
                import json
                mae_by_lead_day = json.loads(multiday_skill_path.read_text()).get("mae_by_lead_day")

            stack, last_obs_date = _run_convlstm_forecast(horizon_days)
            return stack, {
                "variable": "sea_ice_concentration",
                "source": "Trained ConvLSTM (src/models/seaice_forecast/convlstm.py), "
                          "real multi-day autoregressive forecast",
                "observation_date": last_obs_date,
                "input_channels": ["sea_ice_concentration (AMSR2)"] + [
                    f"{v} (Open-Meteo, real historical+forecast)" for v in extra_vars
                ],
                "method": f"autoregressive rollout from the last {input_seq_len} real observed days",
                "held_out_skill": held_out_skill,
                "mae_by_lead_day": mae_by_lead_day,
                "is_real_data": True,
                "is_true_forecast": True,
            }
        except Exception as e:  # noqa: BLE001 -- any inference failure should fall back, not crash the app
            print(f"WARNING: ConvLSTM checkpoint found but inference failed ({e}) — "
                  "falling back to the real-observation persistence path.")

    bremen_files = sorted(SEAICE_BREMEN_DIR.glob("seaice_*.tif")) if SEAICE_BREMEN_DIR.exists() else []
    if bremen_files:
        latest = bremen_files[-1]
        obs_date = latest.stem.replace("seaice_", "")
        obs_date = f"{obs_date[:4]}-{obs_date[4:6]}-{obs_date[6:]}"
        conc = regrid_seaice_bremen(latest)
        stack = np.repeat(conc[np.newaxis, :, :], horizon_days + 1, axis=0)
        return stack, {
            "variable": "sea_ice_concentration",
            "source": "AMSR2 ASI (University of Bremen), real satellite observation",
            "observation_date": obs_date,
            "method": "persistence — today's real observed concentration held constant "
                      "across the forecast horizon; no trained forecast model wired in yet",
            "is_real_data": True,
            "is_true_forecast": False,
        }

    print("WARNING: no real sea-ice file found under data/raw/seaice_bremen/ — "
          "run `python src/data/download_seaice_bremen.py` first. Falling back to "
          "a synthetic placeholder gradient for this run.")
    conc = placeholder_seaice_concentration()
    stack = np.repeat(conc[np.newaxis, :, :], horizon_days + 1, axis=0)
    return stack, {
        "variable": "sea_ice_concentration",
        "source": "synthetic placeholder (no real data downloaded yet)",
        "is_real_data": False,
        "is_true_forecast": False,
    }


def get_forcing_fields(horizon_days: int = None):
    """
    Real-data-first swap chain for wind + ocean current. Returns
    (wind_u, wind_v, current_u, current_v, info) where each array is
    (n_days, n_lat, n_lon) in m/s, and info documents provenance.
    """
    horizon_days = horizon_days if horizon_days is not None else GRID.forecast_horizon_days
    wind_csv = WEATHER_DIR / "wind_openmeteo.csv"
    current_csv = WEATHER_DIR / "current_openmeteo.csv"

    if wind_csv.exists() and current_csv.exists():
        wind_u, wind_v, current_u, current_v = interpolate_weather_samples(wind_csv, current_csv)
        return wind_u, wind_v, current_u, current_v, {
            "variable": "wind_and_current",
            "source": "Open-Meteo (GFS wind model + marine/wave current model), real multi-day forecast",
            "method": "~70 real point samples across the domain, interpolated onto the shared grid",
            "is_real_data": True,
            "is_true_forecast": True,
        }

    print("WARNING: no real weather files found under data/raw/weather/ — "
          "run `python src/data/download_weather.py` first. Falling back to a "
          "constant synthetic placeholder for this run.")
    wind_u_c, wind_v_c, current_u_c, current_v_c = placeholder_forcing_fields()
    n_lon, n_lat = n_grid_cells()
    ones = np.ones((horizon_days + 1, n_lat, n_lon), dtype=np.float32)
    return (wind_u_c * ones, wind_v_c * ones, current_u_c * ones, current_v_c * ones, {
        "variable": "wind_and_current",
        "source": "synthetic placeholder (no real data downloaded yet)",
        "is_real_data": False,
        "is_true_forecast": False,
    })


def run_drift_ensemble(iceberg_cluster, horizon_days: int = None,
                        n_ensemble: int = N_ENSEMBLE, seed: int = 0):
    """
    For each tracked iceberg, run the real WDE17 physics (deterministic
    center member + n_ensemble perturbed members) forward `horizon_days`,
    sampling real (or, if unavailable, disclosed-placeholder) sea-ice
    concentration and wind/current at the iceberg's current grid cell for
    the current forecast day at every step — not a single global
    constant. This is what produces the drift PROBABILITY CONE, not a
    single deterministic line, per the README's uncertainty-first rule.

    Returns (tracks, source_info) where tracks is
    {iceberg_id: [ [ (lat,lon) per day, for member 0 ], ... ]}
    and source_info documents what data actually went into this run.
    """
    horizon_days = horizon_days if horizon_days is not None else GRID.forecast_horizon_days
    rng = np.random.default_rng(seed)
    seaice_conc, seaice_info = get_seaice_concentration(horizon_days)
    wind_u_grid, wind_v_grid, current_u_grid, current_v_grid, forcing_info = get_forcing_fields(horizon_days)
    n_forcing_days = wind_u_grid.shape[0]
    n_seaice_days = seaice_conc.shape[0]

    tracks = {}
    for entry in iceberg_cluster:
        iceberg_id, base_state = entry["id"], entry["state"]
        member_tracks = []
        for m in range(n_ensemble + 1):
            wind_scale = 1.0 if m == 0 else (1 + rng.normal(0, 0.2))
            current_scale = 1.0 if m == 0 else (1 + rng.normal(0, 0.3))

            state = IcebergState(**vars(base_state))
            track = [(state.lat, state.lon)]
            for day in range(horizon_days):
                row, col = latlon_to_index(state.lat, state.lon)
                day_idx = min(day, n_forcing_days - 1)
                seaice_day_idx = min(day, n_seaice_days - 1)
                local_conc = float(seaice_conc[seaice_day_idx, row, col])
                wind_u = float(wind_u_grid[day_idx, row, col]) * wind_scale
                wind_v = float(wind_v_grid[day_idx, row, col]) * wind_scale
                current_u = float(current_u_grid[day_idx, row, col]) * current_scale
                current_v = float(current_v_grid[day_idx, row, col]) * current_scale
                state = step(
                    state, DT_SECONDS,
                    wind_uv=(wind_u, wind_v), current_uv=(current_u, current_v),
                    seaice_uv=(current_u, current_v),  # no separate ice-motion product yet -> approximate with current
                    seaice_concentration=local_conc,
                )
                track.append((state.lat, state.lon))
            member_tracks.append(track)
        tracks[iceberg_id] = member_tracks
    return tracks, {"seaice": seaice_info, "forcing": forcing_info}


def rasterize_iceberg_risk(tracks: dict) -> np.ndarray:
    """
    Turn the drift ensembles into a single (n_lat, n_lon) risk grid,
    0-1: for every ensemble member's position on every forecast day,
    deposit a Gaussian blob (sigma ~ a couple grid cells) and take the
    per-cell max across all icebergs/members/days, then normalize. Max
    (not sum) so a route is penalized for entering ANY iceberg's swept
    area, not artificially double-penalized where cones overlap.

    This is the ALL-TIME aggregate (a cell is risky if any iceberg passes
    through it on ANY day) -- used by the static single-cost-grid A*
    fallback. isochrone_route() below needs per-day risk instead (a route
    that would arrive at a cell on day 6 shouldn't be penalized for where
    an iceberg was on day 1) -- see rasterize_iceberg_risk_per_day().
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


def rasterize_iceberg_risk_per_day(tracks: dict, horizon_days: int = None) -> np.ndarray:
    """
    Same Gaussian-blob approach as rasterize_iceberg_risk(), but keeping
    each forecast day separate: returns (n_days, n_lat, n_lon), where day
    d's risk grid only reflects where the drift ensemble predicts icebergs
    to actually BE on day d -- not a blanket "was near this cell at some
    point in the whole horizon" risk. This is what lets isochrone_route()
    reason about the real iceberg drift trajectory over time, not just a
    static exclusion zone.
    """
    horizon_days = horizon_days if horizon_days is not None else GRID.forecast_horizon_days
    n_lon, n_lat = n_grid_cells()
    lats, lons = lat_lon_mesh()
    lat_grid, lon_grid = np.meshgrid(lats, lons, indexing="ij")
    sigma_deg = 2 * GRID.resolution_deg

    risk = np.zeros((horizon_days + 1, n_lat, n_lon), dtype=np.float32)
    for member_tracks in tracks.values():
        for track in member_tracks:
            for day, (lat, lon) in enumerate(track):
                if day > horizon_days:
                    break
                d2 = (lat_grid - lat) ** 2 + (lon_grid - lon) ** 2
                blob = np.exp(-d2 / (2 * sigma_deg ** 2))
                risk[day] = np.maximum(risk[day], blob)
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
    Chain: real iceberg cluster -> real drift physics ensemble (real
    sea-ice/wind/current where downloaded, disclosed fallback otherwise)
    -> risk raster -> real bathymetry -> cost grid -> A*/naive routes ->
    GeoJSON. See module docstring for exactly what's real vs. fallback.
    """
    print(f"Domain grid: {GRID}")
    forecast_date = forecast_date or pd.Timestamp.today().strftime("%Y-%m-%d")

    iceberg_cluster = load_iceberg_cluster()
    print(f"Loaded {len(iceberg_cluster)} real tracked icebergs: {[e['id'] for e in iceberg_cluster]}")

    tracks, source_info = run_drift_ensemble(iceberg_cluster)
    print(f"Sea-ice source: {source_info['seaice']['source']}")
    print(f"Forcing source: {source_info['forcing']['source']}")
    iceberg_risk = rasterize_iceberg_risk(tracks)

    if not BATHY_TIF.exists():
        raise FileNotFoundError(f"{BATHY_TIF} not found — run src/data/download_bathymetry.py first.")
    bathymetry = regrid_bathymetry(BATHY_TIF)

    seaice_forecast, _ = get_seaice_concentration()  # (n_days, n_lat, n_lon)
    # A* plans one static route over one cost grid -- day-0 concentration
    # is the representative field for that, same simplification as before
    # this was a per-day stack. Day-by-day variation still reaches the
    # sea-ice overlay images and the drift ensemble below.
    cost_grid = build_cost_grid(seaice_forecast[0], iceberg_risk, bathymetry)

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
    manifest_path = write_manifest(forecast_date, iceberg_cluster, seaice_paths, source_info)
    print(f"Pipeline complete. Optimized route: {len(optimized_path)} pts, "
          f"naive route: {len(naive_path)} pts. Outputs: {geojson_path}, {manifest_path}")
    return geojson_path


def write_seaice_images(seaice_forecast: np.ndarray, out_subdir: str = "seaice") -> list:
    """
    Render one georeferenced PNG per forecast day for the dashboard's
    Leaflet ImageOverlay layer (lighter than emitting ~5600 GeoJSON
    polygons per day). `seaice_forecast` is (n_days, n_lat, n_lon) from
    get_seaice_concentration() -- with the ConvLSTM checkpoint wired in,
    each day is now a genuinely different predicted field; on the
    persistence/placeholder fallback paths, every day is still the same
    broadcast snapshot (disclosed in the manifest either way).
    """
    import matplotlib.cm as cm

    out_dir = OUTPUT_DIR / out_subdir
    out_dir.mkdir(parents=True, exist_ok=True)

    from PIL import Image
    paths = []
    for day in range(seaice_forecast.shape[0]):
        rgba = (cm.Blues(seaice_forecast[day]) * 255).astype(np.uint8)
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
                    source_info=None, out_name: str = "manifest.json") -> Path:
    """Metadata the dashboard needs but that doesn't belong in the
    GeoJSON: domain bounds, forecast horizon, sea-ice overlay image
    bounds/paths, and exactly which data sources fed this run (real vs.
    fallback, and — for real data — persistence vs. true forecast) so
    the frontend can show an accurate disclosure instead of a blanket
    guess."""
    source_info = source_info or {}
    from src.utils.grid import ACTIVE_REGION
    manifest = {
        "region": ACTIVE_REGION,
        "forecast_date": forecast_date,
        "forecast_horizon_days": GRID.forecast_horizon_days,
        "bounds": {"lon_min": GRID.lon_min, "lon_max": GRID.lon_max,
                   "lat_min": GRID.lat_min, "lat_max": GRID.lat_max},
        "iceberg_ids": [e["id"] for e in iceberg_cluster],
        "seaice_images": seaice_image_paths or [],
        "data_sources": source_info,
        "placeholder_inputs": [
            v for v in ["sea_ice_concentration", "wind_field", "current_field"]
            if not (source_info.get("seaice", {}).get("is_real_data") if "sea_ice" in v
                    else source_info.get("forcing", {}).get("is_real_data"))
        ],
        "generated_at": pd.Timestamp.now().isoformat(),
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / out_name
    out_path.write_text(json.dumps(manifest, indent=2))
    print(f"Saved {out_path}")
    return out_path


if __name__ == "__main__":
    run_pipeline()
