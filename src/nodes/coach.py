# Coach node: generates personalised, 薬機法-safe routine advice from the audit.
#
# Receives the safety_report from the auditor and the user_profile from state.
# Calls Gemini Flash with a tightly constrained system prompt that:
#   (a) enforces 薬機法-compliant language throughout, and
#   (b) restricts the model to only discussing ingredients that are actually
#       present in the product — no invented benefits.
import logging
from typing import List, Optional, Tuple, cast

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from src.config import FLASH_MODEL
from src.state import AgentState, UserProfile

# Ingredients that are contraindicated during pregnancy / breastfeeding.
_PREGNANCY_FLAGGED_INCI = {
    "Retinol",
    "Salicylic Acid",
    "Benzoyl Peroxide",
    "Glycolic Acid",
    "Lactic Acid",
}

_SYSTEM_PROMPT = """
You are a Japanese skincare specialist assistant providing cosmetics usage guidance.

━━ VOICE ━━
Write like a knowledgeable friend, not a pamphlet. Be warm, specific, and concise.
No filler sentences, no generic platitudes ("everyone's skin is different",
"consistency is key"). Every sentence must carry real, product-specific information.

━━ 薬機法 COMPLIANCE — MANDATORY ━━
You advise on COSMETICS only, not pharmaceuticals or medical treatments.

PROHIBITED:
• Claims to treat, cure, prevent, or improve any disease or clinical condition
• 治す / 治療する / 病気 / 治癒 / 根治
• Absolute guarantees: "will eliminate wrinkles", "permanently clears acne"
• Implying cellular or genetic structural change

REQUIRED — use only compliant phrasings:
• エイジングケア成分 (aging-care ingredient) — never 抗老化
• 肌を整える / helps maintain the appearance of skin
• うるおいを与える / provides moisture to the skin's surface
• 明るい印象の肌へ / for a brighter-looking complexion
• 肌をなめらかに整える / helps smooth the appearance of skin texture
• 〜をサポートする / supports the look or feel of...
• 注意が必要です / caution is advised (for risks — never 危険 or 有害)

PREGNANCY — STRICT:
• Mention pregnancy or breastfeeding ONLY if the user profile explicitly states
  the user is pregnant or breastfeeding. The system adds that caution separately.
• NEVER raise pregnancy speculatively ("if you become pregnant…"), and NEVER
  infer or hint at it from the user's age or gender. Assuming or alluding to a
  woman's pregnancy status unprompted is disrespectful — do not do it.
• When the profile DOES indicate pregnancy, the compliant caution is:
  妊娠中・授乳中の方は医師にご相談の上ご使用ください

━━ SKIN TYPE → BEHAVIOUR ━━
Adapt texture, layering, and frequency to the user's skin type:
• dry         → lean on humectants + occlusives; layer onto damp skin; richer
                textures; avoid high-alcohol products that can feel stripping.
• oily        → favour lightweight/gel textures; don't over-cleanse (can trigger
                rebound oiliness); go easy on heavy occlusives.
• combination → zone it: lighter application on the T-zone, more nourishing on
                the cheeks.
• normal      → maintain balance; focus on barrier upkeep and sun protection.
• sensitive   → prefer fragrance-free; introduce one new active at a time; patch
                test first; be cautious with essential oils and fragrance components.

━━ GOALS → INGREDIENTS (cite only ones actually in the product) ━━
Connect the user's goals to ingredients PRESENT in this product. Never promise outcomes.
• brightening    → Niacinamide, Ascorbic Acid & derivatives (Ascorbyl Glucoside,
                   Magnesium Ascorbyl Phosphate, Tetrahexyldecyl Ascorbate) → 明るい印象の肌へ
• anti_aging / エイジングケア → Retinol, peptides (Palmitoyl/Acetyl...), Niacinamide,
                   antioxidants (Tocopherol) → 肌を整える, ハリのある印象
• hydration      → Sodium Hyaluronate, Glycerin, Ceramides, Panthenol, Squalane → うるおいを与える
• acne_control   → Salicylic Acid, Niacinamide; lightweight textures; keep wording to
                   肌を清潔に保つ / clear-LOOKING skin (never "treats acne")
• barrier_repair → Ceramides, Panthenol, Phytosterols, fatty alcohols; avoid stacking exfoliants
If the product contains nothing relevant to a stated goal, say so honestly rather
than inventing a benefit.

━━ SCOPE ━━
• ONLY reference ingredients listed in the product context below.
• Do NOT invent benefits not supported by the ingredient list.
• TWO COMPLETE VERSIONS — produce the entire advice twice:
    'japanese': every field written ONLY in Japanese (敬体, 薬機法-compliant).
    'english':  the SAME advice written ONLY in English.
  Each version is self-contained: do NOT mix languages within a field. The two
  versions must convey the same content, just in different languages.
""".strip()


