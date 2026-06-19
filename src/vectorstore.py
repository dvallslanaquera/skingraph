# Qdrant-backed vector retrieval for products and ingredients.
#
# Replaces the in-memory rapidfuzz scans with semantic ANN search. Qdrant runs
# in embedded/local mode (an on-disk path, no server) and text is embedded with
# a local multilingual sentence-transformers model, so the whole retrieval layer
# works offline once the model has been downloaded once.
#
# Collections (built by scripts/build_index.py):
#   products    — one point per registry product; the payload carries the curated
#                 ingredient list so a hit returns it directly.
#   ingredients — one point per INCI synonym/form; the payload maps back to the
#                 canonical INCI name for the normalizer's semantic tier.
#
# The embedded store is single-writer: don't run build_index.py while the app
# holds the same on-disk path open.
import logging
import threading
from typing import Any, List, Optional, Tuple

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from src.config import (EMBEDDING_DIM, EMBEDDING_MODEL, INGREDIENT_COLLECTION,
                        PRODUCT_COLLECTION, QDRANT_PATH)

_client: Optional[QdrantClient] = None
_client_lock = threading.Lock()
_model: Any = None
_model_lock = threading.Lock()


def get_client() -> QdrantClient:
    """Lazily open the embedded Qdrant store (one client per process)."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = QdrantClient(path=QDRANT_PATH)
                logging.info("Qdrant store opened at %s", QDRANT_PATH)
    return _client


def get_model():
    """Lazily load the sentence-transformers model (heavy import + weights)."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                import torch
                from sentence_transformers import SentenceTransformer

                # The deploy runs one worker on a single shared vCPU. Extra torch
                # intra-op threads add per-thread memory and contention without
                # speeding up encoding there, so cap to 1 to keep peak RSS down
                # (the model load is the worker's memory high-water mark).
                torch.set_num_threads(1)
                logging.info("Loading embedding model: %s", EMBEDDING_MODEL)
                _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


# multilingual-e5 is trained with asymmetric "query:" / "passage:" prefixes;
# using them improves retrieval quality noticeably.
def embed_query(text: str) -> List[float]:
    vec = get_model().encode(f"query: {text}", normalize_embeddings=True)
    return vec.tolist()


def embed_passages(texts: List[str]) -> List[List[float]]:
    vecs = get_model().encode(
        [f"passage: {t}" for t in texts], normalize_embeddings=True
    )
    return [v.tolist() for v in vecs]


def ensure_collection(name: str) -> None:
    client = get_client()
    if not client.collection_exists(name):
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(
                size=EMBEDDING_DIM, distance=Distance.COSINE
            ),
        )
        logging.info("Created Qdrant collection: %s", name)


def rebuild_collection(name: str, points: List[PointStruct]) -> None:
    """Drop and recreate a collection, then upsert all points (index build)."""
    client = get_client()
    if client.collection_exists(name):
        client.delete_collection(name)
    ensure_collection(name)
    if points:
        client.upsert(collection_name=name, points=points)
    logging.info("Rebuilt collection '%s' with %d point(s).", name, len(points))


def _search_one(collection: str, query: str) -> Tuple[Optional[dict], float]:
    """Return the single best (payload, cosine_score) for a query, or (None, 0)."""
    client = get_client()
    result = client.query_points(
        collection_name=collection,
        query=embed_query(query),
        limit=1,
        with_payload=True,
    )
    points = result.points
    if not points:
        return None, 0.0
    return points[0].payload, float(points[0].score)


def search_product(query: str) -> Tuple[Optional[dict], float]:
    """Best product match for a "{brand} {product_name}" query."""
    return _search_one(PRODUCT_COLLECTION, query)


def search_ingredient(query: str) -> Tuple[Optional[dict], float]:
    """Best ingredient-form match for a raw label ingredient name."""
    return _search_one(INGREDIENT_COLLECTION, query)
