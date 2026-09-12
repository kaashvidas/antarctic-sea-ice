# Phase 6 Dashboard — React + Leaflet

Frontend for the Antarctic sea-ice / iceberg / navigation decision-support
platform (SIH26059). Maps the Weddell Sea (lon -60 to -35, lat -68 to -54):
a togglable sea-ice concentration overlay with a 7-day scrubber, the 6
tracked icebergs (D32, D33A, D33B, D33C, D33D, D35) with their current
positions, predicted drift tracks, and drift-uncertainty cones, and the
optimized (ice-avoiding) vs. naive (straight-line) route comparison.

It's a static Vite/React app — no server-side rendering — that reads
everything from the FastAPI backend in `src/backend/app.py`, which in turn
serves whatever is currently in `outputs/` (manifest, routes GeoJSON,
sea-ice PNGs) produced by `python -m src.integration.pipeline`. The backend
does **not** re-run the pipeline per request, so re-run the pipeline first
if you want fresh outputs.

## Prerequisites

- Node.js 18+ and npm (any recent version; developed against Node 24 / npm
  11)
- Python venv at `venv/` in the repo root with `requirements.txt` installed
  (already set up if you've run the backend/pipeline before)

## 1. Start the backend API (port 8001)

From the **repo root** (`C:\Users\sande\antarctic-sea-ice`), in
PowerShell or Git Bash:

```bash
venv/Scripts/python.exe -m uvicorn src.backend.app:app --reload --port 8001
```

(Port 8001, not 8000 — this dev machine has a stuck orphaned listener on
8000 from an earlier session that the OS won't release. If you're on a
clean machine and want 8000 back, change the port here, in `dashboard/src/api.js`'s
`API_BASE`, and in `App.jsx`'s error message together.)

This serves:
- `GET http://localhost:8001/api/manifest`
- `GET http://localhost:8001/api/routes`
- `GET http://localhost:8001/outputs/seaice/day_NN.png`

If `outputs/manifest.json` / `outputs/routes.geojson` don't exist yet, run
the pipeline first: `venv/Scripts/python.exe -m src.integration.pipeline`.

The backend allows CORS from any `http://localhost:<port>` / `http://127.0.0.1:<port>`
origin (regex, not a single hardcoded port) specifically because Vite falls
back to 5174, 5175, etc. when 5173 is already taken — common on a dev
machine with leftover processes from earlier sessions.

## 2. Start the frontend dev server (port 5173, or the next free one)

In a second terminal, from **this folder** (`dashboard/`):

```bash
npm install      # first time only
npm run dev
```

**Open whatever URL Vite prints** — it's usually **http://localhost:5173**,
but check the terminal output; it'll say "Port 5173 is in use, trying
another one..." and print the real port (e.g. 5174) if so. The map will
show a loading state, then fetch `/api/manifest` and `/api/routes` from
`localhost:8001`. If you see a red error banner instead of the map, the
backend isn't reachable — check step 1.

## Other scripts

```bash
npm run build      # production build to dist/
npm run preview    # preview the production build locally
npm run lint        # oxlint
```

## Project layout

```
src/
  api.js                    # fetch wrappers for the FastAPI backend
  geoutils.js                # GeoJSON [lon,lat] -> Leaflet [lat,lon], convex hull for drift cones
  icebergColors.js           # fixed per-iceberg color assignment
  App.jsx                    # data loading + top-level layout
  components/
    MapView.jsx               # Leaflet map, basemap, fit-to-bounds
    SeaIceOverlay.jsx          # ImageOverlay for the active day_NN.png
    IcebergLayer.jsx           # current position / predicted track / drift cone per iceberg
    RouteLayer.jsx             # optimized (solid green) vs naive (dashed red) routes
    DaySlider.jsx               # styled 0-7 day scrubber + sea-ice toggle/opacity
    DisclosureBanner.jsx        # placeholder-data disclosure, derived from manifest.placeholder_inputs
    Legend.jsx                  # map legend
```

## Known judgment calls

- **Basemap**: CARTO's free `basemaps.cartocdn.com` dark tiles now require
  an API key (they return a watermarked "API key required" placeholder
  tile without one — confirmed while building this). Switched to plain
  OpenStreetMap raster tiles with a CSS filter to darken/desaturate them
  for a chart-like look, since no key is required.
- **Drift cone rendering**: each iceberg's `iceberg_drift_cone` MultiPoint
  (day-7 ensemble endpoints) is rendered as a convex hull polygon rather
  than a scatter, so it reads as a single "uncertainty area" at a glance.
- **Basemap tiles / CORS**: only `/api/*` and `/outputs/*` go through the
  FastAPI backend; map tiles are fetched directly from OpenStreetMap.

