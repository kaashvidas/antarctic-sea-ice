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
"""

import sys
from pathlib import Path

import xarray as xr

sys.path.append(str(Path(__file__).resolve().parents[2]))
from src.data.preprocess import interpolate_weather_samples_historical  # noqa: E402

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
WEATHER_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "weather"


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

    out_path = PROCESSED_DIR / out_name
    ds.to_netcdf(out_path)
    print(f"Saved {out_path} with variables: {list(ds.data_vars)}")
    return out_path


if __name__ == "__main__":
    build()
