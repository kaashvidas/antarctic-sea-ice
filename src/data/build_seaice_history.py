"""
Turns the bulk real AMSR2 history from download_seaice_bremen.py's
download_range() into one processed NetCDF time series, in the exact
shape src/models/seaice_forecast/train.py's SeaIceSequenceDataset
expects: a 'cdr_seaice_conc' variable, dims (time, lat, lon), on the
shared analysis grid, real datetime64 time coordinates, no gaps.

Real satellite data has real gaps (a day the sensor/processing pipeline
didn't publish) -- train.py explicitly refuses NaNs (see its own
docstring: "don't silently zero-fill sea-ice concentration"), so this
script closes small gaps with short linear time-interpolation (a day or
two missing, bridged from its real neighbors) and reports/drops any
longer gaps rather than inventing values across them.
"""

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

sys.path.append(str(Path(__file__).resolve().parents[2]))
from src.data.preprocess import regrid_seaice_bremen  # noqa: E402
from src.utils.grid import lat_lon_mesh  # noqa: E402
from src.utils.paths import PROCESSED_ROOT, shared_raw_dir  # noqa: E402

RAW_DIR = shared_raw_dir("seaice_bremen")
PROCESSED_DIR = PROCESSED_ROOT
MAX_GAP_DAYS_TO_INTERPOLATE = 2


def build(out_name: str = "seaice_history.nc") -> Path:
    files = sorted(RAW_DIR.glob("seaice_*.tif"))
    if not files:
        raise FileNotFoundError(
            f"No files in {RAW_DIR} — run "
            "`python src/data/download_seaice_bremen.py --start ... --end ...` first."
        )

    dates, frames = [], []
    for i, f in enumerate(files):
        m = re.match(r"seaice_(\d{8})\.tif", f.name)
        if not m:
            continue
        date = pd.Timestamp(m.group(1))
        try:
            frames.append(regrid_seaice_bremen(f))
            dates.append(date)
        except Exception as e:  # noqa: BLE001 -- a single corrupt/truncated file shouldn't kill the whole build
            print(f"WARNING: skipping {f.name}, failed to regrid ({e})")
        if (i + 1) % 100 == 0:
            print(f"Regridded {i + 1}/{len(files)}")

    order = np.argsort(dates)
    dates = [dates[i] for i in order]
    stack = np.stack([frames[i] for i in order], axis=0)

    lats, lons = lat_lon_mesh()
    ds = xr.Dataset(
        {"cdr_seaice_conc": (("time", "lat", "lon"), stack.astype(np.float32))},
        coords={"time": dates, "lat": lats, "lon": lons},
    )

    # Reindex onto a complete daily calendar so gaps are explicit NaNs we
    # can reason about, not silently absent timestamps.
    full_range = pd.date_range(dates[0], dates[-1], freq="D")
    ds = ds.reindex(time=full_range)
    n_missing_before = int(ds["cdr_seaice_conc"].isnull().any(dim=["lat", "lon"]).sum())

    ds["cdr_seaice_conc"] = ds["cdr_seaice_conc"].interpolate_na(
        dim="time", method="linear", max_gap=pd.Timedelta(days=MAX_GAP_DAYS_TO_INTERPOLATE)
    )
    still_missing = ds["time"].values[ds["cdr_seaice_conc"].isnull().any(dim=["lat", "lon"]).values]
    if len(still_missing):
        print(f"Dropping {len(still_missing)} day(s) with gaps > {MAX_GAP_DAYS_TO_INTERPOLATE} days "
              f"(real satellite/processing gaps too long to safely interpolate): "
              f"{pd.DatetimeIndex(still_missing).strftime('%Y-%m-%d').tolist()[:10]}"
              f"{'...' if len(still_missing) > 10 else ''}")
        ds = ds.dropna(dim="time", how="any")

    print(f"Final history: {ds.sizes['time']} days, {dates[0].date()} to {dates[-1].date()} "
          f"({n_missing_before} originally-missing days, {n_missing_before - len(still_missing)} "
          f"filled by short-gap interpolation)")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / out_name
    ds.to_netcdf(out_path)
    print(f"Saved {out_path}")
    return out_path


if __name__ == "__main__":
    build()
