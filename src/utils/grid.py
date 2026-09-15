"""Named spatial domains shared by every data and modelling layer.

The project started with one Weddell Sea validation box. It now keeps
that reproducible case as the default and adds a separate Maitri resupply
corridor. Select a domain before starting Python with, for example::

    $env:ANTARCTIC_DOMAIN = "maitri_india_bay"  # PowerShell
    python -m src.integration.pipeline

Keeping selection process-wide is deliberate: a sea-ice checkpoint,
bathymetry raster, weather samples and route output must never come from
different domains in the same run.
"""

from dataclasses import dataclass, field
import os


@dataclass(frozen=True)
class SiteMarker:
    """A labelled reference point shown on maps but not necessarily navigable."""

    id: str
    label: str
    lat: float
    lon: float
    kind: str
    navigable: bool = False


@dataclass(frozen=True)
class DomainGrid:
    """Configuration for one bounded Southern Ocean operating sector."""

    slug: str = "weddell_validation"
    label: str = "Weddell Sea validation sector"
    description: str = "Large-iceberg validation and demonstration domain."

    lon_min: float = -60.0
    lon_max: float = -35.0
    lat_min: float = -68.0
    lat_max: float = -54.0

    # This remains a regional forecast grid. Local SAR iceberg outlines
    # are vector features and must not be reduced to this resolution.
    resolution_deg: float = 0.25
    forecast_horizon_days: int = 7

    native_crs: str = "EPSG:4326"
    source_crs: str = "EPSG:3412"
    local_metric_crs: str = "EPSG:3031"

    demo_iceberg_ids: tuple[str, ...] = (
        "D32", "D33A", "D33B", "D33C", "D33D", "D35",
    )
    default_route_start: tuple[float, float] = (-65.5, -57.0)  # lat, lon
    default_route_goal: tuple[float, float] = (-56.5, -37.0)   # lat, lon
    site_markers: tuple[SiteMarker, ...] = field(default_factory=tuple)
    bathymetry_filename: str = "weddell_bathymetry.tif"

    def contains(self, lat: float, lon: float) -> bool:
        return self.lat_min <= lat <= self.lat_max and self.lon_min <= lon <= self.lon_max


WEDDELL_VALIDATION = DomainGrid()

MAITRI_INDIA_BAY = DomainGrid(
    slug="maitri_india_bay",
    label="Maitri resupply corridor — India Bay / Lazarev Sea",
    description=(
        "Regional marine approach to India's Maitri station. Ships unload at "
        "India Bay; Maitri itself is inland and is a non-navigable map marker."
    ),
    lon_min=5.0,
    lon_max=20.0,
    lat_min=-72.0,
    lat_max=-62.0,
    resolution_deg=0.25,
    demo_iceberg_ids=(),
    default_route_start=(-64.0, 12.3),
    # Antarctic Treaty inspection report: Indian Bay unloading site,
    # 70°19'S, 12°19'E. This is the maritime endpoint, not Maitri station.
    default_route_goal=(-70.3166667, 12.3166667),
    site_markers=(
        SiteMarker(
            id="india_bay",
            label="India Bay unloading site",
            lat=-70.3166667,
            lon=12.3166667,
            kind="maritime_unloading_site",
            navigable=True,
        ),
        SiteMarker(
            id="maitri_station",
            label="Maitri research station (inland)",
            lat=-70.7661111,
            lon=11.7322222,
            kind="research_station",
            navigable=False,
        ),
    ),
    bathymetry_filename="maitri_india_bay_bathymetry.tif",
)

DOMAINS = {
    WEDDELL_VALIDATION.slug: WEDDELL_VALIDATION,
    MAITRI_INDIA_BAY.slug: MAITRI_INDIA_BAY,
}
DEFAULT_DOMAIN_SLUG = WEDDELL_VALIDATION.slug


def get_domain(slug: str | None = None) -> DomainGrid:
    """Return a named domain, raising a useful error for a bad selection."""
    selected = slug or os.getenv("ANTARCTIC_DOMAIN", DEFAULT_DOMAIN_SLUG)
    try:
        return DOMAINS[selected]
    except KeyError as exc:
        choices = ", ".join(sorted(DOMAINS))
        raise ValueError(f"Unknown Antarctic domain '{selected}'. Choose one of: {choices}") from exc


# Backward-compatible active-domain aliases. Existing modules importing GRID
# continue to work, while a fresh process can select a different complete
# domain through ANTARCTIC_DOMAIN.
GRID = get_domain()
DEMO_ICEBERG_IDS = list(GRID.demo_iceberg_ids)


def lat_lon_bounds(grid: DomainGrid | None = None):
    """Return (west, south, east, north), as download APIs expect."""
    grid = grid or GRID
    return (grid.lon_min, grid.lat_min, grid.lon_max, grid.lat_max)


def n_grid_cells(grid: DomainGrid | None = None):
    """Return (n_lon, n_lat) for a domain's regional forecast grid."""
    grid = grid or GRID
    n_lon = int((grid.lon_max - grid.lon_min) / grid.resolution_deg)
    n_lat = int((grid.lat_max - grid.lat_min) / grid.resolution_deg)
    return n_lon, n_lat


def latlon_to_index(lat: float, lon: float, grid: DomainGrid | None = None):
    """Convert a point to the nearest clamped (row, column) grid index."""
    grid = grid or GRID
    lats, lons = lat_lon_mesh(grid)
    row = int(round((lat - lats[0]) / grid.resolution_deg))
    col = int(round((lon - lons[0]) / grid.resolution_deg))
    row = min(max(row, 0), len(lats) - 1)
    col = min(max(col, 0), len(lons) - 1)
    return row, col


def index_to_latlon(row: int, col: int, grid: DomainGrid | None = None):
    """Convert a (row, column) grid index to (latitude, longitude)."""
    lats, lons = lat_lon_mesh(grid or GRID)
    return float(lats[row]), float(lons[col])


def lat_lon_mesh(grid: DomainGrid | None = None):
    """Return one-dimensional latitude and longitude cell-centre arrays."""
    import numpy as np

    grid = grid or GRID
    n_lon, n_lat = n_grid_cells(grid)
    lons = grid.lon_min + (np.arange(n_lon) + 0.5) * grid.resolution_deg
    lats = grid.lat_min + (np.arange(n_lat) + 0.5) * grid.resolution_deg
    return lats, lons


def domain_public_metadata(grid: DomainGrid | None = None) -> dict:
    """JSON-safe domain metadata for manifests and API clients."""
    grid = grid or GRID
    return {
        "slug": grid.slug,
        "label": grid.label,
        "description": grid.description,
        "default_route": {
            "start": {"lat": grid.default_route_start[0], "lon": grid.default_route_start[1]},
            "goal": {"lat": grid.default_route_goal[0], "lon": grid.default_route_goal[1]},
        },
        "site_markers": [
            {
                "id": marker.id,
                "label": marker.label,
                "lat": marker.lat,
                "lon": marker.lon,
                "kind": marker.kind,
                "navigable": marker.navigable,
            }
            for marker in grid.site_markers
        ],
    }


if __name__ == "__main__":
    print(GRID)
    print("Available domains:", ", ".join(DOMAINS))
    print("Bounding box (west, south, east, north):", lat_lon_bounds())
    print("Approx grid shape (n_lon, n_lat):", n_grid_cells())
