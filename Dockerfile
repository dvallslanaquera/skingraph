# ────────────────────────────────────────────────────────────
# Stage 1 – builder
#
# Resolves all production deps via Poetry and installs them
# into /opt/venv. No torch in the graph: embeddings run on
# ONNX Runtime (fastembed), which keeps both the image and the
# worker's memory footprint small.
# ────────────────────────────────────────────────────────────
FROM python:3.14-slim AS builder

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

# No torch: embeddings run on ONNX Runtime (fastembed), so a plain install of the
# exported requirements is all the venv needs.
RUN /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
 && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt


# ────────────────────────────────────────────────────────────
# Stage 2 – base
#
# Shared runtime layer for both `api` and `ocr-worker`: the venv,
# the pre-baked embedding model, source, scripts, and seed data.
# No EXPOSE / CMD here so the two leaf stages set their own.
# ────────────────────────────────────────────────────────────
FROM python:3.14-slim AS base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    FASTEMBED_CACHE_DIR=/app/.fastembed_cache

# libgomp1 = OpenMP runtime used by ONNX Runtime's CPU execution provider
RUN apt-get update \
 && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

# Pre-download the embedding model's ONNX weights into the image (under
# FASTEMBED_CACHE_DIR) so the first scan never hits HuggingFace (~30-60 s) and the
# app runs offline. The int8 file (~120 MB) keeps the loaded model's RSS to fit
# Railway's default 512 MB container — must match EMBEDDING_ONNX_FILE in
# src/config.py. Kept self-contained (no src/ import) and placed before COPY
# src/ so this download layer survives source-only changes — it mirrors
# src/vectorstore.py:_register_model. Retried: HuggingFace rate-limits in CI.
RUN for attempt in 1 2 3 4 5; do \
        echo "Pre-baking embedding model (attempt $attempt/5)..."; \
        python -c "import os; from fastembed import TextEmbedding; from fastembed.common.model_description import ModelSource, PoolingType; M='intfloat/multilingual-e5-small'; TextEmbedding.add_custom_model(model=M, pooling=PoolingType.MEAN, normalization=True, sources=ModelSource(hf=M), dim=384, model_file='onnx/model_qint8_avx512_vnni.onnx'); TextEmbedding(M, cache_dir=os.environ['FASTEMBED_CACHE_DIR'])" && exit 0; \
        sleep 15; \
    done; \
    echo "Model pre-bake failed after 5 attempts" >&2; exit 1

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
