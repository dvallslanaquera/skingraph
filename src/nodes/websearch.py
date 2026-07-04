# Web-search fallback nodes — last resort when neither the registry nor the
# photo yields a usable ingredient list.
#
# Flow (identity is already read upstream — by classify_side for a front photo,
# by the scanner for a back photo — and gated by identity_router):
#   web_search → Gemini + Google Search grounding fetches the official 全成分,
#       a second (search-free) structured pass parses it, and the retrieved
#       product's identity is verified against what was read off the photo.
#       Match + enough ingredients → normalizer; identity mismatch →
#       confirm_identity (never audit another product's list); otherwise →
#       search_failed (ask for a back-label photo).
#
# Google Search grounding cannot be combined with structured output, so the
# search returns grounded text; parsing is a second structured call with a
# deterministic line-parser as fallback. Results are cached on disk so repeat
# scans of the same product don't re-pay the grounded search.
import json
import logging
import os
import re
import time
import unicodedata
from typing import Any
from urllib.parse import urlparse

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field
from rapidfuzz import fuzz

from src import config
from src.config import FLASH_MODEL, MIN_INGREDIENTS_FOR_AUDIT, WEB_IDENTITY_MATCH_THRESHOLD
from src.messages import CONFIRM_IDENTITY, SEARCH_FAILED, WEB_MISMATCH
from src.prompts.websearch import PARSE_PROMPT, SEARCH_PROMPT
from src.state import AgentState, Ingredient, Notice

# Strips leading bullets / numbering like "1. ", "・", "- ", "* ".
_NOISE = re.compile(r"^[\s・\-\*•]*\d*[\.\)]?\s*")


class WebIngredientList(BaseModel):
    """Structured parse of the grounded search answer (second LLM pass)."""

    found: bool = Field(description="False when the text contains no ingredient list.")
    brand: str = Field(default="", description="Brand the found list belongs to.")
    product_name: str = Field(default="", description="Product the found list belongs to.")
    ingredients: list[str] = Field(
        default_factory=list, description="Ingredient names in published order."
    )
    source_url: str = Field(default="", description="URL of the source page, if stated.")


def _build_llm(**kwargs) -> ChatGoogleGenerativeAI:
    """Grounded/parse LLM with the same retry budget as the scanner clients."""
    return ChatGoogleGenerativeAI(
        model=FLASH_MODEL, temperature=0.0, timeout=120, max_retries=3, **kwargs
    )


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


def _parse_ingredients(text: str) -> tuple[list[str], list[str]]:
    """Deterministic fallback parser → (ingredient_names, source_urls)."""
    ingredients: list[str] = []
    sources: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.upper().startswith(("SOURCE:", "MATCHED:")):
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


def _structured_parse(text: str) -> WebIngredientList | None:
    """Second-pass structured extraction of the grounded answer; None on failure."""
    try:
        llm = _build_llm().with_structured_output(WebIngredientList)
        result = llm.invoke([HumanMessage(content=PARSE_PROMPT.format(text=text))])
        return result if isinstance(result, WebIngredientList) else None
    except Exception:  # noqa: BLE001 — the line parser below still works without it
        logging.exception("Structured parse of web-search answer failed; using line parser.")
        return None


def _grounding_sources(response: Any) -> list[str]:
    """Best-effort extraction of citation URLs from grounding metadata."""
    urls: list[str] = []
    try:
        meta = getattr(response, "response_metadata", {}) or {}
        grounding = meta.get("grounding_metadata") or {}
        for chunk in grounding.get("grounding_chunks", []) or []:
            uri = (chunk.get("web") or {}).get("uri")
            if uri:
                urls.append(uri)
    except Exception:  # noqa: S110 — metadata shape varies by version; citations are optional
        pass
    return urls


def _rank_sources(sources: list[str]) -> list[str]:
    """Order source URLs so trusted ingredient-database/official domains come first."""

    def _trusted(url: str) -> bool:
        try:
            host = (urlparse(url).hostname or "").lower()
        except ValueError:
            return False
        return any(host == d or host.endswith("." + d) for d in config.TRUSTED_SOURCE_DOMAINS)

    ranked = sorted(sources, key=lambda u: not _trusted(u))
    if ranked and not _trusted(ranked[0]):
        logging.info("Web-search sources are all untrusted domains: %s", ranked[:3])
    return ranked


def _identity_match(searched: str, found: str) -> float | None:
    """Fuzzy 0-100 similarity between the searched and retrieved identities.

    None when the parse produced no identity to verify against — the caller
    treats that as "no signal" rather than a mismatch.
    """
    if not found.strip() or not searched.strip():
        return None
    return float(fuzz.WRatio(searched.lower(), found.lower()))


_KANA_KANJI = re.compile(r"[぀-ヿ一-鿿]")
_HANGUL = re.compile(r"[가-힯]")


def _infer_language(names: list[str]) -> str:
    """Guess the 2-letter label language of a retrieved ingredient list."""
    joined = " ".join(names)
    if _KANA_KANJI.search(joined):
        return "JP"
    if _HANGUL.search(joined):
        return "KO"
    return "EN"


# --- on-disk result cache -----------------------------------------------------

_CACHE: dict[str, dict] | None = None


