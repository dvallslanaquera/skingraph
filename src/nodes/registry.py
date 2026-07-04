# Product registry lookup via a deterministic JAN/EAN key, then Qdrant
# semantic search.
#
# The JAN tier is checked first: a barcode decoded off the frame (or read off
# the label by the VLM) identifies the product *exactly*, with no dependence on
# how well the brand name was OCR'd. Only when no JAN is available (or it isn't
# in the registry) do we fall back to embedding the scanned
# "{brand} {product_name}" and finding the nearest product in the vector store.
# A hit returns the curated ingredient list from the payload, short-circuiting
# the rest of the pipeline (the normalizer still runs to map those curated
# names to canonical INCI).
import json
import logging

from src.config import PRODUCT_EARLY_THRESHOLD, PRODUCT_MATCH_THRESHOLD, REGISTRY_PATH
from src.state import AgentState
from src.vectorstore import search_product

# {jan_code: product entry} built once from the registry file on first use.
_JAN_INDEX: dict[str, dict] | None = None


def _jan_index() -> dict[str, dict]:
    global _JAN_INDEX
    if _JAN_INDEX is None:
        try:
            with open(REGISTRY_PATH, encoding="utf-8") as f:
                products = json.load(f).get("products", [])
        except (OSError, ValueError):
            logging.warning("Registry file unavailable at %s — JAN tier disabled.", REGISTRY_PATH)
            products = []
        _JAN_INDEX = {p["jan_code"]: p for p in products if p.get("jan_code")}
        logging.info("Registry JAN index: %d barcode key(s).", len(_JAN_INDEX))
    return _JAN_INDEX


def _hit(payload: dict, score: float) -> dict:
    """State update for a registry hit, shared by the JAN and vector tiers."""
    standardized = [
        {"name_raw": name, "name_standardized": name, "source_language": "JP"}
        for name in payload.get("ingredients_jp", [])
    ]
    return {
        "model_used": "database",
        "inference_confidence": score,
        "is_ready_for_logic": True,
        "registry_matched": True,
        "ingredient_source": "registry",
        "standardized_ingredients": standardized,
    }


def _run_registry_match(state: AgentState, threshold: float) -> dict:
    """Match the scanned product against the registry; return the state update.

    Tier 1 — JAN/EAN: a barcode decoded from the frame (state, deterministic)
    or read off the label by the VLM keys the registry exactly. Tier 2 — vector:
    cosine >= ``threshold`` on the embedded brand+name. A miss (or no extraction
    to query with) returns the not-ready flags. Hit vs miss is already encoded
    in the returned dict (``registry_matched`` / the presence of
    ``standardized_ingredients``), so no separate boolean is needed.
    """
    extracted = state["extracted_data"]

    jan = state.get("jan_code") or (extracted.jan_code if extracted else None)
    if jan:
        entry = _jan_index().get(jan)
        if entry:
            logging.info(
                "Registry JAN match (%s): %s - %s",
                jan,
                entry.get("brand"),
                entry.get("product_name"),
            )
            return _hit(entry, 1.0)
        logging.info("JAN %s not in registry — falling back to vector match.", jan)

    if extracted is None:
        return {"is_ready_for_logic": False}

    query = f"{extracted.brand} {extracted.product_name}"
    payload, score = search_product(query)

    if payload and score >= threshold:
        logging.info(
            "Registry match (%.3f cosine): %s - %s",
            score,
            payload.get("brand"),
            payload.get("product_name"),
        )
        return _hit(payload, score)

    best = f"{payload.get('brand')} {payload.get('product_name')}" if payload else "none"
    logging.info("No registry match (best: %s at %.3f cosine)", best, score)
    return {
        "is_ready_for_logic": False,
        "registry_matched": False,
        "ingredient_source": "label",
    }


def registry_lookup_node(state: AgentState) -> dict:
    return _run_registry_match(state, PRODUCT_MATCH_THRESHOLD)


def early_registry_check_node(state: AgentState) -> dict:
    return _run_registry_match(state, PRODUCT_EARLY_THRESHOLD)
