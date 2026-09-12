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

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "outputs"

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
    allow_methods=["GET"],
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


# Serves outputs/seaice/day_NN.png etc. directly at /outputs/seaice/day_NN.png
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")
