# Deterministic tests for the graph's routing functions and inline nodes.
#
# These are pure functions over AgentState — no Gemini, no vector store — so we
# assert their branch decisions exactly against the configured thresholds.
import pytest

from src import graph
from src.config import (
    FLASH_ACCEPT_THRESHOLD,
    FLASH_ESCALATE_THRESHOLD,
    IDENTITY_CONFIDENCE_THRESHOLD,
    MAX_CORRECTIONS,
    MIN_INGREDIENTS_FOR_AUDIT,
)

from tests.helpers import make_extraction


# --------------------------------------------------------------------------- #
# side_router
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "image_type, expected",
    [
        ("front", "front"),
        ("back", "back"),
        (None, "back"),  # unknown side defaults to the back/scan path
    ],
)
def test_side_router(image_type, expected):
    assert graph.side_router({"image_type": image_type}) == expected


def test_side_router_missing_key_defaults_to_back():
    assert graph.side_router({}) == "back"


# --------------------------------------------------------------------------- #
# inference_router
# --------------------------------------------------------------------------- #
def test_inference_router_accepts_at_threshold():
    state = {"inference_confidence": FLASH_ACCEPT_THRESHOLD, "correction_attempts": 0}
    assert graph.inference_router(state) == "accept"


def test_inference_router_accepts_above_threshold():
    assert graph.inference_router({"inference_confidence": 0.99}) == "accept"


def test_inference_router_corrects_in_mid_band_with_attempts_left():
    state = {"inference_confidence": FLASH_ESCALATE_THRESHOLD, "correction_attempts": 0}
    assert graph.inference_router(state) == "correct"


def test_inference_router_escalates_when_corrections_exhausted():
    state = {
        "inference_confidence": (FLASH_ACCEPT_THRESHOLD + FLASH_ESCALATE_THRESHOLD) / 2,
        "correction_attempts": MAX_CORRECTIONS,
    }
    assert graph.inference_router(state) == "escalate"


def test_inference_router_escalates_below_escalate_threshold():
    state = {
        "inference_confidence": FLASH_ESCALATE_THRESHOLD - 0.01,
        "correction_attempts": 0,
    }
    assert graph.inference_router(state) == "escalate"


def test_inference_router_defaults_attempts_to_zero():
    # No correction_attempts key present → treated as 0 attempts.
    state = {"inference_confidence": FLASH_ESCALATE_THRESHOLD + 0.1}
    assert graph.inference_router(state) == "correct"


# --------------------------------------------------------------------------- #
# early_registry_router
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "state, expected",
    [
        ({"is_ready_for_logic": True}, "registry_hit"),
        ({"is_ready_for_logic": False}, "continue"),
        ({}, "continue"),
    ],
)
def test_early_registry_router(state, expected):
    assert graph.early_registry_router(state) == expected


# --------------------------------------------------------------------------- #
# pro_scanner_router
# --------------------------------------------------------------------------- #
def test_pro_scanner_router_accept_at_threshold():
    assert graph.pro_scanner_router({"inference_confidence": FLASH_ACCEPT_THRESHOLD}) == "accept"


def test_pro_scanner_router_retake_below_threshold():
    state = {"inference_confidence": FLASH_ACCEPT_THRESHOLD - 0.01}
    assert graph.pro_scanner_router(state) == "retake"


# --------------------------------------------------------------------------- #
# post_registry_router
# --------------------------------------------------------------------------- #
def test_post_registry_router_registry_hit_always_has_ingredients():
    # A registry match wins even with no photo ingredients at all.
    state = {"registry_matched": True, "extracted_data": make_extraction(0)}
    assert graph.post_registry_router(state) == "have_ingredients"


def test_post_registry_router_miss_with_enough_photo_ingredients():
    state = {
        "registry_matched": False,
        "extracted_data": make_extraction(MIN_INGREDIENTS_FOR_AUDIT),
    }
    assert graph.post_registry_router(state) == "have_ingredients"


def test_post_registry_router_miss_with_too_few_ingredients_needs_search():
    state = {
        "registry_matched": False,
        "extracted_data": make_extraction(MIN_INGREDIENTS_FOR_AUDIT - 1),
    }
    assert graph.post_registry_router(state) == "need_search"


def test_post_registry_router_miss_with_no_extraction_needs_search():
    state = {"registry_matched": False, "extracted_data": None}
    assert graph.post_registry_router(state) == "need_search"


# --------------------------------------------------------------------------- #
# identity_router
# --------------------------------------------------------------------------- #
def test_identity_router_confident_at_threshold():
    state = {"identity_confidence": IDENTITY_CONFIDENCE_THRESHOLD}
    assert graph.identity_router(state) == "confident"


def test_identity_router_uncertain_below_threshold():
    state = {"identity_confidence": IDENTITY_CONFIDENCE_THRESHOLD - 0.01}
    assert graph.identity_router(state) == "uncertain"


def test_identity_router_none_confidence_is_uncertain():
    assert graph.identity_router({"identity_confidence": None}) == "uncertain"
    assert graph.identity_router({}) == "uncertain"


# --------------------------------------------------------------------------- #
# web_result_router
# --------------------------------------------------------------------------- #
def test_web_result_router_found_with_enough_ingredients():
    state = {"extracted_data": make_extraction(MIN_INGREDIENTS_FOR_AUDIT)}
    assert graph.web_result_router(state) == "found"


def test_web_result_router_not_found_with_too_few():
    state = {"extracted_data": make_extraction(MIN_INGREDIENTS_FOR_AUDIT - 1)}
    assert graph.web_result_router(state) == "not_found"


def test_web_result_router_not_found_with_no_extraction():
    assert graph.web_result_router({"extracted_data": None}) == "not_found"


# --------------------------------------------------------------------------- #
# inline nodes: correction / retake / tag_language
# --------------------------------------------------------------------------- #
def test_correction_node_builds_feedback_and_increments_attempts():
    extraction = make_extraction(2, extraction_confidence=0.62, system_status="INCOMPLETE")
    state = {"extracted_data": extraction, "correction_attempts": 1}

    result = graph.correction_node(state)

    assert result["correction_attempts"] == 2
    assert "0.62" in result["correction_feedback"]
    assert "INCOMPLETE" in result["correction_feedback"]


def test_correction_node_defaults_attempts_to_zero():
    state = {"extracted_data": make_extraction(1)}
    assert graph.correction_node(state)["correction_attempts"] == 1


def test_correction_node_raises_without_extraction():
    with pytest.raises(ValueError):
        graph.correction_node({"extracted_data": None})


def test_retake_node_flags_and_message():
    result = graph.retake_node({})
    assert result["retake_requested"] is True
    assert result["is_ready_for_logic"] is False
    assert result["coach_advice"]  # non-empty user-facing prompt


def test_tag_language_node_normalises_case_and_whitespace():
    state = {"extracted_data": make_extraction(0, source_language="  jp ")}
    result = graph.tag_language_node(state)
    assert result["detected_language"] == "JP"
    assert result["language_supported"] is True


def test_tag_language_node_without_extraction():
    result = graph.tag_language_node({"extracted_data": None})
    assert result["detected_language"] == ""
    assert result["language_supported"] is True
