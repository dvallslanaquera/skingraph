# ────────────────────────────────────────────────────────────
# Stage 1 – builder
#
# Resolves all production deps via Poetry and installs them
# into /opt/venv.  CPU-only torch is installed first so pip
# never fetches a CUDA wheel; sentence-transformers picks it
# up and the final image stays ~1 GB lighter.
# ────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update \
 && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends gcc \
 && rm -rf /var/lib/apt/lists/*

# Poetry 2.x removed `export` from core — it now lives in the separate
# poetry-plugin-export package, which pip does NOT pull in automatically.
# Install both so `poetry export` below is available.
RUN pip install --no-cache-dir poetry==2.4.0 poetry-plugin-export

ENV POETRY_NO_INTERACTION=1

COPY pyproject.toml poetry.lock ./

RUN poetry export --without dev --without-hashes \
        -f requirements.txt -o requirements.txt

RUN python -m venv /opt/venv

# Install torch CPU wheel before the rest of the requirements.
# pip treats the installed +cpu local tag as satisfying the
# bare version constraint in requirements.txt and skips re-downloading.
RUN /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
 && /opt/venv/bin/pip install --no-cache-dir \
        torch \
        --index-url https://download.pytorch.org/whl/cpu \
 && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt


# ────────────────────────────────────────────────────────────
# Stage 2 – base
#
# Shared runtime layer for both `api` and `ocr-worker`: the venv,
# the pre-baked embedding model, source, scripts, and seed data.
# No EXPOSE / CMD here so the two leaf stages set their own.
# ────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# libgomp1 = OpenMP runtime required by torch even in CPU mode
RUN apt-get update \
 && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

# Pre-download the sentence-transformers model into the image layer.
# Without this, cold starts hit HuggingFace at first request (~30-60 s delay).
# Placed before COPY src/ so Docker cache survives source-only changes.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-small')"

# The index builder (scripts/build_index.py) only imports src/vectorstore.py and
# src/config.py. Copy just those two files before the build step so that changes
# to the rest of src/ don't bust the index cache and trigger the ~8 min re-embed.
COPY src/vectorstore.py src/config.py ./src/
COPY scripts/ ./scripts/
# Static JSON reference data is baked into /app/seed, NOT /app/data: Railway
# mounts a persistent volume at /app/data that would otherwise shadow these
# files. entrypoint.sh syncs them into /app/data on start. (On AWS only the
# /app/data/qdrant subdir is volume-mounted, so the same sync is a no-op over
# identical files.)
COPY data/*.json ./seed/
COPY entrypoint.sh ./entrypoint.sh
RUN sed -i 's/\r//' entrypoint.sh && chmod +x entrypoint.sh

# Pre-build the Qdrant index at image-build time and stage it under /app/seed.
# Embedding ~500 ingredient forms on Railway's shared CPU at boot took ~8 min
# and blew past the healthcheck window; doing it here (cached, no healthcheck)
# makes first boot a fast file-copy instead. build_index.py reads data/*.json
# and writes data/qdrant, so stage the JSON into data/ for the build, move the
# result into seed/, then drop the temp data/ (the volume provides it at runtime).
# Cache key: scripts/build_index.py + src/vectorstore.py + data/*.json.
RUN mkdir -p data \
 && cp seed/*.json data/ \
 && python scripts/build_index.py \
 && mv data/qdrant seed/qdrant \
 && rm -rf data

# src/ comes last: source-only changes invalidate only this layer and below,
# leaving the slow model-download and index-build layers fully cached.
COPY src/ ./src/


# ────────────────────────────────────────────────────────────
# Stage 3 – ocr-worker   (optional, profile: ocr)
#
# Adds YomiToku + OpenCV on top of the base layer for the
# standalone OCR benchmark in scripts/run_ocr.py.
# This stage is NOT in the production deploy path — it pulls in
# torchvision, which is intentionally absent from `api`.
#
# Build:  docker compose --profile ocr build ocr-worker
# Run:    docker compose --profile ocr run ocr-worker \
#           python scripts/run_ocr.py data/golden_set/ --device cpu
# ────────────────────────────────────────────────────────────
FROM base AS ocr-worker

# Additional system libs required by OpenCV on slim
RUN apt-get update \
 && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgl1 \
 && rm -rf /var/lib/apt/lists/*

# YomiToku downloads its model weights on first run (~hundreds of MB);
# bind-mount a cache dir to avoid re-downloading across container restarts.
RUN pip install --no-cache-dir opencv-python-headless yomitoku

CMD ["python", "scripts/run_ocr.py", "--help"]


# ────────────────────────────────────────────────────────────
# Stage 4 – api   (default production target — MUST stay last)
#
# Runs the FastAPI / LangGraph service. No YomiToku, no OpenCV,
# no torchvision. Because it is the final stage, a plain
# `docker build` (and Railway, which ignores build-target config)
# builds THIS image by default — not the heavier ocr-worker.
#
# Build:  docker build --target api -t skincare-coach-api .
# ────────────────────────────────────────────────────────────
FROM base AS api

EXPOSE 8000

# PORT is injected by Railway; defaults to 8000 for ECS and local Docker.
# On first start the entrypoint builds the Qdrant index if the volume is empty.
CMD ["/app/entrypoint.sh"]
