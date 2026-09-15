"""
Layer 1 (Perception) — tracked iceberg position data access.

Pulls the US National Ice Center's Antarctic iceberg position/size table.
No authentication needed — this is a plain CSV pull, unlike the NSIDC and
CDS sources.

NOTE: USNIC has changed this link before (it has changed formats before
between fixed-width text and CSV). Confirmed working as of 2026-09-12:
https://usicecenter.gov/File/DownloadCurrent?pId=134 — if this starts
404ing again, re-check https://usicecenter.gov/Products/AntarcIcebergs
for the current link — don't silently swallow a parsing failure, print a
clear error pointing back to that page instead.
"""

from pathlib import Path

import pandas as pd
import requests

import sys
sys.path.append(str(Path(__file__).resolve().parents[2]))
from src.utils.paths import shared_raw_dir  # noqa: E402

RAW_DIR = shared_raw_dir("icebergs")

USNIC_URL = "https://usicecenter.gov/File/DownloadCurrent?pId=134"


def download(url: str = USNIC_URL, out_dir: Path = RAW_DIR):
    out_dir.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    if resp.status_code != 200:
        raise RuntimeError(
            f"USNIC pull failed with status {resp.status_code}. "
            "The download link may have changed — check "
            "https://usicecenter.gov/Products/AntarcIcebergs for the "
            "current format/link and update USNIC_URL above."
        )

    out_path = out_dir / "antarctic_icebergs_latest.csv"
    out_path.write_bytes(resp.content)
    print(f"Saved {out_path}")
    return out_path


def load(csv_path: Path):
    """Load the raw pull into a DataFrame. Inspect columns before assuming
    names — USNIC's schema (typically iceberg ID like 'A23A', lat, lon,
    length/width in nautical miles, last observed date) should be
    confirmed against the actual file, not guessed."""
    df = pd.read_csv(csv_path)
    print(df.columns.tolist())
    print(df.head())
    return df


if __name__ == "__main__":
    path = download()
    load(path)
