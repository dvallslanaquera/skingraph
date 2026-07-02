# Prompts for the web-search fallback: the focused identity re-read and the
# Google-grounded ingredient-list search (grounding cannot be combined with
# structured output, so the search prompt demands a strict line format that is
# parsed deterministically).

VERIFY_PROMPT = """
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


SEARCH_PROMPT = """
Find the official FULL ingredient list for this cosmetic product:

  Brand: {brand}
  Product: {product_name}

Use web search. Prefer the brand's official site, an official retailer, or a
reputable cosmetics ingredient database. Return the complete ingredient list
EXACTLY as published, in label order.

OUTPUT FORMAT (strict):
- One ingredient per line. No numbering, no bullets, no commentary.
- Use the INCI name where available; otherwise the name as published
  (e.g. the Japanese 成分表示名称).
- After the list, add ONE final line:  SOURCE: <the url you used>
- If you cannot find a reliable full ingredient list, reply with exactly:
  NOT_FOUND
""".strip()
