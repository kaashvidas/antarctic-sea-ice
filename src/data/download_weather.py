"""
Layer 1 (Perception) — wind + ocean current data access.

Real, live, NO-LOGIN alternative to ERA5 (CDS) / CMEMS, both of which are
blocked on this build machine (no ~/.cdsapirc, no CMEMS account). Uses
Open-Meteo's free public APIs, which need no API key at all:
  - https://api.open-meteo.com/v1/gfs           (wind, GFS-model-based)
  - https://marine-api.open-meteo.com/v1/marine (ocean current, wave-model-based)
Confirmed working for real Weddell Sea coordinates on 2026-09-13.

Open-Meteo has no gridded bulk-download endpoint — it's a point-query API,
though it DOES accept batched comma-separated lat/lon lists in one
request. So this script samples a coarse grid of representative points
across GRID's bounding box (not every 0.25deg cell — that would be
thousands of points) and preprocess.py's regrid machinery interpolates
those real point samples onto the full shared grid, the same way it
already handles curvilinear-source regridding.

Direction conventions (confirmed against Open-Meteo's own docs, easy to
get backwards — verify before touching this):
  - wind_direction_10m: METEOROLOGICAL convention, direction the wind is
    coming FROM. u = -speed*sin(dir), v = -speed*cos(dir).
  - ocean_current_direction: OCEANOGRAPHIC convention, direction the
    current is heading TOWARD. u = speed*sin(dir), v = speed*cos(dir).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

sys.path.append(str(Path(__file__).resolve().parents[2]))
from src.utils.grid import GRID  # noqa: E402

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "weather"

WIND_URL = "https://api.open-meteo.com/v1/gfs"
CURRENT_URL = "https://marine-api.open-meteo.com/v1/marine"

# Coarse sample grid of representative points across GRID's bounding box —
# deliberately much sparser than the 0.25deg analysis grid (100x56 cells
# would be thousands of API calls); preprocess.py interpolates these real
# samples onto the full grid.
N_SAMPLE_LON, N_SAMPLE_LAT = 10, 7


def _sample_points():
    lons = np.linspace(GRID.lon_min, GRID.lon_max, N_SAMPLE_LON)
    lats = np.linspace(GRID.lat_min, GRID.lat_max, N_SAMPLE_LAT)
    lat_grid, lon_grid = np.meshgrid(lats, lons, indexing="ij")
    return lat_grid.ravel(), lon_grid.ravel()


def download_wind(forecast_days: int = None, out_dir: Path = RAW_DIR) -> Path:
    forecast_days = forecast_days or (GRID.forecast_horizon_days + 1)
    lats, lons = _sample_points()

    resp = requests.get(
        WIND_URL,
        params={
            "latitude": ",".join(f"{v:.3f}" for v in lats),
            "longitude": ",".join(f"{v:.3f}" for v in lons),
            "hourly": "wind_speed_10m,wind_direction_10m",
            "forecast_days": forecast_days,
            "wind_speed_unit": "ms",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Open-Meteo wind request failed (status {resp.status_code}): {resp.text[:300]}")

    rows = []
    payload = resp.json()
    payload = payload if isinstance(payload, list) else [payload]
    for point in payload:
        times = pd.to_datetime(point["hourly"]["time"])
        speed = np.array(point["hourly"]["wind_speed_10m"], dtype=float)
        direction = np.array(point["hourly"]["wind_direction_10m"], dtype=float)
        u = -speed * np.sin(np.radians(direction))  # meteorological "from" convention
        v = -speed * np.cos(np.radians(direction))
        df = pd.DataFrame({"time": times, "wind_u": u, "wind_v": v})
        df["day"] = (df["time"] - df["time"].iloc[0]).dt.days
        daily = df.groupby("day")[["wind_u", "wind_v"]].mean().reset_index()
        daily["lat"], daily["lon"] = point["latitude"], point["longitude"]
        rows.append(daily)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "wind_openmeteo.csv"
    pd.concat(rows, ignore_index=True).to_csv(out_path, index=False)
    print(f"Saved {out_path} ({len(rows)} sample points x {forecast_days} days)")
    return out_path


def download_current(forecast_days: int = None, out_dir: Path = RAW_DIR) -> Path:
    forecast_days = forecast_days or (GRID.forecast_horizon_days + 1)
    lats, lons = _sample_points()

    resp = requests.get(
        CURRENT_URL,
        params={
            "latitude": ",".join(f"{v:.3f}" for v in lats),
            "longitude": ",".join(f"{v:.3f}" for v in lons),
            "hourly": "ocean_current_velocity,ocean_current_direction",
            "forecast_days": forecast_days,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Open-Meteo marine request failed (status {resp.status_code}): {resp.text[:300]}")

    rows = []
    payload = resp.json()
    payload = payload if isinstance(payload, list) else [payload]
    for point in payload:
        times = pd.to_datetime(point["hourly"]["time"])
        speed_kmh = np.array(point["hourly"]["ocean_current_velocity"], dtype=float)
        speed_ms = speed_kmh / 3.6
        direction = np.array(point["hourly"]["ocean_current_direction"], dtype=float)
        u = speed_ms * np.sin(np.radians(direction))  # oceanographic "toward" convention
        v = speed_ms * np.cos(np.radians(direction))
        df = pd.DataFrame({"time": times, "current_u": u, "current_v": v})
        df["day"] = (df["time"] - df["time"].iloc[0]).dt.days
        daily = df.groupby("day")[["current_u", "current_v"]].mean().reset_index()
        daily["lat"], daily["lon"] = point["latitude"], point["longitude"]
        rows.append(daily)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "current_openmeteo.csv"
    pd.concat(rows, ignore_index=True).to_csv(out_path, index=False)
    print(f"Saved {out_path} ({len(rows)} sample points x {forecast_days} days)")
    return out_path


if __name__ == "__main__":
    download_wind()
    download_current()
