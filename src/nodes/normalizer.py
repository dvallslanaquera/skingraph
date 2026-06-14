# Linguistic normalizer: maps raw ingredient names to canonical INCI keys.
# Runs after the registry step on the supported-language path. It enriches the
# verified registry list (registry hit) or normalizes the raw VLM extraction
# (registry miss), so downstream logic always sees canonical INCI names.
import json
import logging
import unicodedata
from typing import Dict, List, Optional, Tuple

from rapidfuzz import fuzz, process

from src.state import AgentState
from src.config import INGREDIENT_MASTER_PATH, NORMALIZER_FUZZY_THRESHOLD

# Built once on first call, then reused across invocations.
_INDEX_CACHE: Optional[Dict[str, str]] = None


def _normalize(text: str) -> str:
    """NFKC-fold, lowercase, and strip all whitespace for robust matching.

    NFKC collapses full-width kana/digits to half-width (２Ｋ -> 2k), so the
    ledger's half-width synonyms match labels printed in full-width forms.
    """
    return "".join(unicodedata.normalize("NFKC", text).lower().split())


def _load_index() -> Dict[str, str]:
    """Build an inverted {normalized synonym -> canonical INCI} lookup table."""
    global _INDEX_CACHE
    if _INDEX_CACHE is None:
        with open(INGREDIENT_MASTER_PATH, "r", encoding="utf-8") as f:
            master = json.load(f)
        index: Dict[str, str] = {}
        for inci, synonyms in master.items():
            index[_normalize(inci)] = inci
            for synonym in synonyms:
                index[_normalize(synonym)] = inci
        _INDEX_CACHE = index
        logging.info(
            "Normalizer ledger loaded: %d INCI keys, %d lookup forms.",
            len(master),
            len(index),
        )
    return _INDEX_CACHE


def _resolve(raw_name: str, index: Dict[str, str]) -> Tuple[Optional[str], str]:
    """Resolve one raw name to (inci_or_None, method)."""
    key = _normalize(raw_name)
    if not key:
        return None, "empty"
    if key in index:
        return index[key], "exact"
    match = process.extractOne(key, index.keys(), scorer=fuzz.WRatio)
    if match and match[1] >= NORMALIZER_FUZZY_THRESHOLD:
        return index[match[0]], "fuzzy"
    return None, "unmatched"


def _select_input(state: AgentState) -> List[Tuple[str, Optional[bool], str]]:
    """Pick the ingredient source: verified registry list, else VLM extraction.

    Returns tuples of (name_raw, is_active, source_language).
    """
    registry_list = state.get("standardized_ingredients")
    if registry_list:
        return [
            (item["name_raw"], item.get("is_active"), item.get("source_language", "JP"))
            for item in registry_list
        ]
    extracted = state.get("extracted_data")
    if extracted:
        return [
            (ing.name_raw, ing.is_active, ing.source_language)
            for ing in extracted.ingredients
        ]
    return []


def normalizer_node(state: AgentState) -> dict:
    index = _load_index()
    raw_items = _select_input(state)

    normalized: List[dict] = []
    unmatched: List[str] = []
    exact = fuzzy = 0
    for name_raw, is_active, lang in raw_items:
        inci, method = _resolve(name_raw, index)
        if method == "exact":
            exact += 1
        elif method == "fuzzy":
            fuzzy += 1
        elif method == "unmatched":
            unmatched.append(name_raw)
        normalized.append(
            {
                "name_raw": name_raw,
                "name_standardized": inci,
                "is_active": is_active,
                "source_language": lang,
            }
        )

    total = len(normalized)
    matched = exact + fuzzy
    logging.info(
        "Normalizer: %d/%d mapped to INCI (%d exact, %d fuzzy, %d unmatched).",
        matched,
        total,
        exact,
        fuzzy,
        len(unmatched),
    )
    if unmatched:
        logging.info("Unmatched ingredients: %s", ", ".join(unmatched))

    return {
        "standardized_ingredients": normalized,
        "unmatched_ingredients": unmatched,
        "is_ready_for_logic": True,
    }
