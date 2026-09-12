# Antarctic Sea-Ice, Iceberg Trajectory & Navigation Decision Support Platform

**SIH26059** · Ministry of Earth Sciences · Smart India Hackathon 2026

An AI/ML decision-support platform that forecasts Antarctic sea-ice concentration, predicts iceberg drift trajectories, and recommends safe, fuel-efficient navigation routes for research vessels — built on public satellite, oceanographic, and meteorological data.

---

## The Problem

India's Antarctic research vessels navigate a moving, poorly-forecast ice environment largely on human judgment reading *current* ice charts, not predictive ones. This isn't hypothetical: the *MV Akademik Shokalskiy* was trapped 10 days in 2013 (a $2.4M rescue, three icebreakers, an iceberg within 370m of the ship), and the *Scenic Eclipse II* was freed from ice near McMurdo Sound by USCG icebreaker *Polar Star* as recently as January 2026. India's new polar research vessel is budgeted at ~$310 million — every voyage is a high-stakes planning problem this platform is meant to de-risk.

**Why this gap exists:** the addressable fleet is tiny (34 COMNAP national Antarctic programs, ~1-2 voyages/season each), so no commercial weather-routing company (StormGeo, DTN) has built Antarctic-specific ice/iceberg modeling. The incumbent solution — national ice centers' human-drawn ice charts — describes *today*, not *five days from now*. Short-term operational sea-ice forecasting is itself still active research, not a shelf product.

## The Pitch

