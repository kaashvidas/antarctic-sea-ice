# Kryos backend. One shared image serves ANY region -- which one is
# decided at container start by the REGION env var (see
# src/utils/grid.py), not at build time. This changed from an earlier
# ARG-based per-region build after confirming (Render's own
# render.yaml.json schema) that Render's Blueprint spec has no field
# for passing Docker --build-arg values, so a build-arg-per-service
# design silently can't work there. Since the trimmed deploy_data/
# bundle is tiny (~8MB for all three regions combined, see
# scripts/export_serving_data.py), baking all three in and switching
# at runtime is simpler anyway -- one image, no per-region build step,
# three Render services just set a different REGION env var each.
#
# Build: docker build -t kryos .
# Run:   docker run -e REGION=weddell -p 10000:10000 kryos
FROM python:3.14-slim

WORKDIR /app

COPY requirements-serving.txt .
RUN pip install --no-cache-dir -r requirements-serving.txt

COPY src/ src/

# Merge all three regions' trimmed data into one data/ + outputs/ tree --
# each region's files live under its own region-named subpath (see
# region_path() in src/utils/grid.py) except the small shared iceberg
# feed and AMSR2 fallback tifs, which are identical across all three
# copies, so layering them on top of each other is harmless.
COPY deploy_data/weddell/data/ data/
COPY deploy_data/weddell/outputs/ outputs/
COPY deploy_data/prydz_bay/data/ data/
COPY deploy_data/prydz_bay/outputs/ outputs/
COPY deploy_data/ross_sea/data/ data/
COPY deploy_data/ross_sea/outputs/ outputs/

# REGION is NOT set here -- each Render service supplies its own via
# render.yaml's envVars, so this one image serves whichever region that
# service is configured for.
#
# Port: Render's docker-runtime services do NOT auto-inject PORT the way
# other runtimes do -- confirmed against Render's own docs -- and its
# health checker defaults to port 10000. render.yaml sets PORT=10000
# explicitly for exactly this reason; the ${PORT:-10000} fallback here
# just means a plain local `docker run` with no PORT set still matches
# Render's real default instead of an arbitrary one that only works
# locally.
CMD ["sh", "-c", "uvicorn src.backend.app:app --host 0.0.0.0 --port ${PORT:-10000}"]
