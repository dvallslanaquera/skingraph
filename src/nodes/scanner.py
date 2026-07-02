# Vision scanner nodes: the Tier-2 content/side classifier, the lightweight
# flash scanner, and the pro expert fallback for challenging pictures.
import logging
from typing import Any, Dict, Literal, cast

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from src.config import FLASH_MODEL, PRO_MODEL
from src.preprocess import encode_image
from src.prompts.scanner import CLASSIFY_PROMPT, SCANNER_SYSTEM_PROMPT
from src.state import AgentState, ProductExtraction


class ImageSide(BaseModel):
    content: Literal["product", "not_a_product", "multiple_products"] = Field(
        default="product",
        description=(
            "What the photo shows: one analysable product, no product at all, "
            "or several distinct products sharing one frame."
        ),
    )
    side: Literal["front", "back"] = Field(
        description="Which side of the product the photo shows."
    )
    confidence: float = Field(
        description="0.0-1.0 overall confidence in the content + side classification."
    )


def build_vlm(model: str, schema, *, temperature: float = 0.0):
    """Configured Gemini client with structured output, shared by the VLM nodes."""
    return ChatGoogleGenerativeAI(
        model=model, temperature=temperature, timeout=120, max_retries=3
    ).with_structured_output(schema)


def image_message(text: str, image_path: str) -> HumanMessage:
    """A HumanMessage carrying a text prompt plus the preprocessed base64 image."""
    base64_image = encode_image(image_path)
    return HumanMessage(
        content=[
            {"type": "text", "text": text},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
            },
        ]
    )


def classify_side_node(state: AgentState) -> Dict[str, Any]:
    """Classify the photo's content (Tier 2) and which side it shows.

    In one VLM call this both decides front vs back AND flags out-of-distribution
    frames — ``not_a_product`` / ``multiple_products`` — so the graph can reject
    them before the structured-output scanner is forced to fabricate a product.
    An explicitly passed ``image_type`` (CLI override) wins and skips the call;
    the Tier-1 pixel gate still guards that path.
    """
    override = state.get("image_type")
    if override in ("front", "back"):
        logging.info("Image side overridden by caller: %s", override)
        return {"image_type": override}

    logging.info("Classifying image content + side...")
    llm = build_vlm(FLASH_MODEL, ImageSide)
    result = cast(ImageSide, llm.invoke([image_message(CLASSIFY_PROMPT, state["image_path"])]))
    logging.info(
        "Image classified: content=%s side=%s (confidence %.2f)",
        result.content,
        result.side,
        result.confidence,
    )
    return {"image_type": result.side, "image_content": result.content}


# Both scanners share everything but the model, prompt, and the model tag they
# record — so they delegate to one core and only differ in those three inputs.
def _run_scanner(
    state: AgentState, *, model: str, prompt: str, model_tag: str
) -> Dict[str, Any]:
    llm = build_vlm(model, ProductExtraction)
    extracted = cast(
        ProductExtraction, llm.invoke([image_message(prompt, state["image_path"])])
    )
    logging.info(
        "%s scan completed with confidence %.2f",
        model_tag,
        extracted.extraction_confidence,
    )
    return {
        "extracted_data": extracted,
        "inference_confidence": extracted.extraction_confidence,
        "model_used": model_tag,
    }


# Lightweight scanner (Flash Gemini). On a correction retry, the deterministic
# feedback from the correction node is appended to the system prompt.
def flash_scanner_node(state: AgentState) -> Dict[str, Any]:
    logging.info("Starting lightweight flash scan using %s...", FLASH_MODEL)
    prompt = SCANNER_SYSTEM_PROMPT
    if state.get("correction_attempts", 0) > 0:
        prompt += (
            f"\n\nPREVIOUS ATTEMPT FEEDBACK:\n{state['correction_feedback']}\n"
            "Correct specifically those issues. Do not repeat the same mistakes."
        )
    return _run_scanner(state, model=FLASH_MODEL, prompt=prompt, model_tag="flash")


# Heavyweight model (aka expert fallback) for visually difficult labels.
def pro_scanner_node(state: AgentState) -> Dict[str, Any]:
    logging.info("Starting heavyweight pro scan using %s...", PRO_MODEL)
    prompt = (
        SCANNER_SYSTEM_PROMPT
        + "\nFOCUS: Pay extreme attention to warped text on the edges of the bottle."
    )
    return _run_scanner(state, model=PRO_MODEL, prompt=prompt, model_tag="pro")
