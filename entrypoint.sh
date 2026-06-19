#!/bin/sh
set -e

# Railway mounts the persistent volume at /app/data, which shadows the JSON
# reference data baked into the image. Sync it in from /app/seed so the app and
# the index builder can read it. users.db and the qdrant/ index live on the same
# volume and persist across restarts.
mkdir -p /app/data
cp /app/seed/*.json /app/data/

# Restore the Qdrant index onto the volume from the pre-built seed. The index is
# derived from the seed JSON + the embedding model, so it must match the image
# that built it; we refresh it on every boot (a fast copy of a small, read-only
# index) so a stale index from an earlier build or embedding model can't linger
# on the volume. users.db on the same volume is user data and is left untouched.
# Fall back to a live build only if the image ships no pre-built index.
if [ -d "/app/seed/qdrant" ]; then
  echo "==> Restoring pre-built Qdrant index onto the volume..."
  rm -rf /app/data/qdrant
  cp -r /app/seed/qdrant /app/data/qdrant
elif [ ! -f "/app/data/qdrant/meta.json" ]; then
  echo "==> No pre-built index found, building live (slow)..."
  python scripts/build_index.py
fi
echo "==> Index ready."

exec uvicorn src.api.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers 1