One decision-support platform, three integrated layers, one map:
1. **Forecasts** sea-ice concentration days ahead (not just today's satellite snapshot)
2. **Predicts** where tracked icebergs will drift — physics-based, and coupled to the sea-ice forecast (in the Antarctic, sea ice literally drags icebergs with it)
3. **Recommends** a route trading off distance against forecasted ice/iceberg risk, shown *alongside* the naive shortest path so the safety-vs-fuel tradeoff is visible, not hidden in a black box

No public tool integrates all three today. That's the gap.

---

## Mental Model

Not three separate ML projects — one digital twin of a moving ocean corridor:

```
LAYER 1 — PERCEPTION      "What does the ocean look like right now?"
   satellite + reanalysis data → one shared spatial grid
        │
        ▼
LAYER 2 — PREDICTION      "What will it look like in 3–10 days?"
   (a) sea-ice concentration forecast
   (b) iceberg drift forecast — COUPLED to (a) via sea-ice locking physics
        │
        ▼
LAYER 3 — DECISION        "Given that future, what's the best path?"
   cost-grid route optimizer (distance vs. ice/iceberg risk)
        │
        ▼
LAYER 4 — COMMUNICATION   dashboard: forecast maps, drift cones, route comparison,
                          honest uncertainty
```

**Two rules that govern everything:**
1. Layers 2a and 2b must share the same spatial grid and forecast timestamps — decide this (e.g. 0.25°/25km grid over one bounded Southern Ocean sector) before writing any model code.
2. Every output is a forecast with error — surface uncertainty (confidence bands, probability cones, route comparisons) as a first-class output from day one, not a retrofit.

---

## How Many Models Are We Actually Building?

**1 trained ML model at MVP scope**, plus 2 algorithmic (non-trained) engines:

| # | Component | Type | Notes |
|---|---|---|---|
| 1 | Sea-ice concentration forecaster | **Trained neural net** (ConvLSTM) | The only component with a real train/val/test cycle |
| 2 | Iceberg drift engine | Physics/deterministic (Wagner et al. 2017 + sea-ice locking logic) | No training needed at MVP |
| 3 | Route optimizer | Algorithm (isochrone method / A*) | Not ML — a search over a hand-defined cost function |
| 4 | *(Stretch)* Drift residual-correction net | Trained neural net | IDRIFTNET-style, only after (2) works end-to-end |

**Recommended build order:** (2) iceberg drift physics first — fastest to a testable result, validate directly against A23a's real track → (1) sea-ice ConvLSTM second, give it the most calendar time → (3) route optimizer in parallel with (1) using synthetic data, then wire to real output → (4) only if time remains.

---

## Datasets & Access, by Module

### Module 1 — Sea-ice concentration forecaster

| Dataset | Purpose | Link |
|---|---|---|
| NOAA/NSIDC CDR Passive Microwave Sea Ice Concentration (G02202, v6) | Training target + input history (daily, 25km, since 1978) | https://nsidc.org/data/g02202/versions/6 |
| Near-Real-Time CDR (G10016) | Current conditions | https://nsidc.org/data/g10016/versions/4 |
| Polar Stereographic Ancillary Grid Info (NSIDC-0771) | Lat/lon + land mask | https://nsidc.org/data/nsidc-0771/versions/1 |
| Valid Ice Masks (NSIDC-0622) | Climatological sanity mask | https://nsidc.org/data/nsidc-0622/versions/1 |
| ERA5 reanalysis (10m wind u/v, 2m temp) | Atmospheric forcing input | https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels |
| CMEMS ocean currents/SST *(optional)* | Extra input channel | https://data.marine.copernicus.eu |

**Access:** NSIDC → free Earthdata Login (urs.earthdata.nasa.gov) + `earthaccess` Python lib. ERA5 → free CDS account (cds.climate.copernicus.eu) + personal API token + `cdsapi`. CMEMS → separate free account + `copernicusmarine` package.

### Module 2 — Iceberg drift engine

| Dataset | Purpose | Link |
|---|---|---|
| US National Ice Center Antarctic Iceberg Data | Live tracked iceberg positions/sizes (CSV/shapefile, weekly) | https://usicecenter.gov/Products/AntarcIcebergs |
| A23a historical track (BAS) | Validation case study | https://www.bas.ac.uk/media-post/new-animation-shows-track-of-giant-a23a-iceberg/ |
| ERA5 wind | Drift forcing | (see above) |
| CMEMS ocean currents | Drift forcing | (see above) |
| AMPS (Antarctic Mesoscale Prediction System) | Finer-resolution local/katabatic wind for operational forcing | https://www2.mmm.ucar.edu/rt/amps/ (backup: https://amps-backup.ucar.edu/) |
| Sea-ice concentration (from Module 1 output) | Determines free-drift / drag / locked regime | — |
| IBCSO v2 / GEBCO Southern Ocean bathymetry | Context for drift near shelf breaks | https://www.gebco.net/data_and_products/gridded_bathymetry_data/southern_ocean/ |

**Reference implementation:** Wagner et al. (2017) analytical drift model — public MATLAB code at https://www.tillwagner.me/wde17 (`WDE17_iceberg_model.m`) — port to Python rather than re-deriving.

### Module 3 — Route optimizer

| Dataset | Purpose | Link |
|---|---|---|
| IBCSO v2 / GEBCO bathymetry | Feasibility/cost constraint | https://www.gebco.net/data_and_products/gridded_bathymetry_data/southern_ocean/ |
| Sea-ice forecast (Module 1 output) | Cost input | — |
| Iceberg drift cones (Module 2 output) | Cost input | — |

*No independent dataset needed beyond the two upstream modules' outputs plus bathymetry.*

### Contextual / stretch layers

| Dataset | Purpose | Link |
|---|---|---|
| MEaSUREs Antarctic Grounding Line (NSIDC-0498) | Ice-shelf front position | https://nsidc.org/data/nsidc-0498/versions/2 |
| MEaSUREs Grounding Zone (NSIDC-0778) | Calving-risk context | https://nsidc.org/data/nsidc-0778/versions/1 |
| ITS_LIVE glacier/ice velocity | Glacier dynamics | https://registry.opendata.aws/its-live-data/ |
| Satellite Ice Sheet Mass Balance (Copernicus CDS) | Seasonal iceberg-supply signal | https://cds.climate.copernicus.eu/datasets/satellite-ice-sheet-mass-balance |
| IMBIE data downloads | Aggregated mass-balance CSV, no login | https://imbie.org/data-downloads/ |

---

## Quickstart (what's runnable right now)

```
python -m venv venv && venv\Scripts\activate      # Windows; use source venv/bin/activate elsewhere
pip install -r requirements.txt

python src/data/download_icebergs.py               # real USNIC data, no login
python src/data/download_bathymetry.py              # real NCEI bathymetry, no login
python -m src.integration.pipeline                  # real drift physics + routing -> outputs/

uvicorn src.backend.app:app --reload --port 8000     # serves outputs/ to the dashboard
# in a second terminal, see dashboard/README.md for the frontend
```

NSIDC sea-ice (`src/data/download_seaice.py`) and ERA5 (`src/data/download_era5.py`) need free
Earthdata/CDS credentials (`~/.netrc`, `~/.cdsapirc`) not yet present on this build — until then,
`src.integration.pipeline` runs on disclosed placeholders for those two inputs only (see
`outputs/manifest.json`'s `placeholder_inputs`); everything else in the command block above is real.

---

## Tech Stack

| Layer | Tooling |
|---|---|
| Data ingestion/storage | Python, `xarray`, `dask`, NetCDF, local Parquet/SQLite cache |
| Sea-ice forecasting | PyTorch, ConvLSTM (baseline) → CNN-Transformer hybrid (stretch) |
| Iceberg drift | Python port of Wagner (2017); optional small PyTorch residual net (IDRIFTNET-style) |
| Route optimization | Isochrone method or NetworkX/heapq A* over a NumPy cost grid |
| Backend | FastAPI serving precomputed GeoJSON |
| Frontend | React + Leaflet (polar projection plugin) or deck.gl |
| Spatial storage *(optional)* | PostGIS |

---

## Build Phases

- **Phase 0 — Scoping:** lock bounding box, forecast horizon (5–10 days), validation case, routing algorithm choice, precomputed-vs-live demo split. **Done** — see `src/utils/grid.py`; the live demo scenario is a real six-iceberg Weddell Sea cluster (A23a itself has since disintegrated, see Honest Limitations below).
- **Phase 1 — Data backbone:** one ingestion script per source → crop to bounding box → regrid to shared grid → cache locally. **Done** for icebergs/bathymetry (real data); NSIDC/ERA5 scripts written, pending credentials.
- **Phase 2 — Sea-ice forecaster:** persistence + climatology baselines → ConvLSTM → (stretch) CNN-transformer hybrid. **Done** end-to-end (verified on synthetic data), pending real NSIDC history to train on for real.
- **Phase 3 — Iceberg drift:** Wagner physics port → sea-ice locking coupling → (stretch) residual net. **Done** — real WDE17 port, tested against real iceberg dimensions/positions.
- **Phase 4 — Route optimizer:** cost function → isochrone/A* routing → always show optimized vs. naive route. **Done** for A*/naive (tested on a real cost grid); isochrone left as a stub, see cut order below.
- **Phase 5 — Integration:** one orchestration script chaining 2→3→4, output as GeoJSON layers, precomputed for demo. **Done** — `src/integration/pipeline.py`.
- **Phase 6 — Dashboard:** map + timeline scrubber + route comparison panel + iceberg drift cones.
- **Phase 7 — Validation/honesty pass:** document each module's measured error and known limitations before presenting. **In progress** — see Honest Limitations below; update the ConvLSTM skill table and drift validation numbers once real data is flowing.

**Cut order under time pressure** (protect top items longest): data pipeline + A23a validation (never cut) → CNN-transformer upgrade → residual learning layer → isochrone (fallback to A*) → route comparison view + timeline scrubber (protect until the end).

---

## Key Papers

- Wagner, Dell & Eisenman (2017) — *An Analytical Model of Iceberg Drift* — https://journals.ametsoc.org/doi/abs/10.1175/JPO-D-16-0262.1
- *Modeling giant-iceberg drift under sea-ice influence, Weddell Sea* — https://www.cambridge.org/core/journals/journal-of-glaciology/article/modeling-gianticeberg-drift-under-the-influence-of-sea-ice-in-the-weddell-sea-antarctica/814FC678B7F55C698343BF19A4B54CA6
- IDRIFTNET (2025) — https://arxiv.org/html/2507.00036
- Antarctic sea ice prediction with a ConvLSTM network — https://www.sciencedirect.com/science/article/abs/pii/S1463500324000738
- IceNet, Nature Communications (2021) — https://www.nature.com/articles/s41467-021-25257-4
- Should Sea-Ice Modeling Tools Designed for Climate Research Be Used for Short-Term Forecasting? — https://pmc.ncbi.nlm.nih.gov/articles/PMC7683458/
- Strategies to improve the isochrone algorithm for ship voyage optimisation — https://www.tandfonline.com/doi/full/10.1080/17445302.2024.2329011

---

## Real-World Grounding (for the pitch deck)

- **MV Akademik Shokalskiy**, Dec 2013–Jan 2014 — trapped 10 days, $2.4M rescue cost, iceberg within 370m of the ship.
- **Scenic Eclipse II**, Jan 17, 2026 — wedged near McMurdo Sound, freed by USCG *Polar Star*. Proof this is a live, current-year problem.
- **Halley Research Station (BAS)**, 2016–2018 — relocated 23km on the Brunt Ice Shelf to escape a widening crack; ongoing calving monitoring since.
- **India's new polar vessel:** ~$310M budget — the capital scale every voyage-planning decision touches.

## Users & Revenue (summary)

**Primary:** NCPOR/MoES, for India's own Bharati/Maitri voyages. **Expansion:** the other 33 COMNAP national programs (BAS, AWI, IPEV, AAD, NIPR, etc.) — none have a public equivalent integrated tool. **Secondary:** Antarctic tourism operators, CCAMLR-regulated Southern Ocean fisheries, marine insurers. **Revenue:** primarily government/multilateral infrastructure funding (voyage frequency is too low for SaaS-churn economics); secondary annual licensing benchmarked against commercial ship-routing services ($3,000–15,000/vessel/year).

## Honest Limitations (state these upfront, don't hide them)

- Route costing runs on a synthesized cost function — no public fuel-consumption ground truth exists for polar research vessels.
- Short-term operational sea-ice forecasting is itself open research; report model skill honestly against baselines.
- Ice-shelf calving prediction is out of scope for a working model — treat known unstable zones (e.g. Brunt Ice Shelf) as a labeled risk overlay, not a predicted event.
- This is a days-ahead planning layer, not a replacement for onboard radar, lookout, or a trained ice pilot's real-time judgment.

### Build-status note (as of 2026-09-12)

- **A23a, this README's original validation case, has genuinely disintegrated** (lost ~99% of its area through 2025-2026 and dropped off the tracked-iceberg feed). The live demo scenario now centers on a real cluster of six currently-tracked Weddell Sea icebergs instead (D32, D33A-D, D35 — see `src/utils/grid.py`); A23a's historical track remains usable separately as a drift-model validation case if you pull BAS's archived positions.
- **Real, working, and tested against actual data:** the USNIC iceberg feed, NCEI bathymetry, the WDE17 iceberg drift physics (ported from the authors' own reference notebook, adapted for Southern Hemisphere Coriolis sign), the A* router and naive-route comparison, the full GeoJSON/PNG output pipeline, and the ConvLSTM training loop (mechanically verified against synthetic data pending real NSIDC history).
- **Not yet real, clearly labeled as such in `outputs/manifest.json`'s `placeholder_inputs`:** sea-ice concentration and wind/current forcing. NSIDC (Earthdata) and ERA5 (CDS) downloads are blocked on credential files not being present on the build machine — `src/data/download_seaice.py` and `download_era5.py` are ready to run the moment `~/.netrc`/`~/.cdsapirc` exist; nothing else in the pipeline needs to change.
- **Not attempted:** the isochrone routing method (`isochrone_route` stays a stub) — per this README's own cut order, it's the first thing to drop under time pressure, and a true time-varying isochrone wouldn't add much until real day-by-day sea-ice forecasts replace the current placeholder anyway.

---

## Team

- Data pipeline:
- Sea-ice forecasting model:
- Iceberg drift model:
- Route optimization:
- Dashboard/frontend:

## License / Status

Prototype built for Smart India Hackathon 2026 (SIH26059, Ministry of Earth Sciences). Deadline: 30 September 2026.
