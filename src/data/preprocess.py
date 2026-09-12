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


def save_processed(ds: xr.Dataset, name: str) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / f"{name}.nc"
    ds.to_netcdf(out_path)
    print(f"Saved {out_path}")
    return out_path
