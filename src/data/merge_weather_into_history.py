"""
Adds real historical wind/current channels to seaice_history.nc (built by
build_seaice_history.py), producing a multi-channel training dataset for
SeaIceConvLSTM -- so the trained forecaster is genuinely based on real
satellite (AMSR2 concentration) AND real localized weather (Open-Meteo
wind + ocean current), not concentration history alone.

Keeps the original seaice_history.nc (concentration-only) untouched and
writes a separate seaice_history_with_weather.nc, so the two can be
trained and honestly compared (does weather actually help skill, or not)
rather than silently replacing a working baseline.

Real data-quality finding (checked directly, not assumed): Open-Meteo's
ocean-current ARCHIVE has a shorter real history than the wind archive --
for this domain, current data genuinely starts 2022-01-01, not whatever
earlier date was requested. This shows up as one long, clean, exactly-
at-the-start run of NaN (112 consecutive days in the 2021-09-11 start
case), not scattered gaps -- confirmed by inspecting the raw CSV, not
guessed. That's a real coverage limit, not a bug, and not something to
paper over with 3+ months of interpolated/fabricated current data.
Two SHORT (1 and 4-day) real gaps later in the record ARE safe to
bridge via short interpolation, same convention as
build_seaice_history.py's AMSR2 gap-filling.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

sys.path.append(str(Path(__file__).resolve().parents[2]))
from src.data.preprocess import interpolate_weather_samples_historical  # noqa: E402
from src.utils.grid import region_path  # noqa: E402

PROCESSED_DIR = region_path("data/processed")
WEATHER_DIR = region_path("data/raw", "weather")
MAX_GAP_DAYS_TO_INTERPOLATE = 5


def build(seaice_history_path=None, out_name: str = "seaice_history_with_weather.nc") -> Path:
    seaice_history_path = seaice_history_path or (PROCESSED_DIR / "seaice_history.nc")
    ds = xr.open_dataset(seaice_history_path)

    wind_csv = WEATHER_DIR / "wind_historical_openmeteo.csv"
    current_csv = WEATHER_DIR / "current_historical_openmeteo.csv"
    if not wind_csv.exists() or not current_csv.exists():
        raise FileNotFoundError(
            f"{wind_csv} / {current_csv} not found — run "
            "`python src/data/download_weather.py --start ... --end ...` first, matching "
            "seaice_history.nc's date range."
        )

    wind_u, wind_v, current_u, current_v = interpolate_weather_samples_historical(
        wind_csv, current_csv, ds.time.values,
    )

    ds["wind_u"] = (("time", "lat", "lon"), wind_u)
    ds["wind_v"] = (("time", "lat", "lon"), wind_v)
    ds["current_u"] = (("time", "lat", "lon"), current_u)
    ds["current_v"] = (("time", "lat", "lon"), current_v)

    # Bridge short real gaps (per this module's docstring, up to
    # MAX_GAP_DAYS_TO_INTERPOLATE), then DROP any day still incomplete --
    # a real long gap (Open-Meteo's actual current-archive coverage
    # limit) gets excluded from the training window entirely rather than
    # interpolated over, since fabricating months of current data would
    # violate this project's own honesty rule.
    for var in ("wind_u", "wind_v", "current_u", "current_v"):
        ds[var] = ds[var].interpolate_na(dim="time", method="linear",
                                          max_gap=pd.Timedelta(days=MAX_GAP_DAYS_TO_INTERPOLATE))

    n_before = ds.sizes["time"]
    still_missing = ds["time"].values[
        np.isnan(ds[["wind_u", "wind_v", "current_u", "current_v"]].to_array()).any(dim=["variable", "lat", "lon"]).values
    ]
    if len(still_missing):
        print(f"Dropping {len(still_missing)} day(s) with real wind/current gaps too long to "
              f"honestly interpolate (> {MAX_GAP_DAYS_TO_INTERPOLATE} days): "
              f"{pd.Timestamp(still_missing[0]).date()} to {pd.Timestamp(still_missing[-1]).date()}")
        ds = ds.dropna(dim="time", how="any")
    print(f"Final multi-channel history: {ds.sizes['time']} days (dropped {n_before - ds.sizes['time']} "
          f"of {n_before}), {pd.Timestamp(ds.time.values[0]).date()} to {pd.Timestamp(ds.time.values[-1]).date()}")

    out_path = PROCESSED_DIR / out_name
    ds.to_netcdf(out_path)
    print(f"Saved {out_path} with variables: {list(ds.data_vars)}")
    return out_path


if __name__ == "__main__":
    build()
