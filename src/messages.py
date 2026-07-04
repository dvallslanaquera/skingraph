# Bilingual (en/ja) copy for the graceful-exit paths: the retake bounces from
# graph.py and the identity/search exits from the websearch nodes. Every entry
# carries both languages; the nodes wrap them in a state.Notice so the UI can
# render the one matching its locale.

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
            "お写真が露出過多でラベルが白飛びしています。反射や直接光を避けて撮り直してください。"
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
    "blurry": {
        "en": (
            "This photo is too blurry to read — the text has no sharp detail. "
            "Please hold the camera steady, tap to focus on the label, and "
            "retake the photo."
        ),
        "ja": (
            "お写真のピントが大きく外れており、文字を読み取ることができません。"
            "カメラを安定させ、ラベルにピントを合わせて撮り直してください。"
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
    "non_skincare_product": {
        "en": (
            "This looks like a product, but not a skincare one — I can only "
            "analyse skincare (cleansers, toners, serums, moisturizers, "
            "sunscreens, masks and similar). Please photograph a skincare "
            "product's label."
        ),
        "ja": (
            "製品は写っていますが、スキンケア製品ではないようです。分析できるのは"
            "スキンケア製品（洗顔料・化粧水・美容液・保湿剤・日焼け止め・マスク等）"
            "のみです。スキンケア製品のラベルを撮影してください。"
        ),
    },
    "low_confidence": {
        "en": (
            "I couldn't tell with confidence what this photo shows. Please "
            "retake it with the single product filling the frame, in good "
            "light and with the label facing the camera."
        ),
        "ja": (
            "お写真に何が写っているかを十分な確度で判定できませんでした。"
            "明るい場所で、製品1点がラベルを正面に向けて画面いっぱいに写るように"
            "撮り直してください。"
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

# Web-mismatch exit: a list was found online but it belongs to a different
# product than the one read off the photo — never audit the wrong ingredients.
# Format with guess="Brand — Product" (the identity read off the photo).
WEB_MISMATCH = {
    "en": (
        "I read this product as '{guess}', but the ingredient list I found "
        "online belongs to a different product, so I didn't use it. Please "
        "confirm the exact brand and product name — or photograph the "
        "ingredient list (全成分) on the back label, which is the most "
        "reliable option."
    ),
    "ja": (
        "製品を「{guess}」と読み取りましたが、オンラインで見つかった全成分リストは"
        "別の製品のものだったため、使用しませんでした。正確なブランド名と製品名を"
        "ご確認いただくか、最も確実な方法として、背面ラベルの全成分表示を"
        "撮影してください。"
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

# Defensive coach exit: the coach node was reached without a safety report, so
# no grounded advice can be generated (should not happen via the normal graph).
COACH_UNAVAILABLE = {
    "en": "Safety audit data unavailable; unable to generate personalised advice.",
    "ja": (
        "安全性監査データが取得できなかったため、パーソナライズされた"
        "アドバイスを生成できませんでした。"
    ),
}
