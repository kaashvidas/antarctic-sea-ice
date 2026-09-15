"""
Layer 1 (Perception) — sea-ice concentration data access.

Downloads Antarctic sea-ice concentration (NOAA/NSIDC CDR, G02202 v6) for
the project's bounding box and date range, using earthaccess.

Run once per person, after you've:
  1. Created a free account at https://urs.earthdata.nasa.gov/
  2. pip install -r requirements.txt

This is the tested version of the original throwaway script, wired to the
shared grid definition in src/utils/grid.py so the bounding box here can
never drift out of sync with what Layers 2a/2b assume.
"""

import argparse
import sys
from pathlib import Path

import earthaccess
import xarray as xr

sys.path.append(str(Path(__file__).resolve().parents[2]))
from src.utils.grid import GRID, lat_lon_bounds  # noqa: E402
from src.utils.plotting import quicklook  # noqa: E402
from src.utils.paths import shared_raw_dir  # noqa: E402

RAW_DIR = shared_raw_dir("seaice")


def download(start_date: str, end_date: str, out_dir: Path = RAW_DIR):
    """
    Search and download G02202 v6 granules covering [start_date, end_date].

    NOTE: this dataset is one file per day covering the WHOLE hemisphere —
    there is no per-granule spatial cropping at the search stage.
    bounding_box mainly confirms the granule intersects the domain; the
    real crop happens in preprocess.py after download.
    """
    earthaccess.login()

    results = earthaccess.search_data(
        short_name="G02202",
        version="6",
        temporal=(start_date, end_date),
        bounding_box=lat_lon_bounds(),
    )
    print(f"Found {len(results)} granules for {start_date} to {end_date}")

    if len(results) == 0:
        print(
            "0 results — don't guess and retry blindly. Check "
            "https://search.earthdata.nasa.gov/search?q=G02202 and confirm "
            "the exact short_name/version string matches what's used here."
        )
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    return earthaccess.download(results, local_path=str(out_dir))


def inspect(file_path):
    """Open one file and print its structure before assuming variable
    names — the concentration variable name and grid layout can vary
    slightly by version. Confirm from this printout, don't hard-code
    blindly."""
    ds = xr.open_dataset(file_path)
    print(ds)
    return ds


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2024-01-01", help="YYYY-MM-DD")
    parser.add_argument("--end", default="2024-01-07", help="YYYY-MM-DD")
    parser.add_argument("--inspect-only", action="store_true",
                         help="Skip download, just inspect an already-downloaded file")
    args = parser.parse_args()

    if args.inspect_only:
        existing = sorted(RAW_DIR.glob("*.nc"))
        if not existing:
            print(f"No files found in {RAW_DIR} — run without --inspect-only first.")
            sys.exit(1)
        ds = inspect(existing[0])
    else:
        files = download(args.start, args.end)
        if files:
            ds = inspect(files[0])
            var_name = "cdr_seaice_conc"  # confirm against the printout above
            if var_name in ds.data_vars:
                quicklook(
                    ds[var_name].isel(time=0),
                    title=f"Sea-ice concentration, {args.start}",
                    save_path="seaice_test_plot.png",
                )
            else:
                print(
                    f"'{var_name}' not in ds.data_vars ({list(ds.data_vars)}) — "
                    "update var_name to match, then re-run."
                )
