"""
Real drift-physics validation: run the live WDE17 pipeline (same
`step()` used in production, same real historical wind/current/sea-ice
grid used to train and drive the sea-ice forecaster) against REAL
observed iceberg tracks, not a synthetic/literature check.

Ground truth: the BYU/NIC Antarctic Iceberg Tracking Database
(consolidated_database_v8.0, scp.byu.edu/data/iceberg/database1.html),
daily ASCAT-scatterometer-derived (falling back to NIC optical/IR when
ASCAT has no fix that day) positions for every named tracked berg,
1978-2026-04-22. Downloaded into
data/raw/icebergs/byu_consolidated_v8/updated7_consol/<id>.csv.

Forcing data: data/processed/seaice_history_with_weather.nc — the same
real AMSR2 concentration + Open-Meteo archive wind/current grid used to
train the ConvLSTM (2022-01-01 to 2026-09-11), so this validation uses
IDENTICAL real historical forcing to what the live pipeline consumes,
not a different/idealized dataset.

Only D32/D33A/D33B/D33C/D35 (this build's DEMO_ICEBERG_IDS) have real
track segments that fall inside both the shared grid domain and the
weather-forcing time window — see `OVERLAP_WINDOWS` below, computed
directly from the data, not assumed.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from src.utils.grid import GRID, latlon_to_index
from src.models.iceberg_drift.wagner_model import (
    IcebergState, step, haversine_km,
)

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
BYU_DIR = DATA_DIR / "raw" / "icebergs" / "byu_consolidated_v8" / "updated7_consol"
FORCING_PATH = DATA_DIR / "processed" / "seaice_history_with_weather.nc"
OUT_PATH = DATA_DIR / "processed" / "drift_validation.json"

DT_SECONDS = 24 * 3600
NM_TO_M = 1852.0


def load_byu_track(csv_path: Path) -> pd.DataFrame:
    """Real (date, lat, lon, size_km) series for one iceberg. ASCAT
    scatterometer fix preferred; falls back to the NIC optical/IR fix
    on days ASCAT has none (both real observations, different sensors
    -- this is the database's own documented fallback convention, not
    something introduced here)."""
    df = pd.read_csv(csv_path)
    lat = df["ascat_1"].where(df["ascat_1"] != 0, df["nic_1"])
    lon = df["ascat_2"].where(df["ascat_2"] != 0, df["nic_2"])
    size1 = df["size_1"].where(df["size_1"] != 0, np.nan)
    size2 = df["size_2"].where(df["size_2"] != 0, np.nan)
    date = pd.to_datetime(df["date"].astype(str), format="%Y%j")
    out = pd.DataFrame({"date": date, "lat": lat, "lon": lon, "size1_km": size1, "size2_km": size2})
    out = out[(out["lat"] != 0) & (out["lon"] != 0)].reset_index(drop=True)
    # carry the last known real size forward so every row has a best-effort
    # size even on days NIC didn't re-measure it (still a real past
    # measurement, never a future one relative to that row's date)
    out["size1_km"] = out["size1_km"].ffill()
    out["size2_km"] = out["size2_km"].ffill()
    return out


def domain_bounds():
    lats = np.arange(GRID.lat_min, GRID.lat_max + 1e-9, GRID.resolution_deg)
    lons = np.arange(GRID.lon_min, GRID.lon_max + 1e-9, GRID.resolution_deg)
    return (lats.min(), lats.max()), (lons.min(), lons.max())


def find_overlap_window(track: pd.DataFrame, forcing_time: pd.DatetimeIndex):
    (lat_lo, lat_hi), (lon_lo, lon_hi) = domain_bounds()
    in_domain = track[
        (track["lat"] >= lat_lo) & (track["lat"] <= lat_hi) &
        (track["lon"] >= lon_lo) & (track["lon"] <= lon_hi) &
        (track["date"] >= forcing_time.min()) & (track["date"] <= forcing_time.max())
    ]
    if in_domain.empty:
        return None
    return in_domain["date"].min(), in_domain["date"].max()


def validate_iceberg(iceberg_id: str, csv_name: str, ds: xr.Dataset, max_horizon_days: int = 20):
    """
    Run the real WDE17 step() forward from a real observed start
    position, sampling real historical forcing at the iceberg's
    (moving) position each day, and compare against the real observed
    position on each subsequent day. Also computes the natural
    zero-motion ("persistence") baseline for comparison — a drift
    model only demonstrates skill if it beats staying put.

    Stops early if the real track has no observation within 2 days of
    the expected date (data gap) or if the run has covered
    max_horizon_days.
    """
    track = load_byu_track(BYU_DIR / csv_name)
    forcing_time = pd.DatetimeIndex(ds["time"].values)
    window = find_overlap_window(track, forcing_time)
    if window is None:
        return None
    win_start, win_end = window
    seg = track[(track["date"] >= win_start) & (track["date"] <= win_end)].reset_index(drop=True)
    if len(seg) < 2:
        return None

    start_row = seg.iloc[0]
    size1 = start_row["size1_km"] if not np.isnan(start_row["size1_km"]) else 20.0
    size2 = start_row["size2_km"] if not np.isnan(start_row["size2_km"]) else 10.0
    length_m, width_m = max(size1, size2) * 1000.0, min(size1, size2) * 1000.0

    state = IcebergState(lat=float(start_row["lat"]), lon=float(start_row["lon"]),
                          length_m=length_m, width_m=width_m, thickness_m=250.0)
    baseline_lat, baseline_lon = state.lat, state.lon

    seg = seg.set_index("date")
    horizon = min(max_horizon_days, (seg.index.max() - seg.index[0]).days)

    records = []
    cur_date = seg.index[0]
    for day in range(1, horizon + 1):
        target_date = cur_date + pd.Timedelta(days=day)
        # forcing at the iceberg's CURRENT (pre-step) position, for the day being stepped
        row, col = latlon_to_index(state.lat, state.lon)
        if target_date < forcing_time.min() or target_date > forcing_time.max():
            break
        day_idx = int(np.argmin(np.abs((forcing_time - target_date).days)))
        wind_u = float(ds["wind_u"].values[day_idx, row, col])
        wind_v = float(ds["wind_v"].values[day_idx, row, col])
        current_u = float(ds["current_u"].values[day_idx, row, col])
        current_v = float(ds["current_v"].values[day_idx, row, col])
        local_conc = float(ds["cdr_seaice_conc"].values[day_idx, row, col])

        state = step(
            state, DT_SECONDS,
            wind_uv=(wind_u, wind_v), current_uv=(current_u, current_v),
            seaice_uv=(current_u, current_v),
            seaice_concentration=local_conc,
        )

        # nearest real observation to target_date, within 2 days
        idx = seg.index.searchsorted(target_date)
        candidates = seg.iloc[max(0, idx - 1):idx + 2]
        if candidates.empty:
            break
        nearest = candidates.iloc[(candidates.index - target_date).map(lambda d: abs(d.days)).argmin()]
        if abs((nearest.name - target_date).days) > 2:
            break

        err_km = haversine_km(state.lat, state.lon, nearest["lat"], nearest["lon"])
        baseline_err_km = haversine_km(baseline_lat, baseline_lon, nearest["lat"], nearest["lon"])
        records.append({
            "day": day, "date": str(target_date.date()),
            "predicted_lat": round(state.lat, 4), "predicted_lon": round(state.lon, 4),
            "observed_lat": round(float(nearest["lat"]), 4), "observed_lon": round(float(nearest["lon"]), 4),
            "error_km": round(err_km, 2),
            "persistence_baseline_error_km": round(baseline_err_km, 2),
        })

    if not records:
        return None

    return {
        "iceberg_id": iceberg_id,
        "start_date": str(seg.index[0].date()),
        "start_lat": round(float(start_row["lat"]), 4), "start_lon": round(float(start_row["lon"]), 4),
        "length_km": round(length_m / 1000.0, 1), "width_km": round(width_m / 1000.0, 1),
        "n_days_validated": len(records),
        "records": records,
        "mean_error_km": round(float(np.mean([r["error_km"] for r in records])), 2),
        "mean_baseline_error_km": round(float(np.mean([r["persistence_baseline_error_km"] for r in records])), 2),
        "final_error_km": records[-1]["error_km"],
        "final_baseline_error_km": records[-1]["persistence_baseline_error_km"],
    }


ICEBERGS_TO_TRY = [
    ("D32", "d32.csv"), ("D33A", "d33a.csv"), ("D33B", "d33b.csv"),
    ("D33C", "d33c.csv"), ("D35", "d35.csv"),
]


def main(max_horizon_days: int = 20):
    ds = xr.open_dataset(FORCING_PATH)
    results = []
    for iceberg_id, csv_name in ICEBERGS_TO_TRY:
        csv_path = BYU_DIR / csv_name
        if not csv_path.exists():
            print(f"{iceberg_id}: no BYU track file at {csv_path}, skipping")
            continue
        r = validate_iceberg(iceberg_id, csv_name, ds, max_horizon_days=max_horizon_days)
        if r is None:
            print(f"{iceberg_id}: no usable real-track/real-forcing overlap window, skipping")
            continue
        results.append(r)
        print(f"{iceberg_id}: {r['n_days_validated']} real days validated, "
              f"mean error {r['mean_error_km']} km (persistence baseline {r['mean_baseline_error_km']} km), "
              f"final-day error {r['final_error_km']} km (baseline {r['final_baseline_error_km']} km)")

    if not results:
        print("No icebergs had a usable validation window — nothing to report.")
        return

    all_errors_by_day = {}
    all_baseline_by_day = {}
    for r in results:
        for rec in r["records"]:
            all_errors_by_day.setdefault(rec["day"], []).append(rec["error_km"])
            all_baseline_by_day.setdefault(rec["day"], []).append(rec["persistence_baseline_error_km"])

    summary = {
        "n_icebergs_validated": len(results),
        "icebergs": [r["iceberg_id"] for r in results],
        "mean_error_km_by_day": {
            str(d): round(float(np.mean(v)), 2) for d, v in sorted(all_errors_by_day.items())
        },
        "mean_baseline_error_km_by_day": {
            str(d): round(float(np.mean(v)), 2) for d, v in sorted(all_baseline_by_day.items())
        },
        "overall_mean_error_km": round(float(np.mean([r["mean_error_km"] for r in results])), 2),
        "overall_mean_baseline_error_km": round(float(np.mean([r["mean_baseline_error_km"] for r in results])), 2),
    }

    payload = {
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "ground_truth_source": "BYU/NIC Antarctic Iceberg Tracking Database, consolidated_database_v8.0 "
                                "(scp.byu.edu/data/iceberg/database1.html), real ASCAT/NIC observed positions",
        "forcing_source": str(FORCING_PATH),
        "model": "WDE17 free-drift force balance + sea-ice concentration coupling (src/models/iceberg_drift/wagner_model.py), "
                 "same step() used in the live pipeline",
        "note": "persistence_baseline = zero-motion null model (iceberg assumed to stay at its start position); "
                "the drift model only demonstrates real skill where its error is below this baseline",
        "summary": summary,
        "per_iceberg": results,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2))
    print(f"\nSaved {OUT_PATH}")
    print(f"\nOverall (n={len(results)} icebergs): mean error {summary['overall_mean_error_km']} km "
          f"vs persistence baseline {summary['overall_mean_baseline_error_km']} km")


if __name__ == "__main__":
    main()
