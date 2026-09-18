# Deploying Kryos

This covers deploying the three regional backends and the dashboard (Vercel), using the prep work already committed: `Dockerfile`, `render.yaml`, `requirements-serving.txt`, `scripts/export_serving_data.py`, and the trimmed `deploy_data/` bundle (~8MB total, already committed, real data — see that script's docstring for what's included and why).

Use this for a shareable link people can open anytime. **For the actual live judging demo, run it locally instead** — zero network/cold-start risk, and you already know it works.

**Backend host: Google Cloud Run, not Render.** Render's free tier (512MB RAM, 0.1 CPU) was tried first and measured to genuinely fail under real load: a single `/api/plan_journey` request peaks at ~374MB RSS (measured directly, not estimated) on top of Python/uvicorn/OS overhead — that's within a hair of Render's 512MB ceiling for *one* request, so a second concurrent visitor reliably pushes it over and Render kills the process (this is what caused the "Is uvicorn running?" error visitors saw). Google Cloud Run's free tier goes up to 32GB of configurable memory and 2M free requests/month, so the same container has real headroom instead of none. The Render config (`render.yaml`) is left in the repo as a secondary option, but it's not the recommended path for a link other people will actually open.

---

## 1. Push to GitHub

Vercel deploys from a GitHub repo. If this repo isn't already pushed, do that first.

## 2. Backend — Google Cloud Run