class AdviceBlock(BaseModel):
    """One complete set of advice, written entirely in a single language."""

    summary: str = Field(
        default="",
        description=(
            "A personalised opening (2-4 sentences) shown before the routine. "
            "It MUST: (1) name the scanned product (brand + product name); "
            "(2) state in one sentence what this product is for / its purpose; "
            "(3) say whether it is a good fit for THIS user, explicitly citing the "
            "user's name and their relevant traits (skin type, goals, pregnancy, "
            "skin conditions) so they can see their profile was considered. "
            "Address the user by name. Never promise outcomes or use medical claims."
        ),
    )
    am_steps: List[str] = Field(
        default_factory=list,
        description="Ordered AM routine steps showing where THIS product fits.",
    )
    pm_steps: List[str] = Field(
        default_factory=list,
        description=(
            "Ordered PM routine steps. Flag PM-only constraints "
            "(photosensitising citrus oils, retinoids)."
        ),
    )
    cautions: List[str] = Field(
        default_factory=list,
        description=(
            "User-profile-specific cautions (skin conditions, conflicts, "
            "sensitivity). One concern per item."
        ),
    )
    tips: List[str] = Field(
        default_factory=list,
        description=(
            "3-5 practical tips for this user's skin type, goals, routine "
            "time, and budget."
        ),
    )


class CoachResponse(BaseModel):
    japanese: AdviceBlock = Field(
        description="The complete advice written ONLY in Japanese (敬体, 薬機法-compliant)."
    )
    english: AdviceBlock = Field(
        description="The same complete advice written ONLY in English."
    )


def _product_context(state: AgentState) -> str:
    lines: List[str] = []

    data = state.get("extracted_data")
    if data:
        lines.append(f"Product: {data.brand} — {data.product_name}")
        if data.is_quasi_drug:
            lines.append(
                "Classification: 医薬部外品 (quasi-drug; contains regulated active ingredients)"
            )

    ingredients = state.get("standardized_ingredients") or []
    inci = [i["name_standardized"] for i in ingredients if i.get("name_standardized")]
    if inci:
        lines.append(f"Verified INCI ingredients ({len(inci)}): {', '.join(inci)}")

    unmatched = state.get("unmatched_ingredients") or []
    if unmatched:
        lines.append(f"Unverified (no INCI mapping): {', '.join(unmatched)}")

    report = state.get("safety_report")
    if report:
        lines.append(f"Safety score: {report.safety_score:.2f} / 1.00")
        if report.ingredient_conflicts:
            lines.append("Ingredient conflicts detected:")
            for c in report.ingredient_conflicts:
                lines.append(f"  • {c}")
        if report.risk_ingredients:
            lines.append(f"Individual risk flags: {', '.join(report.risk_ingredients)}")
        if not report.ingredient_conflicts and not report.risk_ingredients:
            lines.append("No ingredient conflicts or risk flags detected.")

    return "\n".join(lines)


def _user_context(profile: Optional[UserProfile], name: Optional[str]) -> str:
    if profile is None:
        return (
            "User profile: not provided — "
            "give general-purpose advice suitable for all skin types. "
            "No name is available, so address the user generically."
        )

    lines = ["User profile:"]
    lines.append(f"  Name: {name}" if name else "  Name: (not provided)")
    if profile.skin_type:
        lines.append(f"  Skin type: {profile.skin_type}")
    if profile.age is not None:
        lines.append(f"  Age: {profile.age}")
    if profile.gender:
        lines.append(f"  Gender: {profile.gender}")
    if profile.goals:
        lines.append(f"  Goals: {', '.join(profile.goals)}")
    if profile.is_pregnant:
        lines.append(
            "  PREGNANT OR BREASTFEEDING — apply all pregnancy safety restrictions"
        )
    if profile.skin_conditions:
        lines.append(f"  Skin conditions: {', '.join(profile.skin_conditions)}")
    if profile.sun_damage_history and profile.sun_damage_history != "none":
        lines.append(f"  Sun damage history: {profile.sun_damage_history}")
    if profile.routine_time:
        lines.append(f"  Routine time available: {profile.routine_time}")
    if profile.budget:
        lines.append(f"  Budget: {profile.budget}")

    return "\n".join(lines)


