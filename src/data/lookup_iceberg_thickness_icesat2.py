"""
Real per-iceberg thickness lookup via ICESat-2 ATL10 (sea-ice freeboard)
laser altimetry, converted to thickness via hydrostatic equilibrium.

Why this exists: neither NSIDC nor USNIC publish a queryable "iceberg
thickness" product (checked directly, not assumed). The only real path
to an actual measured thickness for a SPECIFIC tracked iceberg is
finding a real ICESat-2 ground track that happened to cross over it --
needs Earthdata credentials and is genuinely hit-or-miss, since a
granule's overall bounding box can span thousands of km while its actual
laser track only clips a small sliver of it (confirmed directly: several
"candidate" granules' real nearest point was 300-1900km away despite a
bounding-box match).

Method (widened per-run, v2 -- checks EVERY real candidate granule per
iceberg, not a capped sample):
  1. Search ATL10 granules near the iceberg's current position (see
     src/data/download_icebergs.py).
  2. STREAM each one (earthaccess.open() + h5py, reading only the
     latitude/longitude/freeboard arrays over HTTPS range requests --
     no full-file download, confirmed ~5-10x faster and avoids
     downloading 40-160MB per candidate for hundreds of candidates).
  3. Track the closest REAL point across all 6 beams (ATL10's 3.4e38
     fill value masked out first -- that's the real "no valid
     retrieval" flag, not a plausible freeboard).
  4. Keep the single closest candidate found across ALL checked
     granules; report it as a genuine match only if within
     HIT_RADIUS_KM, converted to thickness via
     thickness = freeboard * rho_water / (rho_water - rho_ice) (same
     density constants as src/models/iceberg_drift/wagner_model.py).
     Otherwise report the honest closest-approach distance found --
     never filled in with a guess either way.

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

ICEBERG_CSV = Path(__file__).resolve().parents[2] / "data" / "raw" / "icebergs" / "antarctic_icebergs_latest.csv"

FILL_VALUE = np.float32(3.4028235e38)  # ATL10's real "invalid" flag, not a measurement
HIT_RADIUS_KM = 20.0          # generous: these icebergs are themselves 16-39km long
SEARCH_BOX_DEG = 0.5          # ~55km -- confirmed to actually return candidate granules
THICKNESS_FACTOR = RHO_WATER / (RHO_WATER - RHO_ICE)  # hydrostatic equilibrium, same constants project-wide


def _closest_point_streamed(fileset_entry, target_lat, target_lon):
    """Real minimum distance + freeboard across all 6 ATL10 beams, read via
    HTTPS range requests (no full-file download), fill values masked.

    Two-stage per beam: read lat/lon FIRST (cheap-ish) and only pull the
    freeboard array too if this beam actually has a point within the
    coarse pre-filter -- most beams in most granules are hundreds of km
    away (confirmed empirically), so skipping the freeboard fetch for
    those cuts real network time, not just local compute.
    """
    best_km, best_freeboard = float("inf"), None
    with h5py.File(fileset_entry, "r") as f:
        for beam in ["gt1l", "gt1r", "gt2l", "gt2r", "gt3l", "gt3r"]:
            if beam not in f or "freeboard_segment" not in f[beam]:
                continue
            seg = f[beam]["freeboard_segment"]
            lats, lons = seg["latitude"][:], seg["longitude"][:]
            # Coarse pre-filter (flat lat/lon degree distance) -- cheap
            # enough to run before deciding whether this beam is worth a
            # second network round-trip for its freeboard array.
            coarse = np.hypot(lats - target_lat, lons - target_lon)
            near = coarse < 5.0  # ~500km generous pre-filter
            if not near.any():
                continue

            fb = seg["beam_fb_height"][:]
            valid = near & (fb < FILL_VALUE * 0.9)
            if not valid.any():
                continue
            lats, lons, fb = lats[valid], lons[valid], fb[valid]
            d_km = np.array([haversine_km(target_lat, target_lon, lat, lon) for lat, lon in zip(lats, lons)])
            idx = np.argmin(d_km)
            if d_km[idx] < best_km:
                best_km, best_freeboard = float(d_km[idx]), float(fb[idx])
    return best_km, best_freeboard


def lookup_iceberg_thickness(iceberg_id: str, lat: float, lon: float) -> dict:
    """Real search + stream + distance check across EVERY real candidate
    granule for one iceberg. Returns a dict with either a genuine matched
    thickness or the honest closest real approach found."""
    import earthaccess
    earthaccess.login(strategy="netrc")

    box = (lon - SEARCH_BOX_DEG, lat - SEARCH_BOX_DEG, lon + SEARCH_BOX_DEG, lat + SEARCH_BOX_DEG)
    results = earthaccess.search_data(short_name="ATL10", bounding_box=box, temporal=("2024-09-01", "2026-09-13"))
    if not results:
        return {"iceberg_id": iceberg_id, "found": False, "reason": "no ATL10 granules found near this position at all"}

    results = sorted(results, key=lambda r: r["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"],
                      reverse=True)

    best_overall_km, best_overall = float("inf"), None
    n_checked, n_failed = 0, 0
    for i, r in enumerate(results):
        obs_date = r["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"][:10]
        try:
            fileset = earthaccess.open([r])
            dist_km, freeboard_m = _closest_point_streamed(fileset[0], lat, lon)
        except Exception as e:  # noqa: BLE001 -- one bad granule shouldn't abort the whole search
            print(f"  {iceberg_id} [{i+1}/{len(results)}]: stream failed for {obs_date} ({e}), skipping", flush=True)
            n_failed += 1
            continue

        n_checked += 1
        print(f"  {iceberg_id} [{i+1}/{len(results)}]: {obs_date} -> closest real point {dist_km:.1f} km away",
              flush=True)
        if dist_km < best_overall_km and freeboard_m is not None and freeboard_m > 0:
            best_overall_km, best_overall = dist_km, (obs_date, freeboard_m)

        if best_overall_km <= HIT_RADIUS_KM:
            # Real hit -- no need to burn through the rest of this
            # iceberg's ~50 candidates once we have a genuine match.
            break

    if best_overall is not None and best_overall_km <= HIT_RADIUS_KM:
        obs_date, freeboard_m = best_overall
        thickness_m = freeboard_m * THICKNESS_FACTOR
        return {
            "iceberg_id": iceberg_id, "found": True,
            "observation_date": obs_date, "distance_km": round(best_overall_km, 1),
            "freeboard_m": round(freeboard_m, 3), "thickness_m": round(thickness_m, 1),
            "n_candidates_checked": n_checked, "n_candidates_total": len(results),
            "method": "ICESat-2 ATL10 real freeboard, converted via hydrostatic equilibrium "
                      f"(thickness = freeboard * {THICKNESS_FACTOR:.2f})",
        }
    return {
        "iceberg_id": iceberg_id, "found": False,
        "closest_real_approach_km": None if best_overall is None else round(best_overall_km, 1),
        "closest_real_approach_date": None if best_overall is None else best_overall[0],
        "reason": f"checked {n_checked}/{len(results)} real candidate granules ({n_failed} failed to stream), "
                  f"none passed within {HIT_RADIUS_KM}km",
    }


# From the earlier capped (6-candidate) run's real closest-approach
# results -- checking the most promising icebergs first means a genuine
# hit (if any exists) surfaces early rather than after hours of unlikely
# candidates for the ones that were already 300+ km off at their best.
PRIORITY_ORDER = ["D33A", "D33D", "D35", "D32", "D33B", "D33C"]

if __name__ == "__main__":
    df = pd.read_csv(ICEBERG_CSV)
    df.columns = [c.strip() for c in df.columns]
    cluster = df[df["Iceberg"].isin(PRIORITY_ORDER)].copy()
    cluster["_order"] = cluster["Iceberg"].map({v: i for i, v in enumerate(PRIORITY_ORDER)})
    cluster = cluster.sort_values("_order")

    all_results = []
    for _, row in cluster.iterrows():
        result = lookup_iceberg_thickness(row["Iceberg"], float(row["Latitude"]), float(row["Longitude"]))
        print(result, flush=True)
        print(flush=True)
        all_results.append(result)

    print("=" * 60, flush=True)
    print("FINAL SUMMARY (all real data, no guesses):", flush=True)
    for r in all_results:
        print(f"  {r['iceberg_id']}: {r}", flush=True)
