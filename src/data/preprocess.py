"""
Shared preprocessing: crop each raw source to the project's bounding box
and regrid it onto the shared grid (src/utils/grid.py) before anything
downstream (Layer 2a/2b models) touches it.

This is the module most worth pairing on early — if sea-ice, ERA5, and
iceberg data all land on the same grid/timestamps coming out of here,
Phase 5 integration is mostly bookkeeping. If they don't, Phase 5 becomes
the hackathon's biggest time sink.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

sys.path.append(str(Path(__file__).resolve().parents[2]))
from src.utils.grid import GRID, lat_lon_mesh  # noqa: E402

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"


def crop_to_domain(ds: xr.Dataset, lat_name="latitude", lon_name="longitude") -> xr.Dataset:
    """
    Crop a dataset to GRID's bounding box using a boolean mask on its
    (possibly 2-D) lat/lon coordinates.

    Works for the NSIDC CDR case where latitude/longitude are 2-D arrays
    on a polar-stereographic xgrid/ygrid — NOT a simple .sel(lat=slice(...))
    situation. If a given source's lat/lon happen to be 1-D/regular
    (e.g. ERA5), a plain .sel(...) is simpler and fine to use instead for
    that source specifically.
    """
    mask = (
        (ds[lat_name] >= GRID.lat_min) & (ds[lat_name] <= GRID.lat_max) &
        (ds[lon_name] >= GRID.lon_min) & (ds[lon_name] <= GRID.lon_max)
    )
    return ds.where(mask, drop=True)


def regrid_to_shared_grid(ds: xr.Dataset, method: str = "linear",
                           lat_name="latitude", lon_name="longitude") -> xr.Dataset:
    """
    Interpolate a cropped dataset onto the common analysis grid (plain
    lat/lon at GRID.resolution_deg — see grid.py's native_crs decision) so
    that sea-ice, ERA5, and iceberg-adjacent inputs all line up cell-for-
    cell before Layer 2 ever sees them.

    Two code paths, since sources differ in how lat/lon are stored:
      - 1-D regular lat/lon (e.g. ERA5) -> xarray's own .interp(), which
        is a fast, vectorized linear interpolation along each axis.
      - 2-D curvilinear lat/lon (e.g. NSIDC CDR's polar-stereographic
        xgrid/ygrid with separate 2-D lat/lon arrays) -> scipy.griddata
        scattered-point interpolation per timestep, since there's no
        regular axis to call .interp() along.

    Assumes at most one non-spatial dimension (time) for the curvilinear
    path — true for every source this project uses.
    """
    target_lats, target_lons = lat_lon_mesh()
    lat_coord, lon_coord = ds[lat_name], ds[lon_name]

    if lat_coord.ndim == 1 and lon_coord.ndim == 1:
        return ds.interp({lat_name: target_lats, lon_name: target_lons}, method=method)

    from scipy.interpolate import griddata

    spatial_dims = set(lat_coord.dims)
    points = np.column_stack([lat_coord.values.ravel(), lon_coord.values.ravel()])
    target_lat_grid, target_lon_grid = np.meshgrid(target_lats, target_lons, indexing="ij")

    out_vars = {}
    time_dim, time_values = None, None
    for name, da in ds.data_vars.items():
        extra_dims = [d for d in da.dims if d not in spatial_dims]
        if len(extra_dims) > 1:
            raise NotImplementedError(
                f"'{name}' has {len(extra_dims)} non-spatial dims {extra_dims} — "
                "this regridder only handles a single extra dim (time)."
            )
        if extra_dims:
            time_dim = extra_dims[0]
            time_values = ds[time_dim].values
            frames = [
                griddata(points, da.isel({time_dim: i}).values.ravel(),
                         (target_lat_grid, target_lon_grid), method=method)
                for i in range(da.sizes[time_dim])
            ]
            out_vars[name] = ((time_dim, "lat", "lon"), np.stack(frames, axis=0))
        else:
            regridded = griddata(points, da.values.ravel(), (target_lat_grid, target_lon_grid), method=method)
            out_vars[name] = (("lat", "lon"), regridded)

    coords = {"lat": target_lats, "lon": target_lons}
    if time_dim is not None:
        coords[time_dim] = time_values
    return xr.Dataset(out_vars, coords=coords)


def regrid_bathymetry(tif_path) -> np.ndarray:
    """
    Load the GeoTIFF from download_bathymetry.py and resample it onto the
    shared grid's lat/lon mesh, returning a plain (n_lat, n_lon) array of
    depth in meters (negative = below sea level) matching
    src.utils.grid.lat_lon_mesh()'s ordering — the shape build_cost_grid()
    in routing/isochrone.py expects.
    """
    import rasterio
    from rasterio.warp import reproject, Resampling

    target_lats, target_lons = lat_lon_mesh()
    n_lat, n_lon = len(target_lats), len(target_lons)

    with rasterio.open(tif_path) as src:
        # Destination transform: north-up, matching target_lats/target_lons
        # ordering (target_lats is ascending south->north; a north-up
        # raster's transform must start at the NORTH edge and step
        # southward, so use the max/min explicitly rather than assuming
        # which end of the array is "top").
        px_w = (target_lons[-1] - target_lons[0]) / (n_lon - 1)
        px_h = (target_lats[-1] - target_lats[0]) / (n_lat - 1)
        dst_transform = rasterio.transform.from_origin(
            target_lons[0] - px_w / 2, target_lats[-1] + px_h / 2, px_w, px_h
        )
        dest = np.full((n_lat, n_lon), np.nan, dtype=np.float32)
        reproject(
            source=rasterio.band(src, 1),
            destination=dest,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs="EPSG:4326",
            resampling=Resampling.bilinear,
        )
        # dest's row 0 is the NORTH edge (top-down raster convention) but
        # target_lats is south->north ascending -- flip rows to match.
        return dest[::-1, :]


def regrid_seaice_bremen(tif_path) -> np.ndarray:
    """
    Load a University of Bremen AMSR2 ASI GeoTIFF (see
    download_seaice_bremen.py) and resample it onto the shared grid,
    returning a plain (n_lat, n_lon) array of concentration in [0, 1] —
    same shape/convention as the rest of the pipeline expects from
    placeholder_seaice_concentration() (see integration/pipeline.py).

    Per the ASI product's documentation, raw pixel values are 0-100
    (percent); 120 flags land and other values above 100 flag
    missing/masked swaths. Those get set to NaN *before* reprojecting
    (not after) so bilinear resampling never blends a real concentration
    value with a land/nodata flag value into a nonsense number at coastal
    or swath-edge pixels.
    """
    import rasterio
    from rasterio.warp import reproject, Resampling

    target_lats, target_lons = lat_lon_mesh()
    n_lat, n_lon = len(target_lats), len(target_lons)

    with rasterio.open(tif_path) as src:
        raw = src.read(1).astype(np.float32)
        raw[raw > 100] = np.nan  # land (120) / missing-swath flags
        concentration_pct = raw

        px_w = (target_lons[-1] - target_lons[0]) / (n_lon - 1)
        px_h = (target_lats[-1] - target_lats[0]) / (n_lat - 1)
        dst_transform = rasterio.transform.from_origin(
            target_lons[0] - px_w / 2, target_lats[-1] + px_h / 2, px_w, px_h
        )
        dest = np.full((n_lat, n_lon), np.nan, dtype=np.float32)
        reproject(
            source=concentration_pct,
            destination=dest,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs="EPSG:4326",
            resampling=Resampling.bilinear,
            src_nodata=np.nan,
            dst_nodata=np.nan,
        )
        dest = dest[::-1, :] / 100.0  # flip to south->north row order, percent -> fraction

    # Open-water cells with no valid nearby swath pixel (rare, but
    # possible near the domain edge) fall back to 0 (ice-free) rather
    # than propagating NaN into build_cost_grid's arithmetic -- explicit
    # and disclosed, not silent.
    return np.nan_to_num(dest, nan=0.0)


def interpolate_weather_samples(wind_csv, current_csv):
    """
    Load the sparse real point samples from download_weather.py and
    interpolate them onto the shared grid for every forecast day,
    returning (wind_u, wind_v, current_u, current_v), each a
    (n_days, n_lat, n_lon) array.

    scipy.griddata scattered-point interpolation, same approach
    preprocess.py already uses for curvilinear-source regridding in
    regrid_to_shared_grid() -- these ~70 real sample points are sparser
    still, but Open-Meteo has no bulk gridded endpoint (point-query API
    only), so interpolating real sampled values is the honest option,
    not synthesizing a field from nothing.
    """
    from scipy.interpolate import griddata

    target_lats, target_lons = lat_lon_mesh()
    target_lat_grid, target_lon_grid = np.meshgrid(target_lats, target_lons, indexing="ij")

    wind_df = pd.read_csv(wind_csv)
    current_df = pd.read_csv(current_csv)
    n_days = int(max(wind_df["day"].max(), current_df["day"].max())) + 1
    n_lat, n_lon = len(target_lats), len(target_lons)

    def _interp_all_days(df, value_col):
        out = np.zeros((n_days, n_lat, n_lon), dtype=np.float32)
        for day in range(n_days):
            day_df = df[df["day"] == day]
            points = day_df[["lat", "lon"]].values
            values = day_df[value_col].values
            out[day] = griddata(points, values, (target_lat_grid, target_lon_grid), method="linear")
            # points near the box edge can fall outside the sample points' convex hull ->
            # NaN from linear interp; fill those from the nearest real sample instead of 0.
            nan_mask = np.isnan(out[day])
            if nan_mask.any():
                out[day][nan_mask] = griddata(
                    points, values, (target_lat_grid[nan_mask], target_lon_grid[nan_mask]), method="nearest"
                )
        return out

    return (
        _interp_all_days(wind_df, "wind_u"), _interp_all_days(wind_df, "wind_v"),
        _interp_all_days(current_df, "current_u"), _interp_all_days(current_df, "current_v"),
    )


def interpolate_weather_samples_historical(wind_csv, current_csv, dates):
    """
    Same real-point-sample interpolation as interpolate_weather_samples(),
    but keyed by actual calendar date (download_weather.py's
    download_*_historical() output) instead of a relative forecast-day
    index -- needed to align real historical wind/current onto the exact
    same date axis as seaice_history.nc for ConvLSTM training with
    weather as an input channel.

    dates : iterable of date-like values (e.g. seaice_history.nc's `time`
        coordinate) to interpolate for, in order -- output arrays are
        indexed to match this sequence exactly.
    """
    from scipy.interpolate import griddata

    target_lats, target_lons = lat_lon_mesh()
    target_lat_grid, target_lon_grid = np.meshgrid(target_lats, target_lons, indexing="ij")
    n_lat, n_lon = len(target_lats), len(target_lons)

    wind_df = pd.read_csv(wind_csv, parse_dates=["date"])
    current_df = pd.read_csv(current_csv, parse_dates=["date"])
    dates = pd.to_datetime(pd.Index(dates)).normalize()

    def _interp_all_dates(df, value_col):
        out = np.zeros((len(dates), n_lat, n_lon), dtype=np.float32)
        for i, date in enumerate(dates):
            day_df = df[df["date"].dt.normalize() == date]
            if day_df.empty:
                out[i] = out[i - 1] if i > 0 else 0.0  # real data gap -- hold last real day, disclosed via caller
                continue
            points = day_df[["lat", "lon"]].values
            values = day_df[value_col].values
            out[i] = griddata(points, values, (target_lat_grid, target_lon_grid), method="linear")
            nan_mask = np.isnan(out[i])
            if nan_mask.any():
                out[i][nan_mask] = griddata(
                    points, values, (target_lat_grid[nan_mask], target_lon_grid[nan_mask]), method="nearest"
                )
        return out

    return (
        _interp_all_dates(wind_df, "wind_u"), _interp_all_dates(wind_df, "wind_v"),
        _interp_all_dates(current_df, "current_u"), _interp_all_dates(current_df, "current_v"),
    )


def save_processed(ds: xr.Dataset, name: str) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / f"{name}.nc"
    ds.to_netcdf(out_path)
    print(f"Saved {out_path}")
    return out_path
