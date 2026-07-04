# Tests for the web-search fallback nodes.
#
# The deterministic parsers (`_parse_ingredients`, `_text_of`,
# `_grounding_sources`) and the graceful-exit nodes need no mocking; the one
# node that calls Gemini (`web_search_node`) is exercised with the LLM patched.
from unittest.mock import MagicMock

import pytest

from src.config import MIN_INGREDIENTS_FOR_AUDIT
from src.nodes import websearch
from tests.helpers import make_extraction


# --------------------------------------------------------------------------- #
# _parse_ingredients
# --------------------------------------------------------------------------- #
def test_parse_strips_bullets_and_numbering():
    text = "1. Water\n・グリセリン\n- BG\n* Niacinamide"
    names, sources = websearch._parse_ingredients(text)
    assert names == ["Water", "グリセリン", "BG", "Niacinamide"]
    assert sources == []


def test_parse_captures_source_line():
    text = "Water\nGlycerin\nSOURCE: https://example.com/product"
    names, sources = websearch._parse_ingredients(text)
    assert names == ["Water", "Glycerin"]
    assert sources == ["https://example.com/product"]


def test_parse_not_found_returns_no_ingredients():
    assert websearch._parse_ingredients("NOT_FOUND") == ([], [])


def test_parse_skips_prose_lines():
    long_prose = "This is a long sentence of commentary that is not an ingredient name at all"
    japanese_prose = "これは成分ではありません。"
    text = f"Water\n{long_prose}\n{japanese_prose}\nGlycerin"
    names, _ = websearch._parse_ingredients(text)
    assert names == ["Water", "Glycerin"]


# --------------------------------------------------------------------------- #
# _text_of
# --------------------------------------------------------------------------- #
def test_text_of_plain_string_content():
    msg = MagicMock(content="hello")
    assert websearch._text_of(msg) == "hello"


def test_text_of_list_of_blocks():
    msg = MagicMock(content=[{"text": "a"}, {"text": "b"}, "c"])
    assert websearch._text_of(msg) == "a\nb\nc"


# --------------------------------------------------------------------------- #
# _grounding_sources
# --------------------------------------------------------------------------- #
def test_grounding_sources_extracts_uris():
    resp = MagicMock(
        response_metadata={
            "grounding_metadata": {
                "grounding_chunks": [
                    {"web": {"uri": "https://a.com"}},
                    {"web": {"uri": "https://b.com"}},
                ]
            }
        }
    )
    assert websearch._grounding_sources(resp) == ["https://a.com", "https://b.com"]


def test_grounding_sources_tolerates_missing_metadata():
    assert websearch._grounding_sources(MagicMock(response_metadata={})) == []


# --------------------------------------------------------------------------- #
# graceful-exit nodes (no LLM)
# --------------------------------------------------------------------------- #
def test_confirm_identity_node_includes_guess_and_stops():
    state = {"extracted_data": make_extraction(brand="Curel", product_name="Cream")}
    result = websearch.confirm_identity_node(state)
    assert result["is_ready_for_logic"] is False
    # The guess is embedded in both language variants.
    assert "Curel" in result["notice"].en and "Cream" in result["notice"].en
    assert "Curel" in result["notice"].ja


def test_search_failed_node_includes_name_and_stops():
    state = {"extracted_data": make_extraction(brand="Curel", product_name="Cream")}
    result = websearch.search_failed_node(state)
    assert result["is_ready_for_logic"] is False
    assert "Curel" in result["notice"].en
    assert "Curel" in result["notice"].ja


# --------------------------------------------------------------------------- #
# web_search_node (Gemini mocked)
# --------------------------------------------------------------------------- #
@pytest.fixture
def mock_search_llm(monkeypatch, tmp_path):
    """Patch the grounded call and the structured second pass; isolate the cache.

    ``install(content, parsed=...)`` wires the grounded chat to return
    ``content`` and the structured pass to return ``parsed`` (None simulates a
    parse failure → deterministic line-parser fallback). Returns the chat mock.
    """
    monkeypatch.setattr(websearch.config, "WEB_CACHE_PATH", str(tmp_path / "cache.json"))
    monkeypatch.setattr(websearch, "_CACHE", None)

    def install(content, parsed=None):
        resp = MagicMock(content=content, response_metadata={})
        chat = MagicMock()
        chat.invoke = MagicMock(return_value=resp)
        structured = MagicMock()
        structured.invoke = MagicMock(return_value=parsed)
        chat.with_structured_output.return_value = structured
        monkeypatch.setattr(websearch, "ChatGoogleGenerativeAI", MagicMock(return_value=chat))
        return chat

    return install


def _names(n):
    return [f"Ingredient {i}" for i in range(n)]


