# Tests for the ingredient normalizer.
#
# Tier 1 (exact normalized-dict lookup) is exercised against a small controlled
# index injected into the module cache; tier 2 (semantic vector search) is
# exercised with `search_ingredient` patched out. No Qdrant or model is loaded.
import pytest

from src.config import INGREDIENT_MATCH_THRESHOLD
from src.nodes import normalizer

from tests.helpers import make_extraction, std_ingredients


# --------------------------------------------------------------------------- #
# _normalize
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Glycerin", "glycerin"),
        ("  グリセリン  ", "グリセリン"),
        ("BG", "bg"),
        ("ＢＧ", "bg"),  # full-width ASCII folds to half-width via NFKC
        ("Butylene Glycol", "butyleneglycol"),  # all whitespace stripped
        ("", ""),
    ],
)
def test_normalize(raw, expected):
    assert normalizer._normalize(raw) == expected


# --------------------------------------------------------------------------- #
# index + search fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def fake_index(monkeypatch):
    """Inject a tiny, controlled INCI index (keys already NFKC-normalized)."""
    raw_map = {
        "グリセリン": "Glycerin",
        "glycerin": "Glycerin",
        "BG": "Butylene Glycol",
        "Water": "Water",
    }
    index = {normalizer._normalize(k): v for k, v in raw_map.items()}
    monkeypatch.setattr(normalizer, "_INDEX_CACHE", index)
    return index


@pytest.fixture
def patch_vector(monkeypatch):
    """Patch the tier-2 semantic search with a fixed (payload, score)."""

    def set_result(payload, score):
        monkeypatch.setattr(
            normalizer, "search_ingredient", lambda name: (payload, score)
        )

    return set_result


def _no_vector(monkeypatch):
    """Default: tier-2 returns nothing, so only the exact index can match."""
    monkeypatch.setattr(normalizer, "search_ingredient", lambda name: (None, 0.0))


# --------------------------------------------------------------------------- #
# _resolve
# --------------------------------------------------------------------------- #
def test_resolve_exact_hit(fake_index, monkeypatch):
    _no_vector(monkeypatch)
    assert normalizer._resolve("グリセリン", fake_index) == ("Glycerin", "exact")


def test_resolve_exact_is_case_and_width_insensitive(fake_index, monkeypatch):
    _no_vector(monkeypatch)
    assert normalizer._resolve("GLYCERIN", fake_index) == ("Glycerin", "exact")
    assert normalizer._resolve("ＢＧ", fake_index) == ("Butylene Glycol", "exact")


def test_resolve_empty_name(fake_index):
    assert normalizer._resolve("   ", fake_index) == (None, "empty")


def test_resolve_vector_hit_above_threshold(fake_index, patch_vector):
    patch_vector({"inci": "Niacinamide"}, INGREDIENT_MATCH_THRESHOLD)
    assert normalizer._resolve("ナイアシンアミド", fake_index) == ("Niacinamide", "vector")


def test_resolve_vector_below_threshold_is_unmatched(fake_index, patch_vector):
    patch_vector({"inci": "Niacinamide"}, INGREDIENT_MATCH_THRESHOLD - 0.01)
    assert normalizer._resolve("???", fake_index) == (None, "unmatched")


def test_resolve_no_vector_payload_is_unmatched(fake_index, patch_vector):
    patch_vector(None, 0.0)
    assert normalizer._resolve("xyzzy", fake_index) == (None, "unmatched")


# --------------------------------------------------------------------------- #
# _select_input — source precedence
# --------------------------------------------------------------------------- #
def test_select_input_prefers_registry_list_over_extraction():
    state = {
        "standardized_ingredients": std_ingredients(("水", "Water")),
        "extracted_data": make_extraction(3),
    }
    selected = normalizer._select_input(state)
    assert [name for name, _, _ in selected] == ["水"]


def test_select_input_falls_back_to_extraction():
    state = {"extracted_data": make_extraction(
        ingredients=None,
        n_ingredients=2,
    )}
    selected = normalizer._select_input(state)
    assert len(selected) == 2


def test_select_input_empty_when_nothing_available():
    assert normalizer._select_input({}) == []


# --------------------------------------------------------------------------- #
# normalizer_node — end to end over the two tiers
# --------------------------------------------------------------------------- #
def test_node_maps_exact_and_collects_unmatched(fake_index, patch_vector):
    patch_vector(None, 0.0)  # nothing resolves via tier 2
    from src.state import Ingredient

    state = {
        "extracted_data": make_extraction(
            ingredients=[
                Ingredient(name_raw="グリセリン"),
                Ingredient(name_raw="未知の成分"),  # unknown → unmatched
            ]
        )
    }
    result = normalizer.normalizer_node(state)

    std = result["standardized_ingredients"]
    assert std[0]["name_standardized"] == "Glycerin"
    assert std[1]["name_standardized"] is None
    assert result["unmatched_ingredients"] == ["未知の成分"]
    assert result["is_ready_for_logic"] is True


def test_node_uses_vector_tier_when_exact_misses(fake_index, patch_vector):
    patch_vector({"inci": "Niacinamide"}, 0.95)
    from src.state import Ingredient

    state = {"extracted_data": make_extraction(
        ingredients=[Ingredient(name_raw="ナイアシンアミド")]
    )}
    result = normalizer.normalizer_node(state)
    assert result["standardized_ingredients"][0]["name_standardized"] == "Niacinamide"
    assert result["unmatched_ingredients"] == []


def test_node_preserves_is_active_and_language(fake_index, patch_vector):
    patch_vector(None, 0.0)
    from src.state import Ingredient

    # Glycerin is not a function-taxonomy marker, so an incoming is_active=True is
    # carried through untouched (the marker rule only promotes, never clears).
    state = {"extracted_data": make_extraction(
        ingredients=[Ingredient(name_raw="グリセリン", is_active=True, source_language="EN")]
    )}
    item = normalizer.normalizer_node(state)["standardized_ingredients"][0]
    assert item["is_active"] is True
    assert item["source_language"] == "EN"


def test_node_flags_active_marker_ingredient(fake_index, patch_vector):
    # Niacinamide is a marker in data/function_groups.json, so even when the
    # source left is_active unset, the normalizer promotes it to True.
    patch_vector({"inci": "Niacinamide"}, 0.95)
    from src.state import Ingredient

    state = {"extracted_data": make_extraction(
        ingredients=[Ingredient(name_raw="ナイアシンアミド")]
    )}
    item = normalizer.normalizer_node(state)["standardized_ingredients"][0]
    assert item["name_standardized"] == "Niacinamide"
    assert item["is_active"] is True


def test_node_leaves_non_marker_is_active_unset(fake_index, patch_vector):
    # Water resolves but is not an active marker → is_active stays None.
    patch_vector(None, 0.0)
    from src.state import Ingredient

    state = {"extracted_data": make_extraction(
        ingredients=[Ingredient(name_raw="Water")]
    )}
    item = normalizer.normalizer_node(state)["standardized_ingredients"][0]
    assert item["name_standardized"] == "Water"
    assert item["is_active"] is None


def test_node_empty_ingredient_is_neither_matched_nor_unmatched(fake_index, patch_vector):
    patch_vector(None, 0.0)
    from src.state import Ingredient

    state = {"extracted_data": make_extraction(
        ingredients=[Ingredient(name_raw="   ")]
    )}
    result = normalizer.normalizer_node(state)
    assert result["standardized_ingredients"][0]["name_standardized"] is None
    # An empty/whitespace name is not surfaced as an unmatched ingredient.
    assert result["unmatched_ingredients"] == []
