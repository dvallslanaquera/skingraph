# Web price lookup for a saved routine product.
#
# Reuses the Gemini + Google-Search grounding pattern from src/nodes/websearch.py
# (grounding cannot be combined with structured output, so we prompt for a strict
# line format and parse it deterministically). Used at add-to-routine time so the
# routine dashboard can show an amortized monthly cost.
#
# Pricing rule (per product spec): prefer the Japanese-market price; if the
# product is not sold in Japan, use the average price in its origin market. Always
# also return the price converted to USD (the dashboard totals in USD).
import logging
import re
from typing import Any, List, Optional

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel

from src.config import FLASH_MODEL


class PriceInfo(BaseModel):
    """A single product's looked-up price, normalised for the dashboard."""

    price_usd: Optional[float] = None
    price_native: Optional[float] = None
    currency: Optional[str] = None
    market: Optional[str] = None
    months_supply: Optional[float] = None
    source: Optional[str] = None


_PRICE_PROMPT = """
Find the typical retail PRICE of this cosmetic product and how long one unit
lasts:

  Brand: {brand}
  Product: {product_name}

Use web search. Prefer the price in the JAPANESE market (in JPY). If the product
is NOT sold in Japan, use the average price in the market where the brand
originates, in that market's local currency.

Then estimate how many MONTHS a single unit typically lasts for someone using it
daily as directed (e.g. a 30 ml serum ~2-3 months, a cleanser ~3 months).

OUTPUT FORMAT (strict — one value per line, no commentary, no symbols):
PRICE_NATIVE: <number only, no currency symbol or thousands separators>
CURRENCY: <ISO 4217 code, e.g. JPY, USD, EUR, KRW>
MARKET: <JP for a Japanese-market price, otherwise the 2-letter origin country code>
PRICE_USD: <the same price converted to US dollars, number only>
MONTHS: <estimated months one unit lasts, a number like 2 or 3.5>
SOURCE: <the url you used>

If you cannot find a reliable price, reply with exactly:
NOT_FOUND
""".strip()


def _text_of(response: Any) -> str:
    """Flatten a chat response's content to a plain string (grounding-safe)."""
    content = getattr(response, "content", response)
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", ""))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(content)


def _num(value: str) -> Optional[float]:
    """Parse a numeric token, tolerating currency symbols and separators."""
    cleaned = re.sub(r"[^\d.]", "", value.replace(",", ""))
    if not cleaned or cleaned == ".":
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_price(text: str) -> Optional[PriceInfo]:
    """Parse the grounded answer's strict key/value lines into a PriceInfo."""
    fields: dict = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.upper() == "NOT_FOUND":
            return None
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        fields[key.strip().upper()] = val.strip()

    if not fields:
        return None

    info = PriceInfo(
        price_usd=_num(fields.get("PRICE_USD", "")),
        price_native=_num(fields.get("PRICE_NATIVE", "")),
        currency=(fields.get("CURRENCY") or None),
        market=(fields.get("MARKET") or None),
        months_supply=_num(fields.get("MONTHS", "")),
        source=(fields.get("SOURCE") or None),
    )

    # Fall back to the native amount when the model skipped the USD conversion but
    # the native price already is USD.
    if info.price_usd is None and (info.currency or "").upper() == "USD":
        info.price_usd = info.price_native

    if info.price_usd is None and info.price_native is None:
        return None
    return info


def lookup_price(brand: str, product_name: str) -> Optional[PriceInfo]:
    """Look up a product's price via grounded web search; None if not found.

    Best-effort: callers wrap this so any LLM/network failure degrades to "no
    price" rather than blocking the save.
    """
    logging.info("Price lookup: %s — %s", brand, product_name)
    llm = ChatGoogleGenerativeAI(model=FLASH_MODEL, temperature=0.0, timeout=120)
    prompt = _PRICE_PROMPT.format(brand=brand, product_name=product_name)
    response = llm.invoke(
        [HumanMessage(content=prompt)], tools=[{"google_search": {}}]
    )
    info = _parse_price(_text_of(response))
    if info is None:
        logging.info("Price lookup found nothing for %s — %s", brand, product_name)
    else:
        logging.info(
            "Price: %s USD (native %s %s, market %s, ~%s months)",
            info.price_usd,
            info.price_native,
            info.currency,
            info.market,
            info.months_supply,
        )
    return info
