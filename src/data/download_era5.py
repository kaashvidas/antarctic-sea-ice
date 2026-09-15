"""
Layer 1 (Perception) — atmospheric forcing data access.

Downloads ERA5 reanalysis (10m wind u/v components, 2m temperature) for
the project's bounding box, using cdsapi. This is the input forcing for
both the sea-ice forecaster (Module 1) and the iceberg drift engine
(Module 2, wind-driven term of the Wagner et al. force balance).

Setup (once per person, not committed to git):
  1. Create a free account at https://cds.climate.copernicus.eu/
  2. Get your personal API token from your CDS user profile page.
  3. Create ~/.cdsapirc (in your HOME directory, NOT this repo) with:
        url: https://cds.climate.copernicus.eu/api
        key: <your-uid>:<your-api-key>
  4. pip install -r requirements.txt (cdsapi is already listed)

CDS request queues can take anywhere from seconds to hours depending on
load — don't assume a hang means it's broken; check the CDS website's
"Your requests" page if a download seems stuck for a long time.
"""

import sys
from pathlib import Path

import cdsapi

sys.path.append(str(Path(__file__).resolve().parents[2]))
from src.utils.grid import lat_lon_bounds  # noqa: E402
from src.utils.paths import domain_raw_dir  # noqa: E402

RAW_DIR = domain_raw_dir("era5")


def download(year: str, month: str, days: list[str], out_file: str = None):
    """
    Pull 10m u/v wind and 2m temperature for the given year/month/days,
    cropped to the shared domain.

    area for the CDS API is [north, west, south, east] — note this is a
    DIFFERENT axis order than earthaccess's bounding_box (west, south,
    east, north) used in download_seaice.py. Easy to transpose by
    accident; the conversion below is deliberate, don't "simplify" it.
    """
    lon_min, lat_min, lon_max, lat_max = lat_lon_bounds()
    area = [lat_max, lon_min, lat_min, lon_max]  # north, west, south, east

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_file = out_file or str(RAW_DIR / f"era5_{year}_{month}.nc")

    client = cdsapi.Client()
    client.retrieve(
        "reanalysis-era5-single-levels",
        {
            "product_type": "reanalysis",
            "variable": [
                "10m_u_component_of_wind",
                "10m_v_component_of_wind",
                "2m_temperature",
            ],
            "year": year,
            "month": month,
            "day": days,
            "time": [f"{h:02d}:00" for h in range(0, 24, 6)],  # 4x daily
            "area": area,
            "format": "netcdf",
        },
        out_file,
    )
    print(f"Saved {out_file}")
    return out_file


if __name__ == "__main__":
    # TODO: replace with the actual date range once Phase 0 locks the
    # validation window (e.g. matching the A23a track period).
    download(year="2024", month="01", days=[f"{d:02d}" for d in range(1, 8)])
