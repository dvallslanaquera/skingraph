# Product registry lookup via Qdrant semantic search.
#
# Embeds the scanned "{brand} {product_name}" and finds the nearest product in
# the vector store. A hit returns the curated ingredient list from the payload,
# short-circuiting the rest of the pipeline (the normalizer still runs to map
# those curated names to canonical INCI).
import logging

from src.config import PRODUCT_EARLY_THRESHOLD, PRODUCT_MATCH_THRESHOLD
from src.state import AgentState
from src.vectorstore import search_product


def _run_registry_match(state: AgentState, threshold: float) -> dict:
    """Match the scanned product against the registry; return the state update.

    A hit (cosine >= ``threshold``) returns the curated ingredient list; a miss
    (or no extraction to query with) returns the not-ready flags. Hit vs miss is
    already encoded in the returned dict (``registry_matched`` / the presence of
    ``standardized_ingredients``), so no separate boolean is needed.
    """
    extracted = state["extracted_data"]
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

    best = (
        f"{payload.get('brand')} {payload.get('product_name')}"
        if payload
        else "none"
    )
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