def _cache_key(brand: str, product: str) -> str:
    fold = "".join(unicodedata.normalize("NFKC", f"{brand}|{product}").lower().split())
    return fold


def _load_cache() -> dict[str, dict]:
    global _CACHE
    if _CACHE is None:
        try:
            with open(config.WEB_CACHE_PATH, encoding="utf-8") as f:
                _CACHE = json.load(f)
        except (OSError, ValueError):
            _CACHE = {}
    return _CACHE


def _cache_get(brand: str, product: str) -> dict | None:
    entry = _load_cache().get(_cache_key(brand, product))
    if not entry:
        return None
    if time.time() - entry.get("ts", 0) > config.WEB_CACHE_TTL_DAYS * 86400:
        return None
    logging.info("Web-search cache hit for %s — %s", brand, product)
    return entry


def _cache_put(brand: str, product: str, names: list[str], sources: list[str], lang: str) -> None:
    cache = _load_cache()
    cache[_cache_key(brand, product)] = {
        "ts": time.time(),
        "names": names,
        "sources": sources,
        "lang": lang,
    }
    try:
        os.makedirs(os.path.dirname(config.WEB_CACHE_PATH) or ".", exist_ok=True)
        with open(config.WEB_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except OSError:  # cache is best-effort; never fail a scan over it
        logging.warning("Could not persist web-search cache to %s", config.WEB_CACHE_PATH)


# --- nodes ----------------------------------------------------------------------


def _adopt(state: AgentState, names: list[str], sources: list[str], lang: str) -> dict:
    """State update that adopts a retrieved ingredient list."""
    data = state["extracted_data"]
    ingredients = [Ingredient(name_raw=n, source_language=lang) for n in names]
    out: dict = {"web_sources": sources, "ingredient_source": "web"}
    if data is not None:
        out["extracted_data"] = data.model_copy(update={"ingredients": ingredients})
    return out


def web_search_node(state: AgentState) -> dict:
    """Fetch the product's ingredient list from the web via Google grounding."""
    data = state["extracted_data"]
    brand = data.brand if data else ""
    product = data.product_name if data else ""
    logging.info("Web search for ingredients: %s — %s", brand, product)

    cached = _cache_get(brand, product)
    if cached:
        return _adopt(state, cached["names"], cached["sources"], cached.get("lang", "JP"))

    prompt = SEARCH_PROMPT.format(brand=brand, product_name=product)
    response = _build_llm().invoke(
        [HumanMessage(content=prompt)], tools=[{"google_search": {}}]
    )
    text = _text_of(response)

    # Second pass: structured parse (identity-aware); line parser as fallback.
    parsed = _structured_parse(text)
    if parsed is not None:
        names = [] if not parsed.found else [n.strip() for n in parsed.ingredients if n.strip()]
        sources = [parsed.source_url] if parsed.source_url else []
        found_identity = f"{parsed.brand} {parsed.product_name}".strip()
    else:
        names, sources = _parse_ingredients(text)
        found_identity = ""

    for uri in _grounding_sources(response):
        if uri not in sources:
            sources.append(uri)
    sources = _rank_sources(sources)

    if len(names) < MIN_INGREDIENTS_FOR_AUDIT:
        logging.warning(
            "Web search found only %d ingredient(s) — treating as not found.",
            len(names),
        )
        # Leave extracted_data.ingredients unchanged so the router sees < MIN.
        return {"web_sources": sources, "ingredient_source": "web"}

    # Verify the list belongs to the product in the photo before trusting it: a
    # misread brand would otherwise silently audit a different product.
    match = _identity_match(f"{brand} {product}", found_identity)
    if match is not None and match < WEB_IDENTITY_MATCH_THRESHOLD:
        logging.warning(
            "Web result identity mismatch (%.0f/100): searched '%s — %s', found '%s'.",
            match,
            brand,
            product,
            found_identity,
        )
        return {
            "web_identity_mismatch": True,
            "web_sources": sources,
            "ingredient_source": "web",
        }

    lang = _infer_language(names)
    logging.info(
        "Web search recovered %d ingredient(s) [%s] from %d source(s).",
        len(names),
        lang,
        len(sources),
    )
    _cache_put(brand, product, names, sources, lang)
    return _adopt(state, names, sources, lang)


def confirm_identity_node(state: AgentState) -> dict:
    """Graceful exit: the identity read (or the web match on it) wasn't trustworthy."""
    data = state.get("extracted_data")
    guess = f"{data.brand} — {data.product_name}" if data else "this product"
    copy = WEB_MISMATCH if state.get("web_identity_mismatch") else CONFIRM_IDENTITY
    return {
        "is_ready_for_logic": False,
        "notice": Notice(
            en=copy["en"].format(guess=guess),
            ja=copy["ja"].format(guess=guess),
        ),
    }


def search_failed_node(state: AgentState) -> dict:
    """Graceful exit: identity was confident but no ingredient list was found."""
    data = state.get("extracted_data")
    name = f"{data.brand} — {data.product_name}" if data else "this product"
    return {
        "is_ready_for_logic": False,
        "notice": Notice(
            en=SEARCH_FAILED["en"].format(name=name),
            ja=SEARCH_FAILED["ja"].format(name=name),
        ),
    }
