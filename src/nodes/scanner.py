# it contains two main scanners: flash one and the pro expert fallback for challenging pictures
import base64
import os
import logging
from typing import Optional, Literal, List, Dict, Any
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from src.state import AgentState, ProductExtraction

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
  "brand": "string",
  "product_name": "string",
  "ingredients": [{"raw_name": "string", "standardized_name": "string"}],
  "is_quasi_drug": boolean,
  "confidence": float,
  "notes": "string"
}
"""


def encode_image(image_path: str) -> str:
    """
    Converts a local imag efile into a Base64 string for API transmission.
    """
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode(encoding="utf-8")


# Lightweight scanner (flash Gemini)
def flash_scanner_node(state: AgentState) -> Dict[str, Any]:
    logging.info("Starting lightweight flash scan using Gemini 2.5 Flash...")
    # return with structured output
    flash_llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash", temperature=0.0
    ).with_structured_output(ProductExtraction)

    base64_image = encode_image(state["image_path"])
    message = HumanMessage(
        content=[
            {"type": "text", "text": SCANNER_SYSTEM_PROMPT},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
            },
        ]
    )
    extracted = flash_llm.invoke([message])
    logging.info(
        f"Flash scan completed with confidence {extracted.extraction_confidence:.2f}"
    )

    return {
        "extracted_data": extracted,
        "inference_confidence": extracted.extraction_confidence,
        "model_used": "flash",
    }


# Heavyweight model (aka expert fallback)
def pro_scanner_node(state: AgentState) -> Dict[str, Any]:
    logging.info("Starting heavyweight pro scan using Gemini 2.5 Pro...")
    # return with structured output
    pro_llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-pro", temperature=0.0
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
    extracted = pro_llm.invoke([message])
    logging.info(
        f"Pro scan completed with confidence {extracted.extraction_confidence:.2f}"
    )

    return {
        "extracted_data": extracted,
        "inference_confidence": extracted.extraction_confidence,
        "model_used": "pro",
    }
