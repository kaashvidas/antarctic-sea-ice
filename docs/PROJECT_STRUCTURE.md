# Project Structure & Contributor Guide

This document explains what lives where in this repo and how the pieces fit together. For the project pitch itself (problem, mental model, datasets, papers), see the top-level [`README.md`](../README.md). For the full setup walkthrough, see [`STEP_BY_STEP_GUIDE.md`](./STEP_BY_STEP_GUIDE.md).

---

## Folder layout

```
antarctic-nav-platform/
├── README.md                  Project pitch, mental model, datasets, build phases
├── requirements.txt            Shared Python dependencies (pip install -r this)
├── .gitignore                  Excludes venv/, raw data, credentials, node_modules
│
├── src/                         All Python source code
│   ├── data/                    Layer 1 — pulling raw data from public sources
│   │   ├── download_seaice.py       NSIDC sea-ice concentration (earthaccess)
│   │   ├── download_era5.py         ERA5 wind/temperature reanalysis (cdsapi)
│   │   ├── download_icebergs.py     USNIC tracked iceberg positions (no auth)
│   │   ├── download_bathymetry.py   NCEI DEM mosaic bathymetry export (no auth)
│   │   └── preprocess.py            Crop to bounding box + regrid to shared grid
│   │
│   ├── models/
│   │   ├── seaice_forecast/         Module 1 — sea-ice concentration forecaster
│   │   │   ├── baseline.py              Persistence + climatology baselines
│   │   │   ├── convlstm.py              Trained ConvLSTM (the one real ML model)
│   │   │   └── train.py                 Training loop, dataset wrapper
│   │   ├── iceberg_drift/           Module 2 — iceberg drift engine
│   │   │   └── wagner_model.py          Wagner et al. (2017) physics port + sea-ice coupling
│   │   └── routing/                 Module 3 — route optimizer
│   │       └── isochrone.py             Cost grid, A* (working), isochrone (stretch)
│   │
│   ├── integration/
│   │   └── pipeline.py              Phase 5 — chains Modules 1→2→3, outputs GeoJSON/PNG
│   │
│   ├── backend/
│   │   └── app.py                   Phase 6 backend — serves outputs/ to the dashboard
│   │
│   └── utils/
│       ├── grid.py                  THE shared spatial grid definition — read this first
│       └── plotting.py              Quicklook plots + route comparison figures
│
├── dashboard/                   React + Leaflet frontend (Phase 6, separate from src/)
│
├── data/
│   ├── raw/                      Downloaded files land here (gitignored)
│   └── processed/                Cropped/regridded outputs (gitignored)
├── outputs/                      GeoJSON + sea-ice PNGs the dashboard reads (gitignored)
│
├── notebooks/
│   └── 01_data_exploration.ipynb   Scratch space — not imported by anything in src/
│
└── docs/
    ├── STEP_BY_STEP_GUIDE.md      Full setup walkthrough
    ├── PROJECT_STRUCTURE.md       This file
    └── papers/                    Key reference papers (PDFs gitignored; see papers/README.md)
```

---

## The one file to agree on before writing any model code

**`src/utils/grid.py`** defines the bounding box, resolution, and forecast horizon that every other module imports. It is now **locked** — see its docstring for how the current bounds (a real Weddell Sea iceberg cluster, not a guess) were derived. Layers 2a (sea-ice forecast) and 2b (iceberg drift) share this grid and forecast timestamps; changing it now means re-running every downstream module.

---

## How the layers connect

```
LAYER 1 — PERCEPTION      src/data/*.py → src/data/preprocess.py
   satellite + reanalysis data, cropped and regridded onto src/utils/grid.py
        │
        ▼
LAYER 2 — PREDICTION      src/models/seaice_forecast/  +  src/models/iceberg_drift/
   (a) sea-ice concentration forecast
   (b) iceberg drift forecast — COUPLED to (a) via sea-ice locking physics
        │
        ▼
LAYER 3 — DECISION        src/models/routing/isochrone.py
   cost-grid route optimizer (distance vs. ice/iceberg risk)
        │
        ▼
LAYER 4 — COMMUNICATION   src/integration/pipeline.py → outputs/*.geojson → src/backend/ → dashboard/
```

---

## Who works where

Each person works mainly inside their own subfolder so merge conflicts stay rare:

