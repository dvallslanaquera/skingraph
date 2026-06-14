# Web-search fallback nodes — last resort when neither the registry nor the
# photo yields a usable ingredient list.
#
# Flow:
#   verify_identity → focused re-read of brand + product name (+ confidence).
#       If confident → web_search; otherwise → confirm_identity (ask the user).
#   web_search → Gemini + Google Search grounding fetches the official 全成分.
#       If found → normalizer; otherwise → search_failed (ask for a photo).
#
# Google Search grounding cannot be combined with structured output, so the
# search returns grounded text that we parse deterministically.
import logging
import re
from typing import Any, List, Tuple, cast

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from src.config import FLASH_MODEL, MIN_INGREDIENTS_FOR_AUDIT
from src.nodes.scanner import encode_image
from src.state import AgentState, Ingredient


class ProductIdentity(BaseModel):
    brand: str = Field(description="Brand name as legibly read from the label")
    product_name: str = Field(
        description="Product name as legibly read from the label"
    )
    identity_confidence: float = Field(
        description=(
            "0.0-1.0 confidence that the brand AND product name are read "
            "correctly. Use < 0.8 if either is blurry, cropped, or guessed."
        )
    )


_VERIFY_PROMPT = """
Look at this product image and read ONLY the brand and the product name.
Do NOT extract ingredients. Focus entirely on whether the brand and product
name are legible and unambiguous.

Return:
- brand: the brand name (transliterate to English if needed)
- product_name: the official product name (transliterate katakana if needed)
- identity_confidence: 0.0-1.0 — how certain you are that BOTH are correct.
  Use a value below 0.8 if either is blurry, partially hidden, ambiguous,
  or you had to guess.
""".strip()


_SEARCH_PROMPT = """
Find the official FULL ingredient list (全成分) for this cosmetic product:

  Brand: {brand}
  Product: {product_name}

Use web search. Prefer the brand's official site, an official retailer, or a
reputable cosmetics ingredient database. Return the complete ingredient list
EXACTLY as published, in label order.

OUTPUT FORMAT (strict):
- One ingredient per line. No numbering, no bullets, no commentary.
- Use the Japanese 成分表示名称 where available; otherwise the INCI name.
- After the list, add ONE final line:  SOURCE: <the url you used>
- If you cannot find a reliable full ingredient list, reply with exactly:
  NOT_FOUND
""".strip()

# Strips leading bullets / numbering like "1. ", "・", "- ", "* ".
_NOISE = re.compile(r"^[\s・\-\*•]*\d*[\.\)]?\s*")


def verify_identity_node(state: AgentState) -> dict:
    """Re-read brand + product name with a focused, dedicated VLM pass."""
    logging.info("Verifying product identity before web search...")
    llm = ChatGoogleGenerativeAI(
        model=FLASH_MODEL, temperature=0.0, timeout=120, max_retries=3
    ).with_structured_output(ProductIdentity)

    base64_image = encode_image(state["image_path"])
    message = HumanMessage(
        content=[
            {"type": "text", "text": _VERIFY_PROMPT},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
            },
        ]
    )
    identity = cast(ProductIdentity, llm.invoke([message]))
    logging.info(
        "Identity: %s — %s (confidence %.2f)",
        identity.brand,
        identity.product_name,
        identity.identity_confidence,
    )

    result: dict = {"identity_confidence": identity.identity_confidence}
    # Adopt the focused re-read of the name (more reliable than the bulk scan).
    data = state.get("extracted_data")
    if data is not None:
        result["extracted_data"] = data.model_copy(
            update={
                "brand": identity.brand,
                "product_name": identity.product_name,
            }
        )
    return result


def _text_of(response: Any) -> str:
    """Flatten a chat response's content to a plain string."""
    content = getattr(response, "content", response)
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", ""))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(content)


def _parse_ingredients(text: str) -> Tuple[List[str], List[str]]:
    """Parse the grounded answer into (ingredient_names, source_urls)."""
    ingredients: List[str] = []
    sources: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.upper().startswith("SOURCE:"):
            url = line.split(":", 1)[1].strip()
            if url:
                sources.append(url)
            continue
        if line.upper() == "NOT_FOUND":
            return [], sources
        cleaned = _NOISE.sub("", line).strip()
        # Skip prose lines (long, or sentence-like) — keep ingredient-name tokens.
        if cleaned and len(cleaned) <= 60 and "。" not in cleaned:
            ingredients.append(cleaned)
    return ingredients, sources


def _grounding_sources(response: Any) -> List[str]:
    """Best-effort extraction of citation URLs from grounding metadata."""
    urls: List[str] = []
    try:
        meta = getattr(response, "response_metadata", {}) or {}
        grounding = meta.get("grounding_metadata") or {}
        for chunk in grounding.get("grounding_chunks", []) or []:
            uri = (chunk.get("web") or {}).get("uri")
            if uri:
                urls.append(uri)
    except Exception:  # metadata shape varies by version; citations are optional
        pass
    return urls


def web_search_node(state: AgentState) -> dict:
    """Fetch the product's ingredient list from the web via Google grounding."""
    data = state["extracted_data"]
    brand = data.brand if data else ""
    product = data.product_name if data else ""
    logging.info("Web search for ingredients: %s — %s", brand, product)

    llm = ChatGoogleGenerativeAI(model=FLASH_MODEL, temperature=0.0, timeout=120)
    prompt = _SEARCH_PROMPT.format(brand=brand, product_name=product)
    response = llm.invoke(
        [HumanMessage(content=prompt)], tools=[{"google_search": {}}]
    )

    names, sources = _parse_ingredients(_text_of(response))
    for uri in _grounding_sources(response):
        if uri not in sources:
            sources.append(uri)

    if len(names) < MIN_INGREDIENTS_FOR_AUDIT:
        logging.warning(
            "Web search found only %d ingredient(s) — treating as not found.",
            len(names),
        )
        # Leave extracted_data.ingredients unchanged so the router sees < MIN.
        return {"web_sources": sources, "ingredient_source": "web"}

    logging.info(
        "Web search recovered %d ingredient(s) from %d source(s).",
        len(names),
        len(sources),
    )
    ingredients = [Ingredient(name_raw=n, source_language="JP") for n in names]
    out: dict = {"web_sources": sources, "ingredient_source": "web"}
    if data is not None:
        out["extracted_data"] = data.model_copy(update={"ingredients": ingredients})
    return out


def confirm_identity_node(state: AgentState) -> dict:
    """Graceful exit: the product name wasn't read confidently enough to search."""
    data = state.get("extracted_data")
    guess = f"{data.brand} — {data.product_name}" if data else "this product"
    return {
        "is_ready_for_logic": False,
        "coach_advice": (
            "I couldn't confidently read this product's name from the photo. "
            f"My best guess is '{guess}'. Please confirm the exact brand and "
            "product name, or retake a clearer photo of the front label, so I "
            "can look up its ingredients accurately."
        ),
    }


def search_failed_node(state: AgentState) -> dict:
    """Graceful exit: identity was confident but no ingredient list was found."""
    data = state.get("extracted_data")
    name = f"{data.brand} — {data.product_name}" if data else "this product"
    return {
        "is_ready_for_logic": False,
        "coach_advice": (
            f"I identified the product as '{name}' but couldn't find a reliable "
            "full ingredient list online. Could you retake a clear photo of the "
            "ingredient list (全成分) on the back label?"
        ),
    }
