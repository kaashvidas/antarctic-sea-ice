"""
Phase 6 backend — serves the precomputed outputs/ (GeoJSON, manifest,
sea-ice overlay PNGs) from src/integration/pipeline.py to the dashboard.
Per the README's "precomputed vs. live" Phase 0 decision: this does NOT
re-run the pipeline per-request — it serves whatever's already in
outputs/, so the demo isn't depending on live inference during judging.
Re-run `python -m src.integration.pipeline` to refresh outputs/.

Run: uvicorn src.backend.app:app --reload --port 8001
(port 8000 is avoided on this dev machine -- see dashboard/README.md)
"""

import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response
from pydantic import BaseModel

sys.path.append(str(Path(__file__).resolve().parents[2]))
from src.integration.journey_report import plan_journey, ICE_CLASS_PROFILES  # noqa: E402
from src.utils.grid import ACTIVE_REGION, region_path  # noqa: E402

# Region-scoped: this process serves exactly one region (set via the
# REGION env var, see src/utils/grid.py) -- a different region's outputs/
# live in their own subdirectory, not mixed with this one's.
OUTPUT_DIR = region_path("outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)  # StaticFiles below requires the dir to exist

app = FastAPI(title="Antarctic Navigation Platform API")

# Vite's dev server runs on a different port than the API during
# development. Vite falls back to 5174, 5175, ... if 5173 is already
# taken (common on a dev machine with leftover processes from earlier
# sessions), so pin the HOST but allow any localhost/127.0.0.1 port via
# regex rather than a single hardcoded origin string that breaks the
# moment Vite picks a different port.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/manifest")
def get_manifest():
    manifest_path = OUTPUT_DIR / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(
            status_code=404,
            detail="No manifest.json yet — run `python -m src.integration.pipeline` first.",
        )
    # NOTE: this file is already-serialized JSON text — passing it as
    # JSONResponse's `content` would double-encode it (JSONResponse calls
    # json.dumps on whatever it's given, so a JSON *string* becomes a JSON
    # string containing escaped JSON). Response with the raw text and the
    # right media type serves it as-is instead.
    return Response(content=manifest_path.read_text(), media_type="application/json")


@app.get("/api/routes")
def get_routes():
    routes_path = OUTPUT_DIR / "routes.geojson"
    if not routes_path.exists():
        raise HTTPException(
            status_code=404,
            detail="No routes.geojson yet — run `python -m src.integration.pipeline` first.",
        )
    return Response(content=routes_path.read_text(), media_type="application/json")


class LatLon(BaseModel):
    lat: float
    lon: float


class JourneyRequest(BaseModel):
    start: LatLon
    goal: LatLon
    departure_time: str
    vessel_speed_kmh: float
    ice_class: str


@app.get("/api/ice_classes")
def get_ice_classes():
    """Lets the frontend populate the ice-class dropdown from the same
    table the router actually uses, instead of a hand-copied duplicate."""
    return ICE_CLASS_PROFILES


@app.post("/api/plan_journey")
def post_plan_journey(req: JourneyRequest):
    """
    Computes a real route for the given start/goal/vessel — synchronous,
    not precomputed (see journey_report.py's module docstring for why).
    A full drift-ensemble + A* run on this grid takes ~1-2s, so no job
    queue is needed at this scale.
    """
    try:
        return plan_journey(
            start={"lat": req.start.lat, "lon": req.start.lon},
            goal={"lat": req.goal.lat, "lon": req.goal.lon},
            departure_time=req.departure_time,
            vessel_speed_kmh=req.vessel_speed_kmh,
            ice_class=req.ice_class,
        )
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))


# Serves outputs/seaice/day_NN.png etc. directly at /outputs/seaice/day_NN.png
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")
