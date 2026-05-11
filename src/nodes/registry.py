from rapidfuzz import process, fuzz
import json
import logging
from src.state import AgentState
from src.config import REGISTRY_MATCH_THRESHOLD, REGISTRY_EARLY_THRESHOLD


def _run_registry_match(state: AgentState, threshold: float) -> tuple[bool, dict]:
    extracted = state["extracted_data"]
    if extracted is None:
        return False, {"is_ready_for_logic": False}

    with open("data/registry.json", "r", encoding="utf-8") as f:
        registry = json.load(f)

    query = f"{extracted.brand} {extracted.product_name}"
    choices = [f"{item['brand']} {item['product_name']}" for item in registry["products"]]
    best_match, score, index = process.extractOne(query, choices, scorer=fuzz.WRatio)

    if score >= threshold:
        logging.info("Registry match (%.1f%%): %s", score, best_match)
        verified = registry["products"][index]
        standardized = [
            {"name_raw": name, "name_standardized": name, "source_language": "JP"}
            for name in verified["ingredients_jp"]
        ]
        return True, {
            "model_used": "database",
            "inference_confidence": score / 100,
            "is_ready_for_logic": True,
            "standardized_ingredients": standardized,
        }

    logging.info("No registry match (best: %s at %.1f%%)", best_match, score)
    return False, {"is_ready_for_logic": False}


def registry_lookup_node(state: AgentState) -> dict:
    _, result = _run_registry_match(state, REGISTRY_MATCH_THRESHOLD)
    return result


def early_registry_check_node(state: AgentState) -> dict:
    _, result = _run_registry_match(state, REGISTRY_EARLY_THRESHOLD)
    return result