def test_web_search_adopts_structured_parse_when_identity_matches(mock_search_llm):
    parsed = websearch.WebIngredientList(
        found=True,
        brand="Brand",
        product_name="P",
        ingredients=_names(MIN_INGREDIENTS_FOR_AUDIT),
        source_url="https://brand.example/p",
    )
    mock_search_llm("whatever grounded text", parsed=parsed)

    state = {"extracted_data": make_extraction(brand="Brand", product_name="P")}
    result = websearch.web_search_node(state)

    assert result["ingredient_source"] == "web"
    assert "https://brand.example/p" in result["web_sources"]
    assert len(result["extracted_data"].ingredients) == MIN_INGREDIENTS_FOR_AUDIT
    # ASCII names → EN, not the old hardcoded JP.
    assert result["extracted_data"].ingredients[0].source_language == "EN"


def test_web_search_rejects_identity_mismatch(mock_search_llm):
    # The search found *a* list, but for a different product — never adopt it.
    parsed = websearch.WebIngredientList(
        found=True,
        brand="Totally Different",
        product_name="Sunscreen SPF50",
        ingredients=_names(MIN_INGREDIENTS_FOR_AUDIT),
        source_url="https://other.example",
    )
    mock_search_llm("grounded text", parsed=parsed)

    state = {
        "extracted_data": make_extraction(brand="Hada Labo", product_name="Gokujyun Lotion")
    }
    result = websearch.web_search_node(state)

    assert result["web_identity_mismatch"] is True
    assert "extracted_data" not in result


def test_web_search_falls_back_to_line_parser(mock_search_llm):
    # Structured pass fails (parsed=None) → the deterministic parser still works.
    lines = _names(MIN_INGREDIENTS_FOR_AUDIT)
    mock_search_llm("\n".join(lines) + "\nSOURCE: https://brand.example/p", parsed=None)

    state = {"extracted_data": make_extraction(brand="Brand", product_name="P")}
    result = websearch.web_search_node(state)

    assert result["ingredient_source"] == "web"
    assert "https://brand.example/p" in result["web_sources"]
    assert len(result["extracted_data"].ingredients) == MIN_INGREDIENTS_FOR_AUDIT


def test_web_search_leaves_ingredients_unchanged_when_too_few(mock_search_llm):
    mock_search_llm("Water\nGlycerin\nSOURCE: https://x.example", parsed=None)

    state = {"extracted_data": make_extraction(brand="Brand", product_name="P")}
    result = websearch.web_search_node(state)

    # Too few names: don't overwrite extracted_data, so the router sees < MIN.
    assert "extracted_data" not in result
    assert result["ingredient_source"] == "web"


def test_web_search_caches_successful_results(mock_search_llm):
    parsed = websearch.WebIngredientList(
        found=True,
        brand="Brand",
        product_name="P",
        ingredients=_names(MIN_INGREDIENTS_FOR_AUDIT),
        source_url="https://brand.example/p",
    )
    chat = mock_search_llm("grounded text", parsed=parsed)

    state = {"extracted_data": make_extraction(brand="Brand", product_name="P")}
    first = websearch.web_search_node(state)
    second = websearch.web_search_node(state)

    # The grounded search ran once; the repeat scan was served from the cache.
    assert chat.invoke.call_count == 1
    assert [i.name_raw for i in second["extracted_data"].ingredients] == [
        i.name_raw for i in first["extracted_data"].ingredients
    ]


# --------------------------------------------------------------------------- #
# helpers: identity match / language inference / source ranking
# --------------------------------------------------------------------------- #
def test_identity_match_none_without_found_identity():
    assert websearch._identity_match("Brand P", "") is None


def test_identity_match_scores_similar_names_high():
    score = websearch._identity_match("Curel Intensive Moisture Cream", "Curél moisture cream")
    assert score is not None and score >= 70


def test_infer_language():
    assert websearch._infer_language(["Water", "Glycerin"]) == "EN"
    assert websearch._infer_language(["水", "グリセリン"]) == "JP"
    assert websearch._infer_language(["정제수"]) == "KO"


def test_rank_sources_puts_trusted_domains_first():
    ranked = websearch._rank_sources(
        ["https://randomblog.example/post", "https://incidecoder.com/products/x"]
    )
    assert ranked[0] == "https://incidecoder.com/products/x"


def test_parse_ingredients_skips_matched_line():
    text = "MATCHED: Brand — P\nWater\nGlycerin\nSOURCE: https://x.example"
    names, sources = websearch._parse_ingredients(text)
    assert names == ["Water", "Glycerin"]
    assert sources == ["https://x.example"]


def test_confirm_identity_uses_mismatch_copy_after_web_mismatch():
    state = {
        "extracted_data": make_extraction(brand="Curel", product_name="Cream"),
        "web_identity_mismatch": True,
    }
    result = websearch.confirm_identity_node(state)
    assert result["is_ready_for_logic"] is False
    assert "different product" in result["notice"].en
    assert "Curel" in result["notice"].en
