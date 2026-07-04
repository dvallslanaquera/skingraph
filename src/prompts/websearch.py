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
- FIRST line: the exact brand and product name of the product whose list you
  found, as published on the source page, in the form:
  MATCHED: <brand> — <product name>
- Then one ingredient per line. No numbering, no bullets, no commentary.
- Use the INCI name where available; otherwise the name as published
  (e.g. the Japanese 成分表示名称).
- After the list, add ONE final line:  SOURCE: <the url you used>
- If you cannot find a reliable full ingredient list, reply with exactly:
  NOT_FOUND
""".strip()


# Second pass: turn the grounded free text above into a strict structure.
# (Google Search grounding cannot be combined with structured output in one
# call, so parsing is a separate, search-free LLM call over the returned text.)
PARSE_PROMPT = """
The text below is a web-search answer about a cosmetic product's ingredient
list. Extract from it, WITHOUT adding or inventing anything:

- found: false if the text says NOT_FOUND or contains no ingredient list.
- brand / product_name: the brand and product the list actually belongs to,
  as stated in the text (may differ from what was searched for).
- ingredients: every ingredient name, one entry each, in the published order,
  exactly as written (no translation, no commentary lines, no headers).
- source_url: the source URL mentioned in the text, or "" if none.

TEXT:
{text}
""".strip()