**One-time setup:**
1. Go to [console.cloud.google.com](https://console.cloud.google.com), sign in, create a project (e.g. `kryos-antarctic`).
2. Enable billing on the project (**Billing** in the left menu → link/create a billing account). Google Cloud requires a payment method on file to enable Cloud Run at all, even for free-tier usage — but as long as usage stays within the free monthly allowance (180,000 vCPU-seconds, 360,000 GiB-seconds, 2M requests — a demo link won't come close), you aren't charged.
3. Install the `gcloud` CLI: [cloud.google.com/sdk/docs/install](https://cloud.google.com/sdk/docs/install). After installing, run:
   ```
   gcloud init
   gcloud auth login
   gcloud config set project kryos-antarctic
   gcloud services enable run.googleapis.com cloudbuild.googleapis.com
   ```

**Deploy all three regions** (run from the repo root — `gcloud run deploy --source .` builds the existing `Dockerfile` for you via Cloud Build, no separate image-push step needed):
```
gcloud run deploy kryos-weddell --source . --region us-central1 \
  --memory 2Gi --cpu 2 --min-instances 0 --max-instances 3 \
  --allow-unauthenticated \
  --set-env-vars REGION=weddell

gcloud run deploy kryos-prydz-bay --source . --region us-central1 \
  --memory 2Gi --cpu 2 --min-instances 0 --max-instances 3 \
  --allow-unauthenticated \
  --set-env-vars REGION=prydz_bay

gcloud run deploy kryos-ross-sea --source . --region us-central1 \
  --memory 2Gi --cpu 2 --min-instances 0 --max-instances 3 \
  --allow-unauthenticated \
  --set-env-vars REGION=ross_sea
```
`--memory 2Gi` gives ~5x headroom over the measured 374MB peak (room for concurrent requests too), `--cpu 2` is real compute instead of Render's throttled 0.1, and `--min-instances 0` keeps it inside the free tier (costs nothing while idle — Cloud Run just cold-starts on the next request, same tradeoff as Render but the container won't crash once it's up). `--allow-unauthenticated` is required — without it, Cloud Run rejects every browser request with a 403 before it even reaches the app.

Each command takes a few minutes (Cloud Build compiling the image, real PyTorch install) and prints a **Service URL** at the end, e.g. `https://kryos-weddell-xxxxx-uc.a.run.app`. **Copy all three URLs.**

Cloud Run auto-injects its own `PORT` env var (unlike Render, no manual `PORT=10000` needed — the Dockerfile's `${PORT:-10000}` fallback just goes unused here, which is fine).

Sanity-check each one: open `https://kryos-weddell-xxxxx-uc.a.run.app/api/manifest` in a browser — should return real JSON (`"region": "weddell"`, bounds, etc.).

## 3. Frontend — Vercel

1. Go to [vercel.com](https://vercel.com), sign up/log in (GitHub login again).
2. **Add New → Project**, pick this repo.
3. Vercel needs to know the frontend lives in `dashboard/`, not the repo root:
   - **Root Directory**: `dashboard`
   - **Framework Preset**: Vite (should auto-detect)
   - **Build Command**: `npm run build` (default)
   - **Output Directory**: `dist` (default)
4. **Environment Variables** — add these three, using the real Cloud Run URLs from step 2:
   - `VITE_WEDDELL_API_URL` = `https://kryos-weddell-xxxxx-uc.a.run.app`
   - `VITE_PRYDZ_BAY_API_URL` = `https://kryos-prydz-bay-xxxxx-uc.a.run.app`
   - `VITE_ROSS_SEA_API_URL` = `https://kryos-ross-sea-xxxxx-uc.a.run.app`

   (Vite only inlines `VITE_*` vars at *build* time — if you change one later, you need to redeploy the frontend, not just wait.)
5. Deploy. Vercel gives you a URL like `https://kryos-xyz.vercel.app`.

## 4. Close the loop: tell the backends about the frontend

The backends' CORS policy only allows `localhost` by default (see `src/backend/app.py`) — a deployed frontend on a different origin gets silently blocked by the browser until you set this. For **each** of the three Cloud Run services:
```
gcloud run services update kryos-weddell --region us-central1 \
  --update-env-vars FRONTEND_ORIGIN=https://kryos-xyz.vercel.app
gcloud run services update kryos-prydz-bay --region us-central1 \
  --update-env-vars FRONTEND_ORIGIN=https://kryos-xyz.vercel.app
gcloud run services update kryos-ross-sea --region us-central1 \
  --update-env-vars FRONTEND_ORIGIN=https://kryos-xyz.vercel.app
```
(Replace with your real Vercel URL, no trailing slash. Comma-separate multiple origins if needed.) Each command redeploys that service with the new env var — takes under a minute since it reuses the already-built image.

## 5. Verify

Open the Vercel URL. You should see the splash screen, then the planner, with the region switcher pulling real data from all three Cloud Run services. Try planning a journey in each region — this is the step that actually exercises the memory-heavy path that broke on Render, so don't skip it.

If you get a "failed to load data" screen: check the browser console for a CORS error (means step 4 wasn't done or the URL doesn't match exactly) vs. a network error (means the Cloud Run URL in step 3.4 is wrong or that service isn't up). If planning a journey specifically fails while the map loads fine, check `gcloud run services logs read kryos-weddell --region us-central1` for the real traceback.

## 6. Optional: keep-alive workflow to reduce cold starts

`--min-instances 0` above means Cloud Run scales each service to zero when idle — free, but the *next* request pays a cold start (container boot + Python/torch import, likely 10-30s depending on image size, not the 60-90s Render's crashier free tier produced, and critically it won't crash once running). `.github/workflows/keep-alive.yml` (already committed) pings a URL every 10 minutes to prevent that idle gap:

1. Open `.github/workflows/keep-alive.yml` and replace the three placeholder URLs with your real Cloud Run URLs from step 2.
2. Commit and push (note: this specific workflow file may need adding via GitHub's web UI rather than a normal push, if your local git credentials lack the `workflow` scope — see the file's own history in this repo for why).
3. Optional sanity check: **Actions** tab on GitHub → find "Keep Render backends warm" (name still says Render, harmless — it just curls whatever URLs are in the file) → **Run workflow** to trigger it manually once.

This is a nice-to-have here, not a fix for a real problem the way it was for Render — Cloud Run cold starts are slower than a warm response but they don't crash, so skipping this step just means the first visitor after a quiet period waits longer, not that they see an error.

---

## Known limitations of this deployment, stated plainly

- **The live-forecast weather files go stale.** `deploy_data/<region>/data/raw/<region>/weather/{wind,current}_openmeteo.csv` are a real ~8-day forecast snapshot from whenever you last ran `scripts/export_serving_data.py`. They are *not* refreshed automatically once deployed. For a demo link that needs to stay accurate over time, either re-run the export + redeploy periodically, or set up a scheduled job (out of scope here, real follow-up work) that re-runs `download_weather.py` + re-uploads inside the running container.
- **Three separate backend processes, not one.** This mirrors the local dev setup exactly (see `PROJECT_STATUS.md` section 4) — there's no live per-request region switch server-side.
- **Cloud Run's free tier is real but requires a billing account with a payment method on file.** Usage for a demo link stays well within the free monthly allowance (180,000 vCPU-seconds, 360,000 GiB-seconds, 2M requests), so no charge is expected, but it's not a card-free signup the way some free tiers are — worth knowing going in.
- **`--min-instances 0` still means a cold start for the first visitor after idle time**, just a survivable one instead of Render's crash. For the actual live judging demo, run locally regardless — that's the one moment where "definitely works, zero network dependency" matters most.
