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
def mock_search_llm(monkeypatch):
    def install(content):
        resp = MagicMock(content=content, response_metadata={})
        chat = MagicMock()
        chat.invoke = MagicMock(return_value=resp)
        monkeypatch.setattr(websearch, "ChatGoogleGenerativeAI", MagicMock(return_value=chat))

    return install


def test_web_search_populates_ingredients_when_enough_found(mock_search_llm):
    lines = [f"Ingredient {i}" for i in range(MIN_INGREDIENTS_FOR_AUDIT)]
    mock_search_llm("\n".join(lines) + "\nSOURCE: https://brand.example/p")

    state = {"extracted_data": make_extraction(brand="Brand", product_name="P")}
    result = websearch.web_search_node(state)

    assert result["ingredient_source"] == "web"
    assert "https://brand.example/p" in result["web_sources"]
    assert len(result["extracted_data"].ingredients) == MIN_INGREDIENTS_FOR_AUDIT


def test_web_search_leaves_ingredients_unchanged_when_too_few(mock_search_llm):
    mock_search_llm("Water\nGlycerin\nSOURCE: https://x.example")

    state = {"extracted_data": make_extraction(brand="Brand", product_name="P")}
    result = websearch.web_search_node(state)

    # Too few names: don't overwrite extracted_data, so the router sees < MIN.
    assert "extracted_data" not in result
    assert result["ingredient_source"] == "web"
