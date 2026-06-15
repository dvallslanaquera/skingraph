# it contains two main scanners: flash one and the pro expert fallback for challenging pictures
import base64
import io
import logging
from typing import Dict, Any, Literal, cast
from uuid import uuid4
from PIL import Image
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from src.state import AgentState, ProductExtraction
from src.config import FLASH_MODEL, PRO_MODEL



# TODO: probably better to keep prompts in different files
# TODO: fine-tune the prompt to Gemini requirements
SCANNER_SYSTEM_PROMPT = """
## ROLE
You are a Senior Dermatological Assistant and Expert OCR analyzer specializing in Japanese skincare product labels.
Your task is to extract and standardize skincare product information with high accuracy.

## INSTRUCTIONS
1. Identify and extract:
   - Brand name
   - Product name
   - Full list of ingredients (in order of concentration)
2. For each ingredient, provide:
   - Raw ingredient name as written on label
   - Standardized JCIA (Japan Cosmetic Industry Association) name if applicable
3. Classify the product category:
   - Check if labeled as "医薬部外品" (quasi-drug/medicated product)
   - Mark accordingly in is_quasi_drug field
4. Detect the label's PRIMARY language:
   - Base this on the dominant script/text of the label itself, NOT the brand's country of origin.
   - Report it as a 2-letter uppercase code in source_language: JP (Japanese), EN (English),
     KO (Korean), FR (French), ZH (Chinese), etc.
5. Assess extraction confidence (0.0 to 1.0):
   - 1.0: Clear, legible text with no ambiguity
   - 0.7: Minor issues (slight blur, small glare spots) - most content readable
   - 0.4: Significant challenges (curved text, heavy glare) - some guessing required
   - 0.0: Unreadable or missing critical information
6. Return ONLY valid JSON with this exact structure:
{
  "brand": "string (English brand name)",
  "product_name": "string (official English name — transliterate katakana if needed, e.g. モイスチャライジングクリーム → Moisturizing Cream)",
  "ingredients": [{"name_raw": "string", "name_standardized": "string"}],
  "is_quasi_drug": boolean,
  "source_language": "string (2-letter uppercase code: JP, EN, KO, FR, ZH, ...)",
  "extraction_confidence": float,
  "system_status": "SUCCESS | INCOMPLETE | RETAKE_REQUIRED"
}
"""


CLASSIFY_PROMPT = """
Look at this single product photo and decide which side of the package it shows.

- "front": the marketing/branding side — brand, product name, hero copy. The full
  ingredient list (全成分 / "Ingredients:") is NOT legibly visible.
- "back": the information side where the full ingredient list is printed and
  readable (paragraph of ingredient names, often headed 全成分 or "Ingredients").

Rule of thumb: if you can read an actual ingredient LIST, it's "back". If you only
see branding and no readable ingredient list, it's "front".

Return:
- side: "front" or "back"
- confidence: 0.0-1.0 — how certain you are.
""".strip()


class ImageSide(BaseModel):
    side: Literal["front", "back"] = Field(
        description="Which side of the product the photo shows."
    )
    confidence: float = Field(
        description="0.0-1.0 confidence in the front/back classification."
    )


def build_vlm(model: str, schema, *, temperature: float = 0.0):
    """Configured Gemini client with structured output, shared by the VLM nodes."""
    return ChatGoogleGenerativeAI(
        model=model, temperature=temperature, timeout=120, max_retries=3
    ).with_structured_output(schema)


def image_message(text: str, image_path: str) -> HumanMessage:
    """A HumanMessage carrying a text prompt plus the downscaled base64 image."""
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
    """Auto-detect whether the photo is the front (branding) or back (ingredients).

    An explicitly passed ``image_type`` (CLI override) wins and skips the call.
    """
    override = state.get("image_type")
    if override in ("front", "back"):
        logging.info("Image side overridden by caller: %s", override)
        return {"image_type": override}

    logging.info("Classifying image side (front vs back)...")
    llm = build_vlm(FLASH_MODEL, ImageSide)
    result = cast(ImageSide, llm.invoke([image_message(CLASSIFY_PROMPT, state["image_path"])]))
    logging.info(
        "Image side: %s (confidence %.2f)", result.side, result.confidence
    )
    return {"image_type": result.side}


def downscale_image(image_bytes: bytes, max_dim: int = 2048) -> bytes:
    img = Image.open(io.BytesIO(image_bytes))
    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    img.convert("RGB").save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


def encode_image(image_path: str) -> str:
    with open(image_path, "rb") as img_file:
        image_bytes = downscale_image(img_file.read())
    return base64.b64encode(image_bytes).decode(encoding="utf-8")


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
        "trace_id": str(uuid4()),
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
