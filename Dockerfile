# Kryos backend, one image per region. Build with:
#   docker build --build-arg REGION=weddell -t kryos-weddell .
#   docker build --build-arg REGION=prydz_bay -t kryos-prydz-bay .
#   docker build --build-arg REGION=ross_sea -t kryos-ross-sea .
#
# Before building, run scripts/export_serving_data.py for that region --
# this Dockerfile copies the TRIMMED deploy_data/<region>/ bundle it
# produces (a few MB), not the full local data/ tree (multiple hundred
# MB per region, mostly training-only history this image never reads).
FROM python:3.14-slim

WORKDIR /app

COPY requirements-serving.txt .
RUN pip install --no-cache-dir -r requirements-serving.txt

ARG REGION=weddell
ENV REGION=${REGION}

COPY src/ src/
COPY deploy_data/${REGION}/data/ data/
COPY deploy_data/${REGION}/outputs/ outputs/

# Render/Railway inject PORT at runtime; default 8000 for local
# `docker run` without one set.
CMD ["sh", "-c", "uvicorn src.backend.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
