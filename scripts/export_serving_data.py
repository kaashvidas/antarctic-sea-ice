"""
Build a trimmed, deploy-sized copy of one region's real data, for
shipping inside a Docker image instead of the full local data/ tree.

Why this exists: the live serving path (pipeline.py's
_run_convlstm_forecast) only ever reads the last `input_seq_len` (7)
real days of seaice_history.nc for its autoregressive rollout -- but
the actual file on disk is the full multi-year training history
(260-326 MB per region, most of it dead weight once training is done).
Everything else the live app touches is already small. This script
copies exactly what /api/plan_journey and /api/manifest need to run
correctly, nothing more:

  - data/processed/<region>/convlstm_checkpoint.pt        (small, as-is)
  - data/processed/<region>/convlstm_multiday_skill.json  (small, as-is)
  - data/processed/<region>/seaice_history.nc             (TRIMMED to the
    real last KEEP_DAYS days, not the full multi-year file)
  - data/raw/<region>/bathymetry/bathymetry.tif            (small, as-is)
  - data/raw/<region>/weather/{wind,current}_openmeteo.csv (small, as-is
    -- the LIVE forecast files, not the multi-year historical archive,
    which training/validation needed but serving never reads)
  - data/raw/icebergs/antarctic_icebergs_latest.csv         (shared, as-is)
  - data/raw/seaice_bremen/ (last FALLBACK_TIF_COUNT real files only --
    cheap insurance for the persistence-fallback path if ConvLSTM
    inference ever throws, not the full circumpolar archive)
  - outputs/<region>/                                       (small, as-is)

Real data throughout -- this trims volume, it does not fabricate or
downsample anything. Run once per region before building that region's
deploy image; re-run whenever you want the deployed bathymetry/weather/
checkpoint refreshed with newer real data.

Usage: python scripts/export_serving_data.py <region> [--out deploy_data]
"""
import argparse
import shutil
from pathlib import Path

import xarray as xr

REPO_ROOT = Path(__file__).resolve().parents[1]
KEEP_DAYS = 30          # generous buffer over any real checkpoint's input_seq_len
FALLBACK_TIF_COUNT = 3  # cheap persistence-fallback insurance, not the full archive


def export(region: str, out_root: Path):
    src_processed = REPO_ROOT / "data" / "processed" / region
    src_raw_region = REPO_ROOT / "data" / "raw" / region
    src_raw_icebergs = REPO_ROOT / "data" / "raw" / "icebergs"
    src_raw_bremen = REPO_ROOT / "data" / "raw" / "seaice_bremen"
    src_outputs = REPO_ROOT / "outputs" / region

    dst_processed = out_root / region / "data" / "processed" / region
    dst_raw_region = out_root / region / "data" / "raw" / region
    dst_raw_icebergs = out_root / region / "data" / "raw" / "icebergs"
    dst_raw_bremen = out_root / region / "data" / "raw" / "seaice_bremen"
    dst_outputs = out_root / region / "outputs" / region

    for d in (dst_processed, dst_raw_region, dst_raw_icebergs, dst_raw_bremen, dst_outputs):
        d.mkdir(parents=True, exist_ok=True)

    # --- checkpoint + multiday skill: copy as-is, already small ---
    for name in ("convlstm_checkpoint.pt", "convlstm_multiday_skill.json"):
        src = src_processed / name
        if src.exists():
            shutil.copy2(src, dst_processed / name)
            print(f"copied {src.relative_to(REPO_ROOT)} ({src.stat().st_size / 1024:.0f} KB)")
        else:
            print(f"WARNING: {src} missing -- the deployed app will be missing this")

    # --- seaice_history.nc: trim to the real last KEEP_DAYS days ---
    hist_src = src_processed / "seaice_history.nc"
    if hist_src.exists():
        ds = xr.open_dataset(hist_src)
        trimmed = ds.isel(time=slice(-KEEP_DAYS, None))
        hist_dst = dst_processed / "seaice_history.nc"
        trimmed.to_netcdf(hist_dst)
        print(f"trimmed seaice_history.nc: {ds.sizes['time']} days ({hist_src.stat().st_size / 1e6:.0f} MB) "
              f"-> {trimmed.sizes['time']} days ({hist_dst.stat().st_size / 1e6:.1f} MB)")
    else:
        print(f"WARNING: {hist_src} missing -- required for the app to serve real forecasts")

    # --- bathymetry + live-forecast weather: copy as-is, already small ---
    bathy_src = src_raw_region / "bathymetry" / "bathymetry.tif"
    if bathy_src.exists():
        (dst_raw_region / "bathymetry").mkdir(parents=True, exist_ok=True)
        shutil.copy2(bathy_src, dst_raw_region / "bathymetry" / "bathymetry.tif")
        print(f"copied bathymetry.tif ({bathy_src.stat().st_size / 1024:.0f} KB)")

    weather_src = src_raw_region / "weather"
    (dst_raw_region / "weather").mkdir(parents=True, exist_ok=True)
    for name in ("wind_openmeteo.csv", "current_openmeteo.csv"):
        src = weather_src / name
        if src.exists():
            shutil.copy2(src, dst_raw_region / "weather" / name)
            print(f"copied weather/{name}")
        else:
            print(f"WARNING: {src} missing -- re-run download_weather.py for REGION={region} first")

    # --- shared iceberg feed: copy as-is ---
    ib_src = src_raw_icebergs / "antarctic_icebergs_latest.csv"
    if ib_src.exists():
        shutil.copy2(ib_src, dst_raw_icebergs / "antarctic_icebergs_latest.csv")
        print("copied shared antarctic_icebergs_latest.csv")

    # --- tiny AMSR2 fallback slice ---
    if src_raw_bremen.exists():
        latest = sorted(src_raw_bremen.glob("seaice_*.tif"))[-FALLBACK_TIF_COUNT:]
        for f in latest:
            shutil.copy2(f, dst_raw_bremen / f.name)
        print(f"copied {len(latest)} fallback AMSR2 tif(s) (persistence-path insurance only)")

    # --- precomputed demo outputs ---
    if src_outputs.exists():
        shutil.copytree(src_outputs, dst_outputs, dirs_exist_ok=True)
        print(f"copied outputs/{region}/")

    total = sum(f.stat().st_size for f in (out_root / region).rglob("*") if f.is_file())
    print(f"\nDone. {region} deploy bundle: {total / 1e6:.1f} MB at {out_root / region}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("region", choices=["weddell", "prydz_bay", "ross_sea"])
    parser.add_argument("--out", default="deploy_data")
    args = parser.parse_args()
    export(args.region, REPO_ROOT / args.out)
