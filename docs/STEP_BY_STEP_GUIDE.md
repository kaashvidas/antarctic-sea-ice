# Step-by-Step Guide: Building the Antarctic Platform From Zero
### A plain-language walkthrough for SIH26059 — do these steps in order

This guide assumes you're starting with nothing built yet. Follow it top to bottom. Each step says exactly what to do, what link you need *at that point* (not all at once), and how to know you're actually done before moving on.

---

## STEP 0 — Team decisions (30 minutes, no code)

Before anyone opens an editor, sit together and write down answers to these five questions. Don't skip this — it's the single biggest reason multi-person hackathon projects fall apart mid-build.

1. **Which patch of ocean are we modeling?** Pick one bounded box, not all of Antarctica. Easiest choice: the **Weddell Sea** (roughly 20°W–40°E, 55°S–70°S) — it's the best-studied sector in the physics literature you'll be relying on.
2. **How far ahead do we forecast?** Pick 5–10 days. Don't try to forecast months ahead.
3. **What's our test case?** Use **iceberg A23a** — the world's largest iceberg, publicly tracked by the British Antarctic Survey. You'll use its real historical path to check if your models are any good.
4. **Who owns which piece?** Assign one person each to: (a) getting the data, (b) the iceberg drift model, (c) the sea-ice forecast model, (d) the route planner, (e) the map/dashboard.
5. **What does "done" look like for the demo?** One sentence, agreed by everyone: e.g. "We show A23a's real 2024 path next to our predicted path, plus a recommended ship route around it and the sea ice."

Write these five answers at the top of your shared repo's README. Now you can start building.

---

## STEP 1 — Set up your tools (1–2 hours)

Everyone on the team should do this once, individually.

1. Install **Python 3.10+** if you don't have it.
2. Create a project folder and a virtual environment:
   ```
   python -m venv antarctic-env
   source antarctic-env/bin/activate    # or antarctic-env\Scripts\activate on Windows
   ```
3. Install the core libraries everyone will need regardless of their assigned module:
   ```
   pip install xarray dask netCDF4 numpy pandas matplotlib
   ```
4. If you're on the sea-ice or drift-residual model: also install PyTorch — go to https://pytorch.org/get-started/locally/ and use the command it generates for your OS/GPU situation.
5. If you're on the dashboard: install Node.js (https://nodejs.org/) and set up a basic React app (`npx create-react-app` or Vite).

**Checkpoint:** everyone can run `python -c "import xarray; print('ok')"` without an error.

---

## STEP 2 — Get your data accounts sorted (30–45 minutes, do this on Day 1)

You need **three free accounts** before you can download anything. Do all three now, even before you've decided exactly what data you'll pull — the accounts sometimes take a few minutes to activate, so don't discover that the night before a deadline.

1. **NASA Earthdata Login** (for sea-ice concentration and iceberg-adjacent satellite data)
   → Register free at https://urs.earthdata.nasa.gov/
   → Then install the helper library: `pip install earthaccess`

2. **Copernicus Climate Data Store account** (for ERA5 weather/wind data)
   → Register free at https://cds.climate.copernicus.eu/
   → After logging in, go to your profile page and copy your personal API key
   → Create a file at `~/.cdsapirc` (on your home directory) containing:
     ```
     url: https://cds.climate.copernicus.eu/api
     key: YOUR-KEY-HERE
     ```
   → Install the client: `pip install cdsapi`

3. **Copernicus Marine Service account** (for ocean currents — only needed if you use this optional input)
   → Register free at https://data.marine.copernicus.eu/
   → Install: `pip install copernicusmarine`

**Checkpoint:** you have three working logins and two `.rc`/config files set up. You have not downloaded any real data yet — that's the next step.

---

## STEP 3 — Download a tiny test slice of data (half a day)

Don't download years of global data yet. Prove the pipeline works on a *small* slice first.

1. **Sea-ice concentration** — pick one week, your bounding box only:
   - Dataset: NOAA/NSIDC Climate Data Record of Passive Microwave Sea Ice Concentration
   - Link: https://nsidc.org/data/g02202/versions/6
   - Use `earthaccess` in Python to search and download just a handful of days.

2. **Wind data for the same week/box** from ERA5:
   - Link: https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels
   - Variables you want: `10m_u_component_of_wind`, `10m_v_component_of_wind`, `2m_temperature`

3. **Current iceberg positions** (no account needed at all):
   - Link: https://usicecenter.gov/Products/AntarcIcebergs
   - Download the CSV or shapefile directly.