def _pregnancy_cautions(
    state: AgentState, profile: Optional[UserProfile]
) -> Tuple[List[str], List[str]]:
    """Deterministic pregnancy flags as (japanese, english) caution lists."""
    if profile is None or not profile.is_pregnant:
        return [], []
    present = {
        i["name_standardized"]
        for i in (state.get("standardized_ingredients") or [])
        if i.get("name_standardized")
    }
    flagged = sorted(present & _PREGNANCY_FLAGGED_INCI)
    consult = "妊娠中・授乳中の方は医師にご相談の上ご使用ください。"
    if flagged:
        ja = [
            f"妊娠中の注意: {', '.join(flagged)} は妊娠中・授乳期のご使用は"
            f"お控えください。{consult}"
        ]
        en = [
            f"Pregnancy caution: {', '.join(flagged)} should be avoided during "
            "pregnancy and breastfeeding. Please consult a doctor before use."
        ]
        return ja, en
    return [consult], [
        "If you are pregnant or breastfeeding, please consult a doctor before use."
    ]


# Section headers per language: (am, pm, cautions, tips).
_HEADERS = {
    "ja": ("朝のお手入れ", "夜のお手入れ", "注意事項", "アドバイス"),
    "en": ("AM Routine", "PM Routine", "Cautions", "Tips"),
}


def _render_block(block: AdviceBlock, lang: str, extra_cautions: List[str]) -> str:
    """Render one single-language AdviceBlock into a printable section."""
    am_h, pm_h, caut_h, tips_h = _HEADERS[lang]
    cautions = extra_cautions + block.cautions

    sections: List[str] = []
    if block.summary.strip():
        sections.append(block.summary.strip())
    sections.append(
        f"{am_h}:\n"
        + "\n".join(f"  {i}. {s}" for i, s in enumerate(block.am_steps, 1))
    )
    sections.append(
        f"{pm_h}:\n"
        + "\n".join(f"  {i}. {s}" for i, s in enumerate(block.pm_steps, 1))
    )
    if cautions:
        sections.append(f"{caut_h}:\n" + "\n".join(f"  • {c}" for c in cautions))
    if block.tips:
        sections.append(f"{tips_h}:\n" + "\n".join(f"  • {t}" for t in block.tips))
    return "\n\n".join(sections)


def coach_node(state: AgentState) -> dict:
    if state.get("safety_report") is None:
        logging.warning("Coach reached without safety_report — returning placeholder.")
        return {
            "coach_advice": (
                "Safety audit data unavailable; "
                "unable to generate personalised advice."
            ),
            "routine_recommendations": [],
        }

    profile: Optional[UserProfile] = state.get("user_profile")
    user_name = state.get("user_name")
    preg_ja, preg_en = _pregnancy_cautions(state, profile)

    human_prompt = (
        f"## Product Analysis\n{_product_context(state)}\n\n"
        f"## {_user_context(profile, user_name)}\n\n"
        "Write a personalised 'summary' opening that names the scanned product, "
        "states its purpose in one sentence, and tells the user whether it suits "
        "them — citing their name and relevant traits. Then provide AM routine "
        "advice, PM routine advice, user-specific cautions, and practical tips. "
        "Produce the WHOLE thing twice: once entirely in Japanese ('japanese'), "
        "once entirely in English ('english')."
    )

    model = ChatGoogleGenerativeAI(model=FLASH_MODEL, temperature=0.2)
    response: CoachResponse = cast(
        CoachResponse,
        model.with_structured_output(CoachResponse).invoke(
            [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=human_prompt)]
        ),
    )

    ja, en = response.japanese, response.english

    # Japanese version in full, then a separator, then the English version.
    ja_text = _render_block(ja, "ja", preg_ja)
    en_text = _render_block(en, "en", preg_en)
    coach_advice = (
        "【日本語】\n" + ja_text + "\n\n" + "=" * 60 + "\n\n"
        "【English】\n" + en_text
    )

    # Machine-readable list keeps the English steps for downstream consumers.
    all_cautions_en = preg_en + en.cautions
    recommendations: List[str] = (
        [f"[AM] {s}" for s in en.am_steps]
        + [f"[PM] {s}" for s in en.pm_steps]
        + all_cautions_en
        + en.tips
    )

    report = state["safety_report"]
    logging.info(
        "Coach: score=%.2f, %d AM / %d PM step(s), %d caution(s), %d tip(s).",
        report.safety_score,
        len(en.am_steps),
        len(en.pm_steps),
        len(all_cautions_en),
        len(en.tips),
    )

    return {
        "coach_advice": coach_advice,
        "routine_recommendations": recommendations,
    }
