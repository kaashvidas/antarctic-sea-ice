"""Domain-aware filesystem locations.

The original Weddell domain keeps its legacy paths so existing downloads
and checkpoints remain usable. Every additional domain is isolated below
``data/domains/<slug>`` and ``outputs/<slug>``.
"""

from pathlib import Path

from src.utils.grid import DEFAULT_DOMAIN_SLUG, GRID


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / "data"
SHARED_RAW_ROOT = DATA_ROOT / "raw"

if GRID.slug == DEFAULT_DOMAIN_SLUG:
    DOMAIN_DATA_ROOT = DATA_ROOT
    OUTPUT_ROOT = PROJECT_ROOT / "outputs"
else:
    DOMAIN_DATA_ROOT = DATA_ROOT / "domains" / GRID.slug
    OUTPUT_ROOT = PROJECT_ROOT / "outputs" / GRID.slug

DOMAIN_RAW_ROOT = DOMAIN_DATA_ROOT / "raw"
PROCESSED_ROOT = DOMAIN_DATA_ROOT / "processed"


def domain_raw_dir(source: str) -> Path:
    """Raw data cropped or sampled specifically for the active domain."""
    return DOMAIN_RAW_ROOT / source


def shared_raw_dir(source: str) -> Path:
    """Raw continent/global products safe to reuse between domains."""
    return SHARED_RAW_ROOT / source
