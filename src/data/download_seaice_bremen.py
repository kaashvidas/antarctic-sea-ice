"""
Layer 1 (Perception) — sea-ice concentration, real-data alternate source.

download_seaice.py (NSIDC G02202 via earthaccess) is blocked on this build
machine — no Earthdata credentials present. This is a real, NO-LOGIN
alternative: the University of Bremen's daily AMSR2 ASI sea-ice
concentration product, confirmed live and updated through 2026-09-11 (a
~2-day satellite-processing lag is normal and expected, not a bug).

https://data.seaice.uni-bremen.de/amsr2/asi_daygrid_swath/s6250/<year>/<mon>/Antarctic/asi-AMSR2-s6250-<YYYYMMDD>-v5.4.tif

Different sensor/algorithm than NSIDC's CDR (AMSR2 passive microwave +
ASI algorithm vs. NSIDC's own CDR blend), and a snapshot of the most
recently available day rather than the exact requested date if that day
isn't processed yet -- both disclosed via this module's return value, not
hidden.

Per the ASI product's own documentation: raw GeoTIFF values are 0-100
(percent concentration); 120 flags land, other values above 100 flag
missing/masked data. Native CRS is EPSG:3976 (NSIDC Polar Stereographic
South) -- see preprocess.py's regrid_seaice_bremen() for reprojection
onto the shared analysis grid.
"""

import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.append(str(Path(__file__).resolve().parents[2]))

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "seaice_bremen"

BASE_URL = "https://data.seaice.uni-bremen.de/amsr2/asi_daygrid_swath/s6250"


def _url_for_date(date: datetime) -> str:
    month = date.strftime("%b").lower()
    return f"{BASE_URL}/{date.year}/{month}/Antarctic/asi-AMSR2-s6250-{date.strftime('%Y%m%d')}-v5.4.tif"


def download_latest(out_dir: Path = RAW_DIR, max_days_back: int = 5) -> tuple:
    """
    Try today, then walk backward up to max_days_back days for the most
    recent day the satellite processing pipeline has actually published
    (typically ~2 days behind real time). Returns (file_path, actual_date)
    -- callers should use actual_date, not "today", when labeling this
    data, since it may be a day or two old.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for days_back in range(max_days_back + 1):
        date = datetime.now(timezone.utc) - timedelta(days=days_back)
        url = _url_for_date(date)
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200 and len(resp.content) > 1000:
            out_path = out_dir / f"seaice_{date.strftime('%Y%m%d')}.tif"
            out_path.write_bytes(resp.content)
            print(f"Saved {out_path} (real observation date: {date.strftime('%Y-%m-%d')}, "
                  f"{days_back} day(s) before request time)")
            return out_path, date
        print(f"{date.strftime('%Y-%m-%d')} not yet published (status {resp.status_code}), trying earlier...")
    raise RuntimeError(
        f"No AMSR2 sea-ice file found in the last {max_days_back} days — "
        f"check https://data.seaice.uni-bremen.de/amsr2/asi_daygrid_swath/s6250/ manually."
    )


def download_range(start_date: datetime, end_date: datetime, out_dir: Path = RAW_DIR,
                    polite_delay_s: float = 0.5) -> list:
    """
    Bulk-download real daily history for ConvLSTM training (src/models/
    seaice_forecast/train.py needs real multi-month/year history -- this
    is what actually provides it, credential-free). Skips days that
    aren't published (satellite/processing gaps happen -- real data has
    real gaps, don't fabricate a value to fill them) and skips days
    already downloaded, so this is safe to re-run/resume.

    polite_delay_s: a small pause between requests -- this is a free
    public university server, not a commercial API; don't hammer it.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    saved, skipped_existing, missing = [], 0, []
    n_days = (end_date - start_date).days + 1

    for i in range(n_days):
        date = start_date + timedelta(days=i)
        out_path = out_dir / f"seaice_{date.strftime('%Y%m%d')}.tif"
        if out_path.exists():
            skipped_existing += 1
            continue

        resp = requests.get(_url_for_date(date), timeout=30)
        if resp.status_code == 200 and len(resp.content) > 1000:
            out_path.write_bytes(resp.content)
            saved.append(out_path)
        else:
            missing.append(date.strftime("%Y-%m-%d"))
        time.sleep(polite_delay_s)

        if (i + 1) % 50 == 0 or i == n_days - 1:
            print(f"[{i+1}/{n_days}] {len(saved)} saved, {skipped_existing} already had, "
                  f"{len(missing)} missing so far")

    print(f"Done: {len(saved)} newly saved, {skipped_existing} already present, "
          f"{len(missing)} not published for this range.")
    if missing:
        print(f"Missing dates (real satellite/processing gaps): {missing[:20]}"
              f"{'...' if len(missing) > 20 else ''}")
    return saved


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", help="YYYY-MM-DD -- if given with --end, bulk-download a real history range")
    parser.add_argument("--end", help="YYYY-MM-DD")
    args = parser.parse_args()

    if args.start and args.end:
        download_range(datetime.strptime(args.start, "%Y-%m-%d"), datetime.strptime(args.end, "%Y-%m-%d"))
    else:
        download_latest()
