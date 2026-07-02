# Prompt for the web-search fallback: the Google-grounded ingredient-list search
# (grounding cannot be combined with structured output, so the prompt demands a
# strict line format that is parsed deterministically). The brand + product name
# it searches for are read upstream — by classify_side for a front photo, by the
# scanner for a back photo — so there is no separate identity-read prompt here.

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