4. Open all three in Python with `xarray` (for the NetCDF files) or `pandas` (for the iceberg CSV) and just plot them — even a crude matplotlib scatter/imshow. If you can see ice concentration as a colored grid and iceberg dots on a map, your pipeline works end to end.

**Checkpoint:** one Jupyter notebook that downloads, loads, and plots all three, for your bounding box, for a short date range. This is your proof that Step 1's environment and Step 2's accounts actually work together.

---

## STEP 4 — Build the iceberg drift model first (this is your fastest win)

Why first: no training, no neural network, no long experimentation loop. Just physics equations you can implement in an afternoon and test immediately.

1. Read the reference paper conceptually (you don't need every equation, just the idea): Wagner, Dell & Eisenman (2017), "An Analytical Model of Iceberg Drift."
   → Paper: https://journals.ametsoc.org/doi/abs/10.1175/JPO-D-16-0262.1
   → **Public reference code (use this, don't derive from scratch):** https://www.tillwagner.me/wde17 — download the MATLAB file `WDE17_iceberg_model.m` and translate it to Python line by line. This is mechanical work, not new science.

2. Get A23a's historical track to test against:
   → https://www.bas.ac.uk/media-post/new-animation-shows-track-of-giant-a23a-iceberg/ (for the public reference track/dates)
   → Cross-check/pull position data from USNIC's iceberg archive (same link as Step 3).

3. Add the Antarctic-specific twist: sea ice actually drags icebergs. Implement this simple rule on top of the physics:
   - Sea-ice concentration below 15% → ignore sea ice, use pure wind/current physics
   - Between 15–90% → add extra drag force
   - Above 90% → the iceberg just moves with the sea ice's own drift speed instead of its own physics
   → Source for this rule: https://www.cambridge.org/core/journals/journal-of-glaciology/article/modeling-gianticeberg-drift-under-the-influence-of-sea-ice-in-the-weddell-sea-antarctica/814FC678B7F55C698343BF19A4B54CA6

4. Run your model starting from a real past position of A23a, forward a few days, and compare your predicted position to where it actually went.

**Checkpoint:** a script that takes (start position, wind, current, sea-ice concentration) and outputs a predicted path — and when you feed it A23a's real starting conditions, the predicted path is at least roughly near the real one. Don't chase perfection here; a few tens of kilometers of error is fine and expected.

*(Optional, only if this all works with time to spare: look at IDRIFTNET, https://arxiv.org/html/2507.00036, for how to add a small neural network on top that corrects the physics model's errors. Skip this on a first pass.)*

---

## STEP 5 — Build the sea-ice forecasting model

This is your one real "trained AI model" — give it the most time of anything in the project.

1. **Start dumb, on purpose.** Before any neural network, build two baselines:
   - Persistence: "tomorrow's ice = today's ice" (one line of code)
   - Climatology: "tomorrow's ice = the historical average for that day of year" (needs your full downloaded history, a bit more code)
   These aren't throwaway — you'll use them later to prove your real model is actually better than doing nothing clever.

2. **Download more history now** (you only grabbed a week in Step 3) — get several years of the same NSIDC dataset for your bounding box, since your model needs a real training set. Split it by year: e.g., train on older years, validate on a couple of middle years, test on the most recent year. Don't shuffle randomly — this is time-series data.

3. **Build a ConvLSTM model.** In plain terms: it looks at the last several days of ice-concentration maps (like a short video) and predicts the next several days of maps. Look up "PyTorch ConvLSTM implementation" — there are several clean open ones on GitHub to adapt rather than writing the cell logic yourself. Reference paper for why this architecture fits Antarctic sea ice specifically: https://www.sciencedirect.com/science/article/abs/pii/S1463500324000738

4. Train it, then compare its accuracy against your two baselines from step 1. If it doesn't beat persistence, something's wrong before you move on — don't ignore that signal.

**Checkpoint:** a model that takes N days of past ice maps + wind data and outputs a few days of predicted ice maps, with a number showing it beats the "just guess today's ice again" baseline.

---

## STEP 6 — Build the route optimizer

This can be built in parallel with Step 5 by a different teammate, using fake/dummy data at first.

1. Get bathymetry (ocean depth) data for your box:
   → https://www.gebco.net/data_and_products/gridded_bathymetry_data/southern_ocean/

2. Build a **cost function**: for every point on your map grid, compute a number representing "how hard/risky is it to sail through here." Combine: high ice concentration = high cost, close to a predicted iceberg position = high cost, too shallow = infinite cost (impassable).

3. Build the actual route-finding algorithm on top of that cost grid. Two options, pick based on comfort level:
   - Simpler: A* search (standard computer-science pathfinding, treats the grid like a graph)
   - More "how real ships do it": the isochrone method — read https://www.tandfonline.com/doi/full/10.1080/17445302.2024.2329011 for the idea (expand outward step by step under the cost field, rather than searching every possible path)

4. Always output **two** routes: the cheapest/safest one your algorithm finds, and the plain straight-line/shortest-distance one, so you can show them side by side later.

**Checkpoint:** given a fake or real cost grid, start point, and end point, your code draws a route on a plot, and it visibly bends around a high-cost region instead of going straight through it.

---

## STEP 7 — Wire the three pieces together

Now connect what were three separate scripts into one pipeline.

1. Write one script that: takes a date → loads recent ice history → runs Step 5's model forward → feeds that forecast into Step 4's drift model for any nearby tracked icebergs → feeds both into Step 6's cost grid and router → saves everything as simple files (GeoJSON is a good universal format for "stuff to draw on a map").

2. Run this once for your A23a test case and save the output. This precomputed output is what your dashboard will actually read — you are not re-running the neural network live during your demo.

**Checkpoint:** one command that produces a folder of map-ready files representing your full A23a case study, start to finish.

---

## STEP 8 — Build the dashboard

1. Set up a basic React app with a mapping library — **Leaflet** is easier to get started with than deck.gl:
   → https://leafletjs.com/
   For Antarctica specifically, look for a polar stereographic projection plugin, since a normal world map badly distorts the pole.

2. Load Step 7's GeoJSON output onto the map: sea-ice overlay, iceberg position + predicted path, the two routes.

3. Add a simple date slider/scrubber so someone can step through the forecast days and watch the ice and iceberg move — this is your most impressive-per-hour-of-work feature.

**Checkpoint:** you can open the app, see the map, move the slider, and see things change.

---

## STEP 9 — Validate honestly and prepare the pitch

1. Write down, for each model: how far off was it from the real A23a track (in km), and what are its known weak spots (e.g., "doesn't model iceberg breakup," "route cost is a formula we designed, not trained on real fuel data because none is public").
2. Put this on one slide. Judges respond better to an honest "here's our measured error and here's the real gap" than to an unqualified claim of accuracy.
3. Practice showing: the real A23a path vs. your predicted path, then the recommended route vs. the naive route, in under 3 minutes.

---

## If you're running out of time, cut in this order (last resort, not first choice)

1. Skip the ML upgrade to sea-ice forecasting — ConvLSTM alone is fine, don't build the fancier transformer version.
2. Skip the optional IDRIFTNET-style learned correction on the drift model — physics-only is a complete, explainable answer.
3. Use simple A* instead of the isochrone method for routing.
4. Never cut: the data pipeline, the A23a validation, and the side-by-side route comparison on the dashboard — these three are what actually prove your project works.

---

### Quick link reference (everything in one place)

| What | Link |
|---|---|
| Earthdata Login (create account) | https://urs.earthdata.nasa.gov/ |
| Copernicus CDS (create account) | https://cds.climate.copernicus.eu/ |
| Copernicus Marine (create account) | https://data.marine.copernicus.eu/ |
| Sea-ice concentration data | https://nsidc.org/data/g02202/versions/6 |
| ERA5 wind/temperature data | https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels |
| Iceberg positions (USNIC) | https://usicecenter.gov/Products/AntarcIcebergs |
| A23a track reference | https://www.bas.ac.uk/media-post/new-animation-shows-track-of-giant-a23a-iceberg/ |
| Wagner iceberg drift model paper | https://journals.ametsoc.org/doi/abs/10.1175/JPO-D-16-0262.1 |
| Wagner model reference code | https://www.tillwagner.me/wde17 |
| Sea-ice/iceberg locking physics paper | https://www.cambridge.org/core/journals/journal-of-glaciology/article/modeling-gianticeberg-drift-under-the-influence-of-sea-ice-in-the-weddell-sea-antarctica/814FC678B7F55C698343BF19A4B54CA6 |
| ConvLSTM Antarctic sea-ice paper | https://www.sciencedirect.com/science/article/abs/pii/S1463500324000738 |
| Bathymetry data | https://www.gebco.net/data_and_products/gridded_bathymetry_data/southern_ocean/ |
| Isochrone routing method paper | https://www.tandfonline.com/doi/full/10.1080/17445302.2024.2329011 |
| IDRIFTNET (optional stretch model) | https://arxiv.org/html/2507.00036 |
| Leaflet mapping library | https://leafletjs.com/ |
