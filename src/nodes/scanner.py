# it contains two main scanners: flash one and the pro expert fallback for challenging pictures
import base64
import io
import logging
from typing import Dict, Any, cast
from uuid import uuid4
from PIL import Image
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
4. Assess extraction confidence (0.0 to 1.0):
   - 1.0: Clear, legible text with no ambiguity
   - 0.7: Minor issues (slight blur, small glare spots) - most content readable
   - 0.4: Significant challenges (curved text, heavy glare) - some guessing required
   - 0.0: Unreadable or missing critical information
5. Return ONLY valid JSON with this exact structure:
{
  "brand": "string (English brand name)",
  "product_name": "string (official English name — transliterate katakana if needed, e.g. モイスチャライジングクリーム → Moisturizing Cream)",
  "ingredients": [{"name_raw": "string", "name_standardized": "string"}],
  "is_quasi_drug": boolean,
  "extraction_confidence": float,
  "system_status": "SUCCESS | INCOMPLETE | RETAKE_REQUIRED"
}
"""


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
