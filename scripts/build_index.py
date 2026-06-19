"""Build the Qdrant vector index from the JSON seed data.

    poetry run python scripts/build_index.py

Reads data/registry.json and data/ingredient_master.json, embeds them with the
local e5 model on ONNX Runtime (fastembed), and (re)builds the embedded Qdrant
store at data/qdrant/. Re-run whenever the seed JSON changes.

The JSON files become *seed data*: the runtime retrieval mechanism is Qdrant,
not a per-call JSON scan. The embedded store is single-writer, so don't run this
while the pipeline is running (both open the same on-disk path).
"""
import json
import logging
import os
import sys

# Make `src` importable no matter where this script is launched from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qdrant_client.models import PointStruct  # noqa: E402

from src import vectorstore  # noqa: E402
from src.config import (INGREDIENT_COLLECTION, INGREDIENT_MASTER_PATH,  # noqa: E402
                        PRODUCT_COLLECTION)

logging.basicConfig(level=logging.INFO)

REGISTRY_PATH = "data/registry.json"


def build_products() -> int:
    """One point per registry product; payload carries the curated ingredients."""
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        products = json.load(f)["products"]

    texts = [f"{p['brand']} {p['product_name']}" for p in products]
    vectors = vectorstore.embed_passages(texts)
    points = [
        PointStruct(id=i, vector=vectors[i], payload=products[i])
        for i in range(len(products))
    ]
    vectorstore.rebuild_collection(PRODUCT_COLLECTION, points)
    return len(points)


def build_ingredients() -> int:
    """One point per INCI synonym/form; payload maps back to the canonical INCI."""
    with open(INGREDIENT_MASTER_PATH, "r", encoding="utf-8") as f:
        master = json.load(f)

    forms = []  # (text_form, canonical_inci)
    for inci, synonyms in master.items():
        forms.append((inci, inci))
        for synonym in synonyms:
            forms.append((synonym, inci))

    texts = [form for form, _ in forms]
    vectors = vectorstore.embed_passages(texts)
    points = [
        PointStruct(
            id=i,
            vector=vectors[i],
            payload={"form": forms[i][0], "inci": forms[i][1]},
        )
        for i in range(len(forms))
    ]
    vectorstore.rebuild_collection(INGREDIENT_COLLECTION, points)
    logging.info("(%d INCI keys -> %d lookup forms)", len(master), len(forms))
    return len(points)


def main() -> None:
    n_products = build_products()
    n_ingredients = build_ingredients()
    logging.info(
        "Index build complete: %d products, %d ingredient forms at data/qdrant/",
        n_products,
        n_ingredients,
    )


if __name__ == "__main__":
    main()