| Area | Owner works in | Shared files to message the team before editing |
|---|---|---|
| Data pipeline | `src/data/` | `src/utils/grid.py` |
| Sea-ice forecasting | `src/models/seaice_forecast/` | `src/utils/grid.py` |
| Iceberg drift | `src/models/iceberg_drift/` | `src/utils/grid.py` |
| Route optimization | `src/models/routing/` | — |
| Integration | `src/integration/pipeline.py` | touches everyone's output — coordinate before changing interfaces |
| Dashboard/frontend | `dashboard/`, `src/backend/` | reads `outputs/*` — agree on the schema early (see `src/integration/pipeline.py`'s `routes_to_geojson`/`write_manifest` for the current one) |

---

## Setup, in order

1. `python -m venv venv && venv\Scripts\activate` (Windows) or `source venv/bin/activate` (each person, locally)
2. `pip install -r requirements.txt`
3. Get your own free credentials — Earthdata login (NSIDC), CDS API key in `~/.cdsapirc` (ERA5). Never commit these; `.gitignore` already excludes `.cdsapirc` and `.env`. (`download_icebergs.py` and `download_bathymetry.py` need no credentials at all.)
4. Smoke-test the data layer: `python src/data/download_seaice.py --start 2024-01-01 --end 2024-01-07`
5. `src/utils/grid.py` is locked — read its docstring rather than re-deciding the bounding box.
6. Run the full pipeline once data exists: `python -m src.integration.pipeline`, then `uvicorn src.backend.app:app --reload --port 8000` and the dashboard dev server (see `dashboard/README.md`).

---

## Build order & what's already stubbed vs. working

(Updated 2026-09-12 — see README.md's "Build-status note" for the full honesty-pass writeup.)

| File | Status |
|---|---|
| `src/utils/grid.py` | **Locked.** Bounding box is data-derived from a real USNIC pull (Weddell Sea, six tracked icebergs), not a placeholder. |
| `src/data/download_icebergs.py` | Working — real data, confirmed URL fix applied. |
| `src/data/download_bathymetry.py` | **New.** Working — real NCEI DEM mosaic export, no login needed. |
| `src/data/download_seaice.py`, `download_era5.py` | Written and ready, but **not yet run for real** — blocked on missing Earthdata/CDS credential files on this machine. |
| `src/data/preprocess.py` | Crop + regrid (lat/lon `.interp`/`griddata`) + bathymetry regridding all implemented and mechanically tested on synthetic data. |
| `src/models/seaice_forecast/baseline.py` | Working — two real bugs fixed during testing (numpy.datetime64 arithmetic in `persistence_forecast`, missing pandas conversion in `climatology_forecast`). |
| `src/models/seaice_forecast/convlstm.py` | Working architecture, trained. |
| `src/models/seaice_forecast/train.py` | **Trained on real data** — 731 days of real AMSR2 history (`src/data/download_seaice_bremen.py` + `build_seaice_history.py`, no NSIDC needed), genuinely beats persistence (MAE 0.047 vs 0.090) and climatology on a held-out chronological split. Checkpoint at `data/processed/convlstm_checkpoint.pt`, picked up automatically by `pipeline.py`'s `get_seaice_concentration()`. See README's Build-status note for the full skill table. |
| `src/models/iceberg_drift/wagner_model.py` | **Real port** of the WDE17 reference notebook's analytical drift solution (Eqs 6-9), adapted for Southern Hemisphere Coriolis sign; lat/lon advection, melt terms, and haversine validation all implemented and tested against a real iceberg's real dimensions. |
| `src/models/routing/isochrone.py` | A* and naive route working, tested on a real bathymetry+risk cost grid. Isochrone method still stubbed (stretch goal, first to cut per this project's own priority order). |
| `src/integration/pipeline.py` | Full orchestration working end-to-end: real iceberg cluster → real trained-ConvLSTM sea-ice forecast → real drift ensemble (real wind/current) → real bathymetry → cost grid → A*/naive routes → GeoJSON + sea-ice PNGs + manifest. `get_seaice_concentration()`/`get_forcing_fields()` are the real-data-first swap points, each with a disclosed fallback (see manifest's `data_sources`) if a given input's files are ever missing. |
| `src/backend/app.py` | **New.** FastAPI serving `outputs/*` to the dashboard — tested. |
| `dashboard/` | Built in Phase 6 (React + Vite + Leaflet) — see `dashboard/README.md` for run instructions. |
