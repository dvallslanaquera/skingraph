# Tests for the Gemini-backed scanner nodes with the LLM fully mocked.
#
# `ChatGoogleGenerativeAI` and `encode_image` are patched, so no API key,
# network call, or image file is required. We assert how each node shapes its
# state output and that the correction feedback is threaded into the prompt.
from unittest.mock import MagicMock

import pytest
from PIL import Image

from src.nodes import scanner
from src.nodes.scanner import ImageSide
from src.preprocess import assess_image_quality

from tests.helpers import make_extraction


@pytest.fixture
def mock_gemini(monkeypatch):
    """Patch out the Gemini client and image encoder.

    Returns an `install(return_value)` helper that wires the
    `ChatGoogleGenerativeAI(...).with_structured_output(...).invoke(...)` chain
    to return `return_value`, and hands back the mocks for inspection.
    """
    monkeypatch.setattr(scanner, "encode_image", lambda path: "FAKE_BASE64")
    handles = {}

    def install(return_value):
        invoke = MagicMock(return_value=return_value)
        structured = MagicMock()
        structured.invoke = invoke
        chat = MagicMock()
        chat.with_structured_output.return_value = structured
        cls = MagicMock(return_value=chat)
        monkeypatch.setattr(scanner, "ChatGoogleGenerativeAI", cls)
        handles["cls"] = cls
        handles["invoke"] = invoke
        return handles

    return install


def _prompt_text(invoke_mock) -> str:
    """Pull the text block of the HumanMessage passed to the mocked invoke."""
    messages = invoke_mock.call_args.args[0]
    return messages[0].content[0]["text"]


# --------------------------------------------------------------------------- #
# classify_side_node
# --------------------------------------------------------------------------- #
def test_classify_side_honours_caller_override(mock_gemini):
    handles = mock_gemini(None)
    result = scanner.classify_side_node({"image_type": "back", "image_path": "x.jpg"})
    assert result == {"image_type": "back"}
    # The override short-circuits before any model is constructed.
    handles["cls"].assert_not_called()


def test_classify_side_auto_detects_back(mock_gemini):
    handles = mock_gemini(ImageSide(side="back", confidence=0.92))
    result = scanner.classify_side_node({"image_type": None, "image_path": "x.jpg"})
    # A back photo carries no seeded identity — the scanner reads it instead.
    assert result == {"image_type": "back", "image_content": "product"}
    handles["cls"].assert_called_once()


def test_classify_side_front_seeds_identity(mock_gemini):
    # A front photo has no ingredient list, so the classifier's branding read is
    # seeded straight into extracted_data for the web fallback (no verify call).
    mock_gemini(
        ImageSide(
            content="product",
            side="front",
            confidence=0.9,
            brand="Curel",
            product_name="Cream",
            identity_confidence=0.88,
        )
    )
    result = scanner.classify_side_node({"image_type": None, "image_path": "x.jpg"})
    assert result["image_type"] == "front"
    assert result["identity_confidence"] == 0.88
    assert result["model_used"] == "web"
    seeded = result["extracted_data"]
    assert seeded.brand == "Curel"
    assert seeded.product_name == "Cream"
    assert seeded.ingredients == []
    assert seeded.extraction_confidence == 0.88


def test_classify_side_surfaces_content_verdict(mock_gemini):
    # Tier 2: the classifier flags a non-product frame in the same VLM call.
    mock_gemini(ImageSide(content="not_a_product", side="back", confidence=0.3))
    result = scanner.classify_side_node({"image_type": None, "image_path": "x.jpg"})
    assert result == {"image_type": "back", "image_content": "not_a_product"}


# --------------------------------------------------------------------------- #
# assess_image_quality (Tier-1 pixel pre-flight — no VLM)
# --------------------------------------------------------------------------- #
def _save(img, tmp_path, name="img.png") -> str:
    path = tmp_path / name
    img.save(path)
    return str(path)


def test_quality_flags_near_black_frame(tmp_path):
    path = _save(Image.new("RGB", (64, 64), (2, 2, 2)), tmp_path)
    assert assess_image_quality(path) == "too_dark"


def test_quality_flags_blown_out_frame(tmp_path):
    path = _save(Image.new("RGB", (64, 64), (255, 255, 255)), tmp_path)
    assert assess_image_quality(path) == "too_bright"


def test_quality_flags_uniform_blank_frame(tmp_path):
    # Mid-grey: luminance is fine but there's zero contrast → no product.
    path = _save(Image.new("RGB", (64, 64), (128, 128, 128)), tmp_path)
    assert assess_image_quality(path) == "blank"


def test_quality_passes_a_normal_contrasty_image(tmp_path):
    # A gradient has plenty of spread and mid-range mean → worth a VLM call.
    path = _save(Image.linear_gradient("L").convert("RGB"), tmp_path)
    assert assess_image_quality(path) is None


def test_quality_reports_unreadable_bytes(tmp_path):
    path = tmp_path / "broken.jpg"
    path.write_bytes(b"not really an image")
    assert assess_image_quality(str(path)) == "unreadable"


# --------------------------------------------------------------------------- #
# flash_scanner_node
# --------------------------------------------------------------------------- #
def test_flash_scanner_maps_extraction_to_state(mock_gemini):
    extraction = make_extraction(2, extraction_confidence=0.88)
    mock_gemini(extraction)

    result = scanner.flash_scanner_node({"image_path": "x.jpg"})

    assert result["extracted_data"] is extraction
    assert result["inference_confidence"] == 0.88
    assert result["model_used"] == "flash"


def test_flash_scanner_threads_correction_feedback_into_prompt(mock_gemini):
    handles = mock_gemini(make_extraction(1))
    state = {
        "image_path": "x.jpg",
        "correction_attempts": 1,
        "correction_feedback": "FOCUS ON THE CURVED EDGE",
    }
    scanner.flash_scanner_node(state)

    prompt = _prompt_text(handles["invoke"])
    assert "FOCUS ON THE CURVED EDGE" in prompt
    assert "PREVIOUS ATTEMPT FEEDBACK" in prompt


def test_flash_scanner_first_pass_has_no_feedback_block(mock_gemini):
    handles = mock_gemini(make_extraction(1))
    scanner.flash_scanner_node({"image_path": "x.jpg"})
    assert "PREVIOUS ATTEMPT FEEDBACK" not in _prompt_text(handles["invoke"])


# --------------------------------------------------------------------------- #
# pro_scanner_node
# --------------------------------------------------------------------------- #
def test_pro_scanner_tags_model_as_pro(mock_gemini):
    extraction = make_extraction(3, extraction_confidence=0.95)
    mock_gemini(extraction)

    result = scanner.pro_scanner_node({"image_path": "x.jpg"})

    assert result["extracted_data"] is extraction
    assert result["inference_confidence"] == 0.95
    assert result["model_used"] == "pro"
