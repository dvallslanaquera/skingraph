#!/bin/sh
set -e

# Build the Qdrant vector index on first start when the volume is empty.
# On Railway this runs once after the volume is attached; on ECS it fires
# on the first task launch (replaces the manual exec approach).
if [ ! -d "/app/data/qdrant/collection" ]; then
  echo "==> First start: building Qdrant vector index (this takes ~60 s)..."
  python scripts/build_index.py
  echo "==> Index build complete."
fi

exec uvicorn src.api.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers 1
