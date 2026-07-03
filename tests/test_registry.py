# Tests for the product-registry lookup nodes.
#
# `search_product` (Qdrant + embedding model) is patched out entirely, so these
# tests exercise the thresholding and payload-shaping logic deterministically
# without opening the vector store.
import pytest

from src.config import (
    PRODUCT_EARLY_THRESHOLD,
    PRODUCT_MATCH_THRESHOLD,
)
from src.nodes import registry
from tests.helpers import make_extraction


@pytest.fixture
def patch_search(monkeypatch):
    """Patch registry.search_product to return a fixed (payload, score).

    Returns a setter so each test picks its own canned result, and records the
    queries the node issued so we can assert on them.
    """
    calls = []

    def set_result(payload, score):
        def fake_search_product(query):
            calls.append(query)
            return payload, score

        monkeypatch.setattr(registry, "search_product", fake_search_product)

    set_result.calls = calls
    return set_result


PAYLOAD = {
    "brand": "Curel",
    "product_name": "Intensive Moisture Cream",
    "ingredients_jp": ["水", "グリセリン", "ワセリン"],
}


def _state():
    return {"extracted_data": make_extraction(brand="Curel", product_name="Cream")}


# --------------------------------------------------------------------------- #
# registry_lookup_node (normal PRODUCT_MATCH_THRESHOLD)
# --------------------------------------------------------------------------- #
def test_lookup_hit_returns_curated_ingredients(patch_search):
    patch_search(PAYLOAD, PRODUCT_MATCH_THRESHOLD)
    result = registry.registry_lookup_node(_state())

    assert result["registry_matched"] is True
    assert result["is_ready_for_logic"] is True
    assert result["model_used"] == "database"
    assert result["ingredient_source"] == "registry"
    assert result["inference_confidence"] == PRODUCT_MATCH_THRESHOLD

    std = result["standardized_ingredients"]
    assert [i["name_raw"] for i in std] == ["水", "グリセリン", "ワセリン"]
    # On a registry hit, raw == standardized (curated list is already canonical).
    assert all(i["name_raw"] == i["name_standardized"] for i in std)
    assert all(i["source_language"] == "JP" for i in std)


def test_lookup_query_is_brand_plus_product(patch_search):
    patch_search(PAYLOAD, 0.99)
    state = {"extracted_data": make_extraction(brand="Curel", product_name="Cream")}
    registry.registry_lookup_node(state)
    assert patch_search.calls == ["Curel Cream"]


def test_lookup_below_threshold_is_a_miss(patch_search):
    patch_search(PAYLOAD, PRODUCT_MATCH_THRESHOLD - 0.01)
    result = registry.registry_lookup_node(_state())

    assert result["registry_matched"] is False
    assert result["is_ready_for_logic"] is False
    assert result["ingredient_source"] == "label"
    assert "standardized_ingredients" not in result


def test_lookup_no_payload_is_a_miss(patch_search):
    patch_search(None, 0.0)
    result = registry.registry_lookup_node(_state())
    assert result["registry_matched"] is False
    assert result["ingredient_source"] == "label"


def test_lookup_without_extraction_short_circuits(patch_search):
    patch_search(PAYLOAD, 0.99)
    result = registry.registry_lookup_node({"extracted_data": None})
    # Early return before any search; only the not-ready flag is set.
    assert result == {"is_ready_for_logic": False}
    assert patch_search.calls == []


# --------------------------------------------------------------------------- #
# early_registry_check_node (stricter PRODUCT_EARLY_THRESHOLD)
# --------------------------------------------------------------------------- #
def test_early_check_uses_stricter_threshold(patch_search):
    # A score between the two thresholds: a miss for the early check...
    between = (PRODUCT_MATCH_THRESHOLD + PRODUCT_EARLY_THRESHOLD) / 2
    patch_search(PAYLOAD, between)
    assert registry.early_registry_check_node(_state())["registry_matched"] is False


def test_early_check_hit_at_high_confidence(patch_search):
    patch_search(PAYLOAD, PRODUCT_EARLY_THRESHOLD)
    result = registry.early_registry_check_node(_state())
    assert result["registry_matched"] is True
    assert result["is_ready_for_logic"] is True


def test_same_score_differs_between_early_and_normal(patch_search):
    # The exact same vector score is a normal hit but an early miss.
    score = (PRODUCT_MATCH_THRESHOLD + PRODUCT_EARLY_THRESHOLD) / 2
    patch_search(PAYLOAD, score)
    assert registry.registry_lookup_node(_state())["registry_matched"] is True
    assert registry.early_registry_check_node(_state())["registry_matched"] is False
