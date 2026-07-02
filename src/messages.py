# Bilingual (en/ja) copy for the graceful-exit paths: the retake bounces from
# graph.py and the identity/search exits from the websearch nodes. Every entry
# carries both languages so the exits can be served in the UI language; today
# the nodes consume only "en" (the ja side is wired up in the bilingual-notices
# work, Phase 4.2).

# VLM-confidence retake: label unreadable after both scanners.
RETAKE_DEFAULT = {
    "en": (
        "I couldn't read the label clearly. "
        "Could you please retake the photo with less glare and flatter alignment?"
    ),
    "ja": (
        "ラベルをはっきり読み取ることができませんでした。"
        "反射を抑え、ラベルが平らに写るように撮り直していただけますか？"
    ),
}

# Keyed by the Tier-1 pixel verdict (image_quality_issue) or the Tier-2 content
# verdict (image_content), so each rejection tells the user exactly what to fix.
REJECTION_MESSAGES = {
    "too_dark": {
        "en": (
            "This photo looks almost completely dark. Please retake it in good "
            "lighting with the product label clearly visible."
        ),
        "ja": (
            "お写真がほぼ真っ暗に写っています。明るい場所で、製品ラベルが"
            "はっきり見えるように撮り直してください。"
        ),
    },
    "too_bright": {
        "en": (
            "This photo looks overexposed — the label is washed out. Please retake "
            "it with less glare or direct light."
        ),
        "ja": (
            "お写真が露出過多でラベルが白飛びしています。反射や直接光を避けて"
            "撮り直してください。"
        ),
    },
    "blank": {
        "en": (
            "I couldn't find a product in this photo — it looks blank or badly out "
            "of focus. Please retake it with the product label filling the frame."
        ),
        "ja": (
            "お写真から製品を確認できませんでした。何も写っていないか、ピントが"
            "大きく外れているようです。製品ラベルが画面いっぱいに写るように"
            "撮り直してください。"
        ),
    },
    "unreadable": {
        "en": (
            "I couldn't open this image. Please upload a standard photo (JPEG or "
            "PNG) of the product label."
        ),
        "ja": (
            "この画像を開くことができませんでした。製品ラベルを撮影した通常の"
            "写真（JPEGまたはPNG）をアップロードしてください。"
        ),
    },
    "not_a_product": {
        "en": (
            "I couldn't find a skincare product in this photo. Please take a clear "
            "photo of a single product's label."
        ),
        "ja": (
            "お写真からスキンケア製品を確認できませんでした。製品1点のラベルが"
            "はっきり写るように撮影してください。"
        ),
    },
    "multiple_products": {
        "en": (
            "I can see more than one product in this photo. Please photograph one "
            "product at a time so I can analyse its label accurately."
        ),
        "ja": (
            "お写真に複数の製品が写っています。ラベルを正確に分析するため、"
            "1回に1つの製品を撮影してください。"
        ),
    },
}

# Identity exit: the product name wasn't read confidently enough to web-search.
# Format with guess="Brand — Product" (the best available identity read).
CONFIRM_IDENTITY = {
    "en": (
        "I couldn't confidently read this product's name from the photo. "
        "My best guess is '{guess}'. Please confirm the exact brand and "
        "product name, or retake a clearer photo of the front label, so I "
        "can look up its ingredients accurately."
    ),
    "ja": (
        "お写真から製品名をはっきり読み取ることができませんでした。"
        "おそらく「{guess}」かと思われます。成分を正確にお調べするため、"
        "ブランド名と製品名をご確認いただくか、正面ラベルをより鮮明に"
        "撮り直してください。"
    ),
}

# Search exit: identity was confident but no ingredient list was found online.
# Format with name="Brand — Product".
SEARCH_FAILED = {
    "en": (
        "I identified the product as '{name}' but couldn't find a reliable "
        "full ingredient list online. Could you retake a clear photo of the "
        "ingredient list (全成分) on the back label?"
    ),
    "ja": (
        "製品を「{name}」と特定しましたが、信頼できる全成分リストを"
        "オンラインで見つけることができませんでした。背面ラベルの全成分表示を"
        "鮮明に撮り直していただけますか？"
    ),
}
