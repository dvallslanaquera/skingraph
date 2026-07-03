# Text renderers for the coach's structured cards.
#
# Only the CLI (run_pipeline.py) renders the cards to text; the API returns the
# structured CoachResponse as-is and the web UI lays it out itself.

from src.state import CoachResponse, Recommendation, RoutineFitCard

# Field labels + "none" placeholder per language, hoisted so the renderers don't
# rebuild these tables on every call.
_REC_LABELS = {
    "ja": (
        "製品",
        "用途",
        "注意事項",
        "使用タイミング",
        "使用頻度",
        "使い方のポイント",
        "ルーティンへの取り入れ方",
    ),
    "en": (
        "Product",
        "Purpose",
        "Warnings",
        "Best timing",
        "Frequency",
        "How to apply",
        "Fitting it into your routine",
    ),
}
_FIT_LABELS = {
    "ja": ("リスク", "重複", "追加価値"),
    "en": ("Risks", "Redundancy", "Adds value"),
}
_NONE_TEXT = {"ja": "特になし", "en": "None"}


def render_recommendation(card: Recommendation, lang: str) -> str:
    """Render one single-language Recommendation card: verdict first, then details."""
    prod_l, purp_l, warn_l, time_l, freq_l, notes_l, fit_l = _REC_LABELS[lang]
    none_text = _NONE_TEXT[lang]

    lines: list[str] = []
    if card.verdict:
        lines += [card.verdict, ""]
    lines.append(f"{prod_l}: {card.product}")
    lines.append(f"{purp_l}: {card.purpose}")
    if card.warnings:
        lines.append(f"{warn_l}:")
        lines.extend(f"  • {w}" for w in card.warnings)
    else:
        lines.append(f"{warn_l}: {none_text}")
    lines.append(f"{time_l}: {card.timing}")
    lines.append(f"{freq_l}: {card.frequency}")
    if card.application_notes:
        lines.append(f"{notes_l}:")
        lines.extend(f"  • {n}" for n in card.application_notes)
    if card.routine_integration:
        lines.append(f"{fit_l}: {card.routine_integration}")
    return "\n".join(lines)


def render_routine_fit(card: RoutineFitCard, lang: str) -> str:
    """Render one single-language routine-fit card (risks / redundancy / value)."""
    risk_l, red_l, val_l = _FIT_LABELS[lang]
    none_text = _NONE_TEXT[lang]

    lines: list[str] = []
    for label, items in (
        (risk_l, card.risks),
        (red_l, card.redundancy),
        (val_l, card.value_add),
    ):
        if items:
            lines.append(f"{label}:")
            lines.extend(f"  • {x}" for x in items)
        else:
            lines.append(f"{label}: {none_text}")
    return "\n".join(lines)


def _has_findings(card: RoutineFitCard) -> bool:
    return bool(card.risks or card.redundancy or card.value_add)


def render_coach_cards(cards: CoachResponse) -> str:
    """Combined bilingual text block for the CLI: Japanese card, then English."""
    ja = render_recommendation(cards.japanese, "ja")
    en = render_recommendation(cards.english, "en")
    if _has_findings(cards.routine_japanese):
        ja += (
            "\n\n"
            + "─" * 40
            + "\n【ルーティン適合】\n"
            + render_routine_fit(cards.routine_japanese, "ja")
        )
    if _has_findings(cards.routine_english):
        en += (
            "\n\n"
            + "─" * 40
            + "\n【Routine Fit】\n"
            + render_routine_fit(cards.routine_english, "en")
        )
    return "【日本語】\n" + ja + "\n\n" + "=" * 60 + "\n\n【English】\n" + en
