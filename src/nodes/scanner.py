# Vision scanner nodes: the Tier-2 content/side classifier, the lightweight
# flash scanner, and the pro expert fallback for challenging pictures.
import logging
from typing import Any, Literal, cast

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from src.config import FLASH_MODEL, OCR_CROSS_CHECK_ENABLED, PRO_MODEL
from src.nodes.normalizer import ledger_match
from src.ocr_check import ocr_agreement
from src.preprocess import encode_image
from src.prompts.scanner import CLASSIFY_PROMPT, SCANNER_SYSTEM_PROMPT
from src.state import AgentState, ProductExtraction


class ImageSide(BaseModel):
    content: Literal[
        "product", "not_a_product", "non_skincare_product", "multiple_products"
    ] = Field(
        default="product",
        description=(
            "What the photo shows: one analysable skincare product, no product "
            "at all, a product that is NOT skincare (food, supplements, "
            "haircare, cleaning...), or several distinct products in one frame."
        ),
    )
    side: Literal["front", "back"] = Field(description="Which side of the product the photo shows.")
    confidence: float = Field(
        description="0.0-1.0 overall confidence in the content + side classification."
    )
    # Branding read in the SAME call (the classifier already looks at it to decide
    # front vs back), so a front photo can seed the web-search fallback without a
    # separate identity VLM pass.
    brand: str = Field(
        default="", description="Brand name read from the label (English; may be empty)."
    )
    product_name: str = Field(
        default="",
        description="Product name read from the label (English; may be empty).",
    )
    identity_confidence: float = Field(
        default=0.0,
        description=(
            "0.0-1.0 confidence that the brand AND product name are read "
            "correctly. Use < 0.8 if either is blurry, cropped, or guessed."
        ),
    )


def build_vlm(model: str, schema, *, temperature: float = 0.0):
    """Configured Gemini client with structured output, shared by the VLM nodes."""
    return ChatGoogleGenerativeAI(
        model=model, temperature=temperature, timeout=120, max_retries=3
    ).with_structured_output(schema)


def image_message(text: str, image_path: str, *, profile: str = "ocr") -> HumanMessage:
    """A HumanMessage carrying a text prompt plus the preprocessed base64 image.

    ``profile`` picks the preprocessing stack: "light" for classification /
    identity reads (the heavy OCR stack distorts logos and brand colours),
    "ocr" for back-label ingredient extraction.
    """
    base64_image = encode_image(image_path, profile)
    return HumanMessage(
        content=[
            {"type": "text", "text": text},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
            },
        ]
    )


def classify_side_node(state: AgentState) -> dict[str, Any]:
    """Classify the photo's content (Tier 2) and which side it shows.

    In one VLM call this decides front vs back, flags out-of-distribution
    frames — ``not_a_product`` / ``non_skincare_product`` / ``multiple_products``
    — AND reads the branding, so the graph can reject bad frames before the
    structured-output scanner is forced to fabricate a product.

    The classification now runs even when the caller passed an explicit
    ``image_type`` override: the override pins the *side*, but skipping the call
    entirely left two holes — a non-product frame with an override went straight
    to the scanner (which cannot say "no product"), and an overridden *front*
    photo reached the identity gate with no identity read at all, dead-ending
    every such scan at confirm_identity.
    """
    override = state.get("image_type")
    if override not in ("front", "back"):
        override = None

    logging.info("Classifying image content + side...")
    llm = build_vlm(FLASH_MODEL, ImageSide)
    result = cast(
        ImageSide,
        llm.invoke([image_message(CLASSIFY_PROMPT, state["image_path"], profile="light")]),
    )
    side = override or result.side
    if override and override != result.side:
        logging.info(
            "Caller override keeps side=%s (classifier saw %s).", override, result.side
        )
    logging.info(
        "Image classified: content=%s side=%s (confidence %.2f)",
        result.content,
        side,
        result.confidence,
    )
    out: dict[str, Any] = {
        "image_type": side,
        "image_content": result.content,
        "classify_confidence": result.confidence,
    }
    # A front photo has no ingredient list to scan, so seed the identity the web
    # fallback needs directly from this call's branding read — no separate
    # verify_identity VLM pass. Back photos get their identity from the scanner
    # instead, so we leave identity_confidence unset for them.
    if side == "front" and result.content == "product":
        logging.info(
            "Front photo identity: %s — %s (confidence %.2f)",
            result.brand,
            result.product_name,
            result.identity_confidence,
        )
        out["identity_confidence"] = result.identity_confidence
        out["extracted_data"] = ProductExtraction(
            brand=result.brand,
            product_name=result.product_name,
            ingredients=[],
            source_language="",
            extraction_confidence=result.identity_confidence,
            system_status="INCOMPLETE",
        )
        out["model_used"] = "web"
    return out


# Both scanners share everything but the model, prompt, and the model tag they
# record — so they delegate to one core and only differ in those three inputs.
def _run_scanner(state: AgentState, *, model: str, prompt: str, model_tag: str) -> dict[str, Any]:
    llm = build_vlm(model, ProductExtraction)
    extracted = cast(ProductExtraction, llm.invoke([image_message(prompt, state["image_path"])]))
    logging.info(
        "%s scan completed with confidence %.2f",
        model_tag,
        extracted.extraction_confidence,
    )
    # Grounded quality signal the router can trust: how much of what the model
    # "read" resolves to known ingredient names (exact ledger tier, offline).
    rate, unmatched = ledger_match([ing.name_raw for ing in extracted.ingredients])
    if rate is not None:
        logging.info(
            "Ledger match rate: %.2f (%d/%d unmatched)",
            rate,
            len(unmatched),
            len(extracted.ingredients),
        )
    out: dict[str, Any] = {
        "extracted_data": extracted,
        "inference_confidence": extracted.extraction_confidence,
        "ledger_match_rate": rate,
        "model_used": model_tag,
    }
    # Advisory cross-check against a local OCR pass (opt-in; needs yomitoku).
    if OCR_CROSS_CHECK_ENABLED:
        agreement = ocr_agreement(
            state["image_path"], [ing.name_raw for ing in extracted.ingredients]
        )
        if agreement is not None:
            logging.info("OCR cross-check agreement: %.2f", agreement)
        out["ocr_agreement"] = agreement
    return out


# Lightweight scanner (Flash Gemini). On a correction retry, the deterministic
# feedback from the correction node is appended to the system prompt.
def flash_scanner_node(state: AgentState) -> dict[str, Any]:
    logging.info("Starting lightweight flash scan using %s...", FLASH_MODEL)
    prompt = SCANNER_SYSTEM_PROMPT
    if state.get("correction_attempts", 0) > 0:
        prompt += (
            f"\n\nPREVIOUS ATTEMPT FEEDBACK:\n{state['correction_feedback']}\n"
            "Correct specifically those issues. Do not repeat the same mistakes."
        )
    return _run_scanner(state, model=FLASH_MODEL, prompt=prompt, model_tag="flash")


# Heavyweight model (aka expert fallback) for visually difficult labels.
def pro_scanner_node(state: AgentState) -> dict[str, Any]:
    logging.info("Starting heavyweight pro scan using %s...", PRO_MODEL)
    prompt = (
        SCANNER_SYSTEM_PROMPT
        + "\nFOCUS: Pay extreme attention to warped text on the edges of the bottle."
    )
    return _run_scanner(state, model=PRO_MODEL, prompt=prompt, model_tag="pro")
