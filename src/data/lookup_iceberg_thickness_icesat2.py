"""
Real per-iceberg thickness lookup via ICESat-2 ATL10 (sea-ice freeboard)
laser altimetry, converted to thickness via hydrostatic equilibrium.

Why this exists: neither NSIDC nor USNIC publish a queryable "iceberg
thickness" product (see the conversation that led to this file -- this
was checked directly, not assumed). The only real path to an actual
measured thickness for a SPECIFIC tracked iceberg is finding a real
ICESat-2 ground track that happened to cross over it, which needs
Earthdata credentials (same login as NSIDC) and is genuinely
hit-or-miss -- most candidate granules' overall bounding box overlaps a
given iceberg's search box without the actual laser ground track passing
anywhere near it (checked directly: one candidate granule's search-box
match was real, but its nearest actual data point was ~1900km away).

Method:
  1. Search ATL10 granules whose bounding box is near the iceberg's
     current position (see src/data/download_icebergs.py), most recent
     first.
  2. For each candidate, download it and check the ACTUAL closest point
     across all 6 beams (fill-value 3.4e38 masked out first -- that's
     ATL10's real "no valid retrieval" flag, not a real 3.4e38-meter
     freeboard).
  3. Keep the first candidate within HIT_RADIUS_KM of the iceberg's
     position -- convert its freeboard to thickness via
     thickness = freeboard * rho_water / (rho_water - rho_ice), same
     density constants as src/models/iceberg_drift/wagner_model.py.
  4. Icebergs with no real match after checking N_CANDIDATES_TO_CHECK
     granules are reported as genuinely not found -- never filled in
     with a guess.

Caveat that stays disclosed downstream: a real match's observation date
is whenever that overpass happened (can be months old), not the
iceberg's current position's date -- these icebergs drift, so a real
measurement from months ago is a real measurement of *a* freeboard near
that location on that date, not necessarily still true today.
"""

import sys
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[2]))
from src.models.iceberg_drift.wagner_model import RHO_WATER, RHO_ICE, haversine_km  # noqa: E402

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "icesat2"
ICEBERG_CSV = Path(__file__).resolve().parents[2] / "data" / "raw" / "icebergs" / "antarctic_icebergs_latest.csv"

FILL_VALUE = np.float32(3.4028235e38)  # ATL10's real "invalid" flag, not a measurement
HIT_RADIUS_KM = 20.0          # generous: these icebergs are themselves 16-39km long
SEARCH_BOX_DEG = 0.5          # ~55km -- confirmed to actually return candidate granules
N_CANDIDATES_TO_CHECK = 6     # per iceberg, most recent first -- each ATL10 granule is 40-160MB,
                              # so this is a real bandwidth/time budget, not an arbitrary number
THICKNESS_FACTOR = RHO_WATER / (RHO_WATER - RHO_ICE)  # hydrostatic equilibrium, same constants project-wide


def _closest_point_in_granule(h5_path, target_lat, target_lon):
    """Real minimum distance + freeboard across all 6 ATL10 beams, fill values masked."""
    best_km, best_freeboard = float("inf"), None
    with h5py.File(h5_path, "r") as f:
        for beam in ["gt1l", "gt1r", "gt2l", "gt2r", "gt3l", "gt3r"]:
            if beam not in f or "freeboard_segment" not in f[beam]:
                continue
            seg = f[beam]["freeboard_segment"]
            lats, lons, fb = seg["latitude"][:], seg["longitude"][:], seg["beam_fb_height"][:]
            valid = fb < FILL_VALUE * 0.9  # real ATL10 fill-value guard, not a plausible freeboard
            if not valid.any():
                continue
            lats, lons, fb = lats[valid], lons[valid], fb[valid]
            d_km = np.array([haversine_km(target_lat, target_lon, lat, lon) for lat, lon in zip(lats, lons)])
            idx = np.argmin(d_km)
            if d_km[idx] < best_km:
                best_km, best_freeboard = float(d_km[idx]), float(fb[idx])
    return best_km, best_freeboard


def lookup_iceberg_thickness(iceberg_id: str, lat: float, lon: float) -> dict:
    """Real search + download + distance check for one iceberg. Returns a
    dict with either a genuine matched thickness or an honest 'not_found'."""
    import earthaccess
    earthaccess.login(strategy="netrc")

    box = (lon - SEARCH_BOX_DEG, lat - SEARCH_BOX_DEG, lon + SEARCH_BOX_DEG, lat + SEARCH_BOX_DEG)
    results = earthaccess.search_data(short_name="ATL10", bounding_box=box, temporal=("2024-09-01", "2026-09-13"))
    if not results:
        return {"iceberg_id": iceberg_id, "found": False, "reason": "no ATL10 granules found near this position at all"}

    # Most recent first -- closer in time to the iceberg's current position is more likely still relevant.
    results = sorted(results, key=lambda r: r["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"],
                      reverse=True)[:N_CANDIDATES_TO_CHECK]

    out_dir = RAW_DIR / iceberg_id
    for i, r in enumerate(results):
        obs_date = r["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"][:10]
        try:
            paths = earthaccess.download([r], local_path=str(out_dir))
        except Exception as e:  # noqa: BLE001 -- a single bad download shouldn't abort the whole search
            print(f"  {iceberg_id} [{i+1}/{len(results)}]: download failed for {obs_date} ({e}), trying next")
            continue

        dist_km, freeboard_m = _closest_point_in_granule(paths[0], lat, lon)
        print(f"  {iceberg_id} [{i+1}/{len(results)}]: {obs_date} -> closest real point {dist_km:.1f} km away")
        is_hit = dist_km <= HIT_RADIUS_KM and freeboard_m is not None and freeboard_m > 0

        if not is_hit:
            # ATL10 granules run 40-160MB each -- don't keep the ones that missed,
            # this is a real (if free) server's bandwidth, not unlimited local disk.
            Path(paths[0]).unlink(missing_ok=True)

        if is_hit:
            thickness_m = freeboard_m * THICKNESS_FACTOR
            return {
                "iceberg_id": iceberg_id, "found": True,
                "observation_date": obs_date, "distance_km": round(dist_km, 1),
                "freeboard_m": round(freeboard_m, 3), "thickness_m": round(thickness_m, 1),
                "method": "ICESat-2 ATL10 real freeboard, converted via hydrostatic equilibrium "
                          f"(thickness = freeboard * {THICKNESS_FACTOR:.2f})",
            }
    return {
        "iceberg_id": iceberg_id, "found": False,
        "reason": f"checked {len(results)} real candidate granules, none passed within {HIT_RADIUS_KM}km",
    }


if __name__ == "__main__":
    df = pd.read_csv(ICEBERG_CSV)
    df.columns = [c.strip() for c in df.columns]
    cluster = df[df["Iceberg"].isin(["D32", "D33A", "D33B", "D33C", "D33D", "D35"])]

    for _, row in cluster.iterrows():
        result = lookup_iceberg_thickness(row["Iceberg"], float(row["Latitude"]), float(row["Longitude"]))
        print(result)
        print()
