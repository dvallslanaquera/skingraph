#!/bin/sh
set -e

# Railway mounts the persistent volume at /app/data, which shadows the JSON
# reference data baked into the image. Sync it in from /app/seed so the app and
# the index builder can read it. users.db and the qdrant/ index live on the same
# volume and persist across restarts.
mkdir -p /app/data
cp /app/seed/*.json /app/data/

# Build the Qdrant vector index on first start, when the volume has no index yet.
# On Railway this runs once after the volume is attached; on ECS it fires on the
# first task launch (replaces the manual exec approach).
if [ ! -f "/app/data/qdrant/meta.json" ]; then
  echo "==> First start: building Qdrant vector index (this takes ~60 s)..."
  python scripts/build_index.py
  echo "==> Index build complete."
fi

exec uvicorn src.api.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers 1
