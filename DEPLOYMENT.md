# Deploying Kryos

This covers deploying the three regional backends (Render) and the dashboard (Vercel), using the prep work already committed: `Dockerfile`, `render.yaml`, `requirements-serving.txt`, `scripts/export_serving_data.py`, and the trimmed `deploy_data/` bundle (~8MB total, already committed, real data — see that script's docstring for what's included and why).

Use this for a shareable link people can open anytime. **For the actual live judging demo, run it locally instead** — zero network/cold-start risk, and you already know it works.

---

## 1. Push to GitHub

Render and Vercel both deploy from a GitHub repo. If this repo isn't already pushed, do that first — both platforms need to be able to see it.

## 2. Backend — Render

1. Go to [render.com](https://render.com), sign up/log in (GitHub login is easiest — it wires up repo access at the same time).
2. **New → Blueprint**, pick this repo. Render reads `render.yaml` and shows you three services: `kryos-weddell`, `kryos-prydz-bay`, `kryos-ross-sea`.
3. Before clicking deploy, note: `render.yaml` sets `plan: starter`, not the free tier — **keep it that way**. Render's free tier spins down after ~15 min idle, and the cold-start on the next request stacks on top of the isochrone router's own ~30s, which will look broken to anyone clicking the deployed link cold. Starter is a low, flat monthly cost per service (check Render's current pricing) and stays warm.
4. Click **Apply** / **Deploy Blueprint**. Render builds all three Docker images (each `--build-arg REGION=<name>`) and starts them. First build takes a few minutes per service (real PyTorch install, not instant).
5. Once deployed, each service has its own URL, e.g. `https://kryos-weddell.onrender.com`. **Copy all three URLs** — you need them for the frontend step.
6. Sanity-check each one directly: open `https://kryos-weddell.onrender.com/api/manifest` in a browser — should return real JSON (`"region": "weddell"`, bounds, etc.), not an error.

## 3. Frontend — Vercel

1. Go to [vercel.com](https://vercel.com), sign up/log in (GitHub login again).
2. **Add New → Project**, pick this repo.
3. Vercel needs to know the frontend lives in `dashboard/`, not the repo root:
   - **Root Directory**: `dashboard`
   - **Framework Preset**: Vite (should auto-detect)
   - **Build Command**: `npm run build` (default)
   - **Output Directory**: `dist` (default)
4. **Environment Variables** — add these three, using the real Render URLs from step 2.6:
   - `VITE_WEDDELL_API_URL` = `https://kryos-weddell.onrender.com`
   - `VITE_PRYDZ_BAY_API_URL` = `https://kryos-prydz-bay.onrender.com`
   - `VITE_ROSS_SEA_API_URL` = `https://kryos-ross-sea.onrender.com`

   (Vite only inlines `VITE_*` vars at *build* time — if you change one later, you need to redeploy the frontend, not just wait.)
5. Deploy. Vercel gives you a URL like `https://kryos-xyz.vercel.app`.

## 4. Close the loop: tell the backends about the frontend

The backends' CORS policy only allows `localhost` by default (see `src/backend/app.py`) — a deployed frontend on a different origin gets silently blocked by the browser until you set this:

1. Back in Render, for **each** of the three services: **Environment** tab → add `FRONTEND_ORIGIN` = your real Vercel URL (e.g. `https://kryos-xyz.vercel.app`, no trailing slash). Comma-separate if you have more than one (e.g. a preview-deploy URL too).
2. Save — Render redeploys automatically when an env var changes.

## 5. Verify

Open the Vercel URL. You should see the splash screen, then the planner, with the region switcher pulling real data from all three Render services. Try planning a journey in each region.

If you get a "failed to load data" screen: check the browser console for a CORS error (means step 4 wasn't done or the URL doesn't match exactly) vs. a network error (means the Render URL in step 3.4 is wrong or that service isn't up).

---

## Known limitations of this deployment, stated plainly

- **The live-forecast weather files go stale.** `deploy_data/<region>/data/raw/<region>/weather/{wind,current}_openmeteo.csv` are a real ~8-day forecast snapshot from whenever you last ran `scripts/export_serving_data.py`. They are *not* refreshed automatically once deployed. For a demo link that needs to stay accurate over time, either re-run the export + redeploy periodically, or set up a scheduled job (out of scope here, real follow-up work) that re-runs `download_weather.py` + re-uploads inside the running container.
- **Three separate backend processes, not one.** This mirrors the local dev setup exactly (see `PROJECT_STATUS.md` section 4) — there's no live per-request region switch server-side.
- **Cost**: three `starter`-tier Render services running continuously is a real, ongoing cost, not free. If that's not acceptable, the free tier works but accept the cold-start tradeoff described in step 2.3, or only deploy one region (e.g. Weddell) as the shareable link and keep the others local-only.
