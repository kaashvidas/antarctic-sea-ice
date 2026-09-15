# Project Status & Handoff — Antarctic Sea-Ice / Iceberg / Navigation Platform

SIH26059, Ministry of Earth Sciences. Deadline: **2026-09-30**. This document is for anyone (human or AI) picking up work on this repo — it covers what's real and working, what's actually broken or missing, what to fix now vs. later, and a concrete plan for splitting regional expansion across multiple people/machines. It does not replace `README.md` (the project pitch/architecture doc) — read that first for the "what is this and why" framing; this doc is the "what's the actual state and what do I do next" framing.

Last updated: 2026-09-15, after the 14yr Weddell Sea retrain completed and was promoted (see "Live status" below for the real final numbers and a methodology lesson worth knowing before you compare your own checkpoints).

---

## 1. Current state — what's real and verified right now

Everything below is real data / real measured results, not placeholders, unless explicitly flagged otherwise.

**Data pipeline (all real, no-login sources):**
- Sea-ice concentration: University of Bremen AMSR2 (`src/data/download_seaice_bremen.py`), confirmed circumpolar coverage (not Weddell-specific), real archive back to 2012-07-15.
- Wind + ocean current: Open-Meteo (`src/data/download_weather.py`), real forecast (GFS + marine model) and real historical archive (current archive genuinely starts 2022-01-01, not a bug — confirmed by inspecting raw data).
- Iceberg positions: US National Ice Center (`src/data/download_icebergs.py`), circumpolar, real-time.
- Iceberg historical tracks: BYU/NIC consolidated database (`data/raw/icebergs/byu_consolidated_v8/`), circumpolar, real ASCAT/NIC observations, 1978-2026-04-22.
- Bathymetry: NOAA NCEI global DEM mosaic (`src/data/download_bathymetry.py`), any bounding box, live ArcGIS query.

**Models:**
- ConvLSTM sea-ice forecaster: real trained checkpoint, held-out (never-trained-on) skill measured against persistence and climatology baselines every run — see `held_out_skill` in the checkpoint file, never hand-waved.
- Multi-day autoregressive skill (`src/models/seaice_forecast/evaluate_multiday.py`): measures real error growth from day 1 to day 7 (previous 5yr checkpoint: 0.030 → 0.073 MAE, +142% over the horizon). Surfaced live in the dashboard as a per-day confidence tag.
- Iceberg drift: real WDE17 (Wagner/Dell/Eisenman 2017) physics port, Southern-Hemisphere-corrected Coriolis term (the reference implementation is Northern-Hemisphere-only — this is a genuine, citable fix, not a cosmetic one). `src/models/iceberg_drift/wagner_model.py`.
- **Real drift validation exists** (`src/models/iceberg_drift/validate_drift.py`) — the live physics run against real independent observed tracks (BYU/NIC), not just "looks plausible." Across 5 icebergs, 20-day windows: mean error 14.2km vs. 32.2km for a zero-motion baseline, gap widening with lead time. One iceberg (D33B) does *not* beat baseline — reported honestly, not hidden.

