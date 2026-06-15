#!/bin/sh
set -e

# Railway mounts the persistent volume at /app/data, which shadows the JSON
# reference data baked into the image. Sync it in from /app/seed so the app and
# the index builder can read it. users.db and the qdrant/ index live on the same
# volume and persist across restarts.
mkdir -p /app/data
cp /app/seed/*.json /app/data/

# Restore the Qdrant index onto the volume on first boot. It is pre-built into
# /app/seed/qdrant at image-build time, so this is a fast copy rather than an
# ~8 min CPU embedding that blew past the healthcheck window. Fall back to
# building it live only if the pre-built copy is somehow missing.
if [ ! -f "/app/data/qdrant/meta.json" ]; then
  if [ -d "/app/seed/qdrant" ]; then
    echo "==> First start: restoring pre-built Qdrant index onto the volume..."
    cp -r /app/seed/qdrant /app/data/qdrant
  else
    echo "==> First start: no pre-built index found, building live (slow)..."
    python scripts/build_index.py
  fi
  echo "==> Index ready."
fi

exec uvicorn src.api.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers 1
