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


def classify_side_node(state: AgentState) -> Dict[str, Any]:
    """Auto-detect whether the photo is the front (branding) or back (ingredients).

    An explicitly passed ``image_type`` (CLI override) wins and skips the call.
    """
    override = state.get("image_type")
    if override in ("front", "back"):
        logging.info("Image side overridden by caller: %s", override)
        return {"image_type": override}

    logging.info("Classifying image side (front vs back)...")
    llm = ChatGoogleGenerativeAI(
        model=FLASH_MODEL, temperature=0.0, timeout=120, max_retries=3
    ).with_structured_output(ImageSide)

    base64_image = encode_image(state["image_path"])
    message = HumanMessage(
        content=[
            {"type": "text", "text": CLASSIFY_PROMPT},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
            },
        ]
    )
    result = cast(ImageSide, llm.invoke([message]))
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


# Lightweight scanner (flash Gemini)
def flash_scanner_node(state: AgentState) -> Dict[str, Any]:
    logging.info("Starting lightweight flash scan using Gemini 2.5 Flash...")
    flash_llm = ChatGoogleGenerativeAI(
        model=FLASH_MODEL, temperature=0.0, timeout=120, max_retries=3
    ).with_structured_output(ProductExtraction)

    prompt = SCANNER_SYSTEM_PROMPT
    if state.get("correction_attempts", 0) > 0:
        prompt += (
            f"\n\nPREVIOUS ATTEMPT FEEDBACK:\n{state['correction_feedback']}\n"
            "Correct specifically those issues. Do not repeat the same mistakes."
        )

    base64_image = encode_image(state["image_path"])
    message = HumanMessage(
        content=[
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
            },
        ]
    )
    extracted = cast(ProductExtraction, flash_llm.invoke([message]))
    logging.info(
        f"Flash scan completed with confidence {extracted.extraction_confidence:.2f}"
    )

    return {
        "extracted_data": extracted,
        "inference_confidence": extracted.extraction_confidence,
        "model_used": "flash",
        "trace_id": str(uuid4()),
    }


# Heavyweight model (aka expert fallback)
def pro_scanner_node(state: AgentState) -> Dict[str, Any]:
    logging.info("Starting heavyweight pro scan using Gemini 2.5 Pro...")
    # return with structured output
    pro_llm = ChatGoogleGenerativeAI(
        model=PRO_MODEL, temperature=0.0, timeout=120, max_retries=3
    ).with_structured_output(ProductExtraction)

    base64_image = encode_image(state["image_path"])
    message = HumanMessage(
        content=[
            {
                "type": "text",
                "text": SCANNER_SYSTEM_PROMPT
                + "\nFOCUS: Pay extreme attention to warped text on the edges of the bottle.",
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
            },
        ]
    )
    extracted = cast(ProductExtraction, pro_llm.invoke([message]))
    logging.info(
        f"Pro scan completed with confidence {extracted.extraction_confidence:.2f}"
    )

    return {
        "extracted_data": extracted,
        "inference_confidence": extracted.extraction_confidence,
        "model_used": "pro",
        "trace_id": str(uuid4()),
    }