**Routing:**
- Real isochrone (time-stepped Dijkstra) routing, not a stub — `src/models/routing/isochrone.py`. A* fallback if isochrone fails, disclosed via `routing_method` in the API response.
- Ice-class-aware cost model with a real fix (2026-09-14): concentration is now a *steep cost*, not a hard wall, for capable ice classes (Polar Class PC5/PC3+) — a PC3+ vessel can now actually transit dense pack ice instead of being refused outright, which was defeating the purpose of having an ice-class input at all. Weak vessel classes still get a hard wall (correctly — they can't survive dense pack).

**Frontend:**
- Two-view app: journey planner form → report view (map, iceberg panel, weather panel, day-by-day timeline, closest-approach warnings, route comparison).
- Per-day sea-ice forecast confidence disclosure (colored tag/dot, `dashboard/src/format.js`'s `seaIceConfidence()`), driven by the real measured MAE-by-lead-day, not a guess.
- Every data field is tagged real vs. placeholder in the API response and rendered as such — this disclosure discipline is a real differentiator, not decoration.

**Tests:** 24+ tests in `tests/`, all passing as of last full run. Includes real-data-dependent tests that skip cleanly (not fake-pass) when the underlying data/checkpoint isn't present on a given machine.

### Live status — 14yr retrain complete, promoted, here's what actually happened

The 14-year (2012-2026, 5,169 real days) Weddell Sea sea-ice retrain finished and **the 14yr checkpoint is now live**, replacing the previous 5-year one. Two things worth knowing before you repeat this process for a new region:

**1. Per-epoch training time on this CPU-only setup is highly variable — budget for it, don't predict it.** The same config (hidden_dim=32, 2 layers) ran at ~28 min/epoch at one point and ~120+ min/epoch at another, on the *same machine*, no code change (real resource contention, confirmed via CPU-time accounting, not a stall). `train.py` now has early stopping (`--patience`, default 3) and saves a rolling best-checkpoint every time val_loss improves (`<checkpoint_path>.rolling.pt`) specifically because a fixed-epoch run with no intermediate saving nearly wasted 8 hours of real compute when it converged early (by epoch 5) but was still set to grind through 15 more. **Always use `--patience` and check the rolling checkpoint exists early on.**

**2. Don't trust a "compare held_out_skill.mae between two checkpoints" promotion check unless both were evaluated on the SAME window.** The orchestrator's first-pass comparison said the 14yr checkpoint (MAE 0.0468) was *worse* than the 5yr one (0.0462) and correctly declined to promote — but that comparison was invalid: chronological train/val/test splits depend on total dataset length, so the 5yr checkpoint's held-out window was a ~9-month span in 2025, and the 14yr checkpoint's was a ~2-year span in 2022-2024 — different real ice seasons, not a controlled comparison. Re-evaluating both checkpoints on an *identical* fixed recent window (last 300 real days, 2025-11-16 to 2026-09-11, unseen by either model's own training) gave the real answer: **14yr checkpoint MAE 0.0271 vs. 5yr checkpoint MAE 0.0300 — a genuine ~9.7% improvement.** Promoted manually based on this controlled result. **Lesson for anyone comparing checkpoints: always re-evaluate both on one shared, fixed window — don't trust each checkpoint's own self-reported held-out number for a head-to-head comparison.**

Real current numbers (`data/processed/convlstm_checkpoint.pt`, 14yr, promoted 2026-09-15):
- Held-out MAE 0.047, RMSE 0.127 (on its own held-out window; see caveat above about why this isn't directly comparable to the old checkpoint's numbers).
- Multi-day autoregressive skill (`data/processed/convlstm_multiday_skill.json`): day 1 MAE 0.028 → day 7 MAE 0.061 (+118% degradation over the horizon) — an improvement over the previous 5yr checkpoint's day 1 0.030 → day 7 0.073 (+142.6%) at every single lead day.
- Full test suite: 24/24 passing post-promotion.

Old checkpoints kept for reference, not deleted: `convlstm_checkpoint_5yr_backup_v2.pt` (the one just replaced), `convlstm_checkpoint_concentration_only_5yr.pt`, `convlstm_checkpoint_weather_5yr_backup.pt` (confirms weather channels underperform concentration-only — see `README.md`'s build-status note for that earlier finding, still valid).

---

## 2. Targets

Per SIH26059's own framing (see `README.md` for full detail): a decision-support platform that (1) forecasts sea-ice concentration days ahead, (2) predicts iceberg drift coupled to that forecast, (3) recommends a route trading distance against ice/iceberg risk, shown alongside the naive route so the tradeoff is visible. Primary user: NCPOR/MoES for India's Bharati/Maitri voyages. Deadline-driven — the deliverable is a working, honestly-validated demo, not a production system.

---

## 3. Current flaws (real, not hypothetical)

Ranked by how much they actually matter for the pitch:

1. **Domain is Weddell Sea, not near India's actual stations.** Bharati (69.41°S, 76.19°E) and Maitri (70.77°S, 11.73°E) are both in the Indian Ocean sector — nowhere near the Weddell Sea (Atlantic sector, near the Antarctic Peninsula). This is the single biggest gap for a Ministry of Earth Sciences problem statement. See section 6.
2. **Sea-ice forecast skill is real but modest**, not SOTA — day-1 MAE ~0.03-0.05 concentration points, degrading over the week. Genuinely beats naive baselines, honestly measured, but shouldn't be oversold as "solved."
3. **Iceberg thickness is a literature-based size-class lookup**, not a measurement — no public per-iceberg thickness dataset exists (confirmed via an exhaustive real ICESat-2 search this project already did — see `src/data/lookup_iceberg_thickness_icesat2.py`'s docstring for why it didn't pan out). Mitigated: confirmed via direct code read that thickness does NOT actually affect drift velocity in the WDE17 physics (only length/width do) — so this gap is disclosed but not load-bearing.
4. **Melt physics is written but never invoked** in the live pipeline — no real SST source is wired in, so `melt_rates()` exists but nothing calls it with real data.
5. **The codebase assumes exactly one active region at a time.** `GRID`, `DEMO_ICEBERG_IDS`, and every processed-data file path (`seaice_history.nc`, `convlstm_checkpoint.pt`, etc.) are single global constants/paths, not region-scoped. This blocks running multiple regions side-by-side or having multiple people contribute region-specific work without file collisions. See section 6.
6. **Isochrone routing is slow for a live API** — realistically up to ~30s per `/api/plan_journey` request. The frontend has a spinner for this, but it's a real UX cost, not solved.
7. Resolution is 0.25° (~25km) even though the real AMSR2 source is natively 6.25km — a deliberate, disclosed choice (see section 5), not an oversight, but still a real ceiling on forecast sharpness at the ice edge.
8. No mobile/responsive check done. No caching of the last computed route in the frontend (a page refresh loses it).

---

## 4. What's supposed to be fixed right now

- ~~Finish the current 14yr Weddell Sea retrain~~ **Done.** Real result, worth knowing: the orchestrator's first comparison said 14yr data *didn't* beat the old 5yr checkpoint — that comparison was invalid (the two were evaluated on different chronological windows). A controlled re-evaluation on an identical fixed window showed a genuine ~9.7% improvement, and that's what's live now. Full writeup in section 1's "Live status."
- ~~The region-scoping refactor~~ **Done** (2026-09-15). `src/utils/grid.py` now has a `REGIONS` registry; every per-region file goes through a new `region_path()` helper (`data/{raw,processed}/<region>/...`, `outputs/<region>/...`). Existing Weddell data was migrated into `data/processed/weddell/`, `data/raw/weddell/{bathymetry,weather}/`, `outputs/weddell/`. Verified: full test suite passes, live API confirmed working, and switching `REGION=prydz_bay` resolves a completely separate config with zero collision against Weddell's files.

  **How to actually use this for regional work:** set the `REGION` env var to one of `weddell` (default), `prydz_bay`, `queen_maud_land`, or `ross_sea` before running any script, e.g. `REGION=prydz_bay python -m src.data.download_bathymetry` or (Windows) `set REGION=prydz_bay && python -m src.data.download_bathymetry`. Every download/build/train/evaluate script and the backend (`REGION=prydz_bay uvicorn src.backend.app:app --port 8001`) picks it up automatically — nothing else to configure. **Before starting real work on `prydz_bay` or `ross_sea`,** re-verify the `REGION_ICEBERG_IDS` list in `grid.py` against a fresh live USNIC pull (positions/tracked-set membership drift over months, same caveat the original Weddell cluster docstring already carried). **`queen_maud_land`'s iceberg list is explicitly provisional** — only one real nearby berg (D37) was found as of 2026-09-15, re-check before relying on it.

  Known real limitation carried over from this refactor, not fixed: the grid is a simple non-wrapping lon/lat box, so a region crossing the antimeridian (180°/-180°) isn't representable — `ross_sea`'s bounds were chosen to avoid this rather than fix the underlying grid math. Fine for now; would need real work if a future region genuinely requires straddling the dateline.

## 5. What can be stalled for later

- **Resolution increase (0.25° → 0.125°).** Real, worth doing, but expensive (roughly 4x training compute) and needs its own dedicated run with a full epoch budget — don't combine it with other changes in the same run, and don't rush it the way tonight's first attempt at combining it with more data almost did.
- **Hyperparameter sweep + ensembling.** Infrastructure already built (`src/models/seaice_forecast/sweep_and_ensemble.py`, real ensemble-averaging support already wired into `pipeline.py`'s inference) but not run at full scope — deferred because stacking it with the resolution bump and 14yr data in one run wasn't affordable. Fine to leave for a later pass once there's spare compute budget.
- **Melt physics / real SST integration** — real physics exists (`melt_rates()`), just needs a real SST source wired into `step()`'s call site. Second-order effect on drift over a multi-day horizon per WDE17 itself, so not urgent.
- **Isochrone performance optimization, frontend route caching, mobile UX pass** — all real, all lower priority than the above.

---

## 6. Regions to expand to, in order of relevance

All checked against real data this session — not assumed. Every source below (AMSR2, USNIC current positions, BYU/NIC historical tracks, NOAA bathymetry, Open-Meteo weather) is confirmed circumpolar/global, so data availability is *not* the constraint for any of these — the region-scoping refactor (section 4) is.

1. **Prydz Bay / Larsemann Hills (near Bharati, India, 69.41°S 76.19°E).** Highest relevance — real, currently-tracked iceberg cluster confirmed right in this sector: D23 (~4° from Bharati), D15A/B/C/D, D34. Several have deep real historical tracks in the BYU database (D15A: 3,392 rows, D15B: 3,682 rows) — likely at least as strong a drift-validation case as the current Weddell cluster.
2. **Queen Maud Land (near Maitri, India, 70.77°S 11.73°E).** Second — real iceberg presence is thinner here (D37 is the closest real tracked berg, ~less close than Bharati's cluster), but it's India's other station, so still worth covering for narrative completeness.
3. **Ross Sea / McMurdo Sound.** Third — not an Indian station, but a globally significant, heavily-trafficked research hub (McMurdo, Scott Base). Confirmed real tracked icebergs nearby (B22A/F/H, ~165-177°). Good for the "this generalizes beyond one country's stations" pitch angle if there's time.

Weddell Sea (current domain) stays as the baseline/most-mature region regardless.

---

## 7. How this can be done in parallel

**The region-scoping refactor (section 4) has landed — parallel regional work can start now.** The split is clean:

1. Pull latest `main` (which has the region refactor). One person/branch per region (e.g. `region/prydz-bay`, `region/queen-maud-land`, `region/ross-sea`), or just work directly with `REGION=<name>` set if branches feel like overkill for this.
2. Each person runs, for their region only (`REGION=<name>` before every command — see section 4's usage note):
   a. **Re-verify the iceberg cluster first** — `python -m src.data.download_icebergs` (shared/global, already works for any region) then check the live CSV for real bergs near your region's coordinates, cross-check against `data/raw/icebergs/byu_consolidated_v8/updated7_consol/` for historical track depth, and update `REGION_ICEBERG_IDS` in `grid.py` if the provisional list needs correcting. ~15-30 min.
   b. `python -m src.data.download_bathymetry` — seconds.
   c. Sea-ice: re-crop+rebuild from the *already-downloaded* circumpolar AMSR2 archive if your machine already has `data/raw/seaice_bremen/` populated (`python -m src.data.build_seaice_history`, ~10-20 min, no network needed), or a fresh download first if not (`python -m src.data.download_seaice_bremen --start ... --end ...`, longer, network-bound).
   d. `python -m src.data.download_weather --start ... --end ...` — ~30-60 min.
   e. `python -m src.models.seaice_forecast.train --patience 3` — the dominant cost, see the timing notes in section 1 and 8. **Use `--patience`, always** — the whole reason it exists is tonight's near-miss.
   f. `python -m src.models.seaice_forecast.evaluate_multiday` then `python -m src.models.iceberg_drift.validate_drift`.
3. Commit only region-scoped files (thanks to the refactor, these won't collide with anyone else's) plus any `grid.py` correction from step 2a.
4. Merge each region branch once its own test suite subset passes (`REGION=<name> pytest tests/ -q`).

---

## 8. Realistic deliverables and expected time

Be honest with collaborators about this — tonight is a live example of why:

- **Region-scoping refactor:** 2-3 hours, one person, blocking everything else in this section.
- **Per-region data acquisition** (bathymetry, weather, iceberg selection, sea-ice rebuild): under 1 hour per region, fairly predictable.
- **Per-region ConvLSTM training:** the real variable cost. Tonight's 14yr Weddell run saw per-epoch time swing between ~28 min and ~120+ min on the *same unchanged machine* — CPU contention on a personal laptop is real and not fully controllable. Budget **3-9 hours per region, unattended, run overnight**, not "a few hours" as a hard promise. With early stopping now in place, it will not run longer than necessary, and it will not lose progress if interrupted (rolling checkpoint) — but it can still be slow.
- **Per-region drift validation + skill evaluation:** ~30-60 min once training is done, mostly automated script reruns.
- **Net effect of parallelizing across 3 people/machines:** 3 regions ready in roughly the time 1 region takes sequentially on one machine — a real win, but each person's *own* wall-clock time doesn't shrink; they're each still waiting out one real training run.

**Suggested realistic milestone:** region-scoping refactor done in one sitting, then each person kicks off their regional training run to complete overnight, with results reviewed and merged the next day. Two such cycles (refactor day + one overnight run) is a realistic timeline to have three new regions integrated and validated — call it **2-3 days end-to-end**, not a same-day turnaround, given the deadline is 2026-09-30 and there's real margin for this.
