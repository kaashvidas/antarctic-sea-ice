"""
Layer 1 (Perception) — bathymetry data access.

Route optimization (Module 3) needs ocean depth to flag infeasible
(too-shallow/grounded) cells. No login needed: NOAA NCEI hosts a global
DEM mosaic (blends GEBCO/ETOPO/regional surveys, best available per
location) as an ArcGIS ImageServer that supports direct bounding-box
export — no huge global file download required, unlike GEBCO's own
interactive-only download app.

Service root: https://gis.ngdc.noaa.gov/arcgis/rest/services/DEM_mosaics/DEM_global_mosaic/ImageServer
Confirmed 2026-09-12: WGS84 (EPSG:4326), single-band float32, meters,
negative = below sea level. If this service ever moves, browse
https://gis.ngdc.noaa.gov/arcgis/rest/services/DEM_mosaics for the
current service name.
"""

import sys
from pathlib import Path

import requests

sys.path.append(str(Path(__file__).resolve().parents[2]))
from src.utils.grid import lat_lon_bounds  # noqa: E402

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "bathymetry"

IMAGE_SERVER_URL = (
    "https://gis.ngdc.noaa.gov/arcgis/rest/services/DEM_mosaics/"
    "DEM_global_mosaic/ImageServer/exportImage"
)


def download(out_dir: Path = RAW_DIR, out_name: str = "weddell_bathymetry.tif",
             pixels_per_degree: int = 16) -> Path:
    """
    Export a GeoTIFF subset of the global DEM mosaic cropped to GRID's
    bounding box (src/utils/grid.py). pixels_per_degree controls output
    resolution — 16 px/degree (~1/16 deg, finer than GRID.resolution_deg)
    is plenty since preprocess.py will regrid this onto the shared grid
    anyway; no need to pull the ImageServer's native ~30m resolution.
    """
    lon_min, lat_min, lon_max, lat_max = lat_lon_bounds()
    width = max(1, round((lon_max - lon_min) * pixels_per_degree))
    height = max(1, round((lat_max - lat_min) * pixels_per_degree))

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / out_name

    resp = requests.get(
        IMAGE_SERVER_URL,
        params={
            "bbox": f"{lon_min},{lat_min},{lon_max},{lat_max}",
            "bboxSR": "4326",
            "imageSR": "4326",
            "size": f"{width},{height}",
            "format": "tiff",
            "pixelType": "F32",
            "interpolation": "RSP_BilinearInterpolation",
            "f": "image",
        },
        timeout=60,
    )
    if resp.status_code != 200 or not resp.content.startswith(b"II") and not resp.content.startswith(b"MM"):
        raise RuntimeError(
            f"Bathymetry export failed (status {resp.status_code}). "
            "The ImageServer may have moved — check "
            "https://gis.ngdc.noaa.gov/arcgis/rest/services/DEM_mosaics for "
            "the current service name and update IMAGE_SERVER_URL above."
        )

    out_path.write_bytes(resp.content)
    print(f"Saved {out_path} ({width}x{height} px)")
    return out_path


def inspect(tif_path: Path):
    """Open the GeoTIFF and print bounds/depth range before assuming
    anything about sign convention or coverage."""
    import rasterio
    import numpy as np

    with rasterio.open(tif_path) as src:
        arr = src.read(1)
        print(f"shape={arr.shape} bounds={src.bounds} crs={src.crs}")
        print(f"depth range (m): {np.nanmin(arr):.1f} to {np.nanmax(arr):.1f}")
        print(f"fraction below sea level: {np.mean(arr < 0):.3f}")
        return src, arr


if __name__ == "__main__":
    path = download()
    inspect(path)
