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

# Drying / barrier-stripping agents — flag a dehydration caution when present.
_DRYING_INCI = {
    "Alcohol Denat.",
    "Isopropyl Alcohol",
    "SD Alcohol 40-B",
    "Ethanol",
    "Sodium Lauryl Sulfate",
}

# Actives that raise sun sensitivity (or are phototoxic) — flag a sun-damage
# caution and a daily-SPF reminder when present.
_PHOTOSENSITISING_INCI = {
    "Retinol",
    "Glycolic Acid",
    "Lactic Acid",
    "Salicylic Acid",
    "Citrus Aurantium Bergamia (Bergamot) Fruit Oil",
    "Citrus Limon (Lemon) Peel Oil",
    "Citrus Aurantifolia (Lime) Oil",
    "Citrus Aurantium Dulcis (Orange) Peel Oil",
    "Citrus Aurantium Dulcis (Orange) Oil",
    "Citrus Junos Fruit Extract",
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

━━ TIMING (AM / PM / AM & PM) ━━
Decide when this product is best used, from its type and ingredients:
• PM-leaning: Retinol/retinoids, AHA (Glycolic/Lactic Acid), BHA (Salicylic
  Acid), and other exfoliating or photosensitising actives — they degrade in
  light and/or raise sun sensitivity, so favour night use.
• AM-leaning: sunscreens / SPF day products, antioxidant serums worn under SPF.
• AM & PM: gentle daily steps — cleansers, hydrating toners, moisturisers,
  ceramide/hyaluronic-acid products with no photosensitising actives.
Output exactly one of: "AM", "PM", or "AM & PM".

━━ FREQUENCY (X times per week) ━━
Recommend how often to use it:
• Strong actives (retinoids, exfoliating acids) → start low, e.g.
  "2–3 times per week", building up as tolerated.
• Daily-safe products (moisturiser, sunscreen, gentle cleanser, hydrating
  toner) → "Daily" (sunscreen: every morning).
Be concrete; never say "as needed" without a number or "Daily".

━━ OUTPUT CONTRACT ━━
• ONLY reference ingredients listed in the product context below.
• Do NOT invent benefits not supported by the ingredient list.
• Produce a single recommendation card with exactly these fields:
    product   — "Brand — Product Name" as given in the context.
    purpose   — ONE sentence on what this product is for.
    warnings  — user-tailored cautions; one concern per item. MUST call out if
                the product can make skin more prone to dehydration or to sun
                damage (raised sun sensitivity). [] if genuinely none.
    timing    — "AM", "PM", or "AM & PM" per the rules above.
    frequency — e.g. "Daily" or "2–3 times per week".
• TWO COMPLETE VERSIONS — fill the card twice:
    'japanese': every field written ONLY in Japanese (敬体, 薬機法-compliant).
    'english':  the SAME card written ONLY in English.
  Each version is self-contained: do NOT mix languages within a field. Both
  versions must convey the same content; 'timing' stays "AM"/"PM"/"AM & PM"
  in both.
""".strip()


class Recommendation(BaseModel):
    """One complete recommendation card, written entirely in a single language."""

    product: str = Field(
        default="",
        description="The scanned product as 'Brand — Product Name'.",
    )
    purpose: str = Field(
        default="",
        description="ONE sentence describing what this product is intended for.",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description=(
            "User-tailored cautions, one concern per item. MUST flag if the "
            "product can make skin more prone to dehydration or sun damage. "
            "Empty list if there are genuinely none."
        ),
    )
    timing: str = Field(
        default="",
        description="Best time to use: exactly 'AM', 'PM', or 'AM & PM'.",
    )
    frequency: str = Field(
        default="",
        description="How often to use, e.g. 'Daily' or '2–3 times per week'.",
    )


class CoachResponse(BaseModel):
    japanese: Recommendation = Field(
        description="The card written ONLY in Japanese (敬体, 薬機法-compliant)."
    )
    english: Recommendation = Field(
        description="The same card written ONLY in English."
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


def _dehydration_sun_flags(state: AgentState) -> Tuple[List[str], List[str]]:
    """Deterministic dehydration + sun-damage cautions as (japanese, english).

    These are the safety-critical warnings the user specifically asked for, so
    they are derived from the ingredient list rather than left to the model.
    """
    present = {
        i["name_standardized"]
        for i in (state.get("standardized_ingredients") or [])
        if i.get("name_standardized")
    }
    ja: List[str] = []
    en: List[str] = []

    drying = sorted(present & _DRYING_INCI)
    if drying:
        ja.append(
            f"乾燥に注意: {', '.join(drying)} を含むため、肌のうるおいが奪われ"
            "やすくなることがあります。保湿を十分に行ってください。"
        )
        en.append(
            f"Dehydration caution: contains {', '.join(drying)}, which can leave "
            "skin more prone to dehydration — follow with good moisturisation."
        )

    photo = sorted(present & _PHOTOSENSITISING_INCI)
    if photo:
        ja.append(
            f"紫外線に注意: {', '.join(photo)} は日中の紫外線に対する肌の"
            "敏感さを高めることがあります。日中は毎日の日焼け止めをご使用ください。"
        )
        en.append(
            f"Sun-sensitivity caution: {', '.join(photo)} can make skin more "
            "prone to sun damage — wear a daily SPF."
        )
    return ja, en


def _render_recommendation(
    card: Recommendation, lang: str, extra_warnings: List[str]
) -> str:
    """Render one single-language Recommendation as the 5-point card."""
    labels = {
        "ja": ("製品", "用途", "注意事項", "使用タイミング", "使用頻度"),
        "en": ("Product", "Purpose", "Warnings", "Best timing", "Frequency"),
    }[lang]
    prod_l, purp_l, warn_l, time_l, freq_l = labels
    warnings = extra_warnings + card.warnings

    none_text = "特になし" if lang == "ja" else "None"
    lines = [
        f"1. {prod_l}: {card.product}",
        f"2. {purp_l}: {card.purpose}",
    ]
    if warnings:
        lines.append(f"3. {warn_l}:")
        lines.extend(f"   • {w}" for w in warnings)
    else:
        lines.append(f"3. {warn_l}: {none_text}")
    lines.append(f"4. {time_l}: {card.timing}")
    lines.append(f"5. {freq_l}: {card.frequency}")
    return "\n".join(lines)


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
    sun_ja, sun_en = _dehydration_sun_flags(state)
    extra_ja = preg_ja + sun_ja
    extra_en = preg_en + sun_en

    human_prompt = (
        f"## Product Analysis\n{_product_context(state)}\n\n"
        f"## {_user_context(profile, user_name)}\n\n"
        "Fill the recommendation card for this product and user: the product "
        "name (brand + product name), its purpose in one sentence, "
        "user-tailored warnings (including dehydration or sun-sensitivity risk "
        "where relevant), the best timing (AM / PM / AM & PM), and the use "
        "frequency. Produce the WHOLE card twice: once entirely in Japanese "
        "('japanese'), once entirely in English ('english')."
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
    ja_text = _render_recommendation(ja, "ja", extra_ja)
    en_text = _render_recommendation(en, "en", extra_en)
    coach_advice = (
        "【日本語】\n" + ja_text + "\n\n" + "=" * 60 + "\n\n"
        "【English】\n" + en_text
    )

    # Machine-readable card keeps the English fields for downstream consumers.
    all_warnings_en = extra_en + en.warnings
    recommendations: List[str] = (
        [f"[PRODUCT] {en.product}"]
        + [f"[PURPOSE] {en.purpose}"]
        + [f"[WARNING] {w}" for w in all_warnings_en]
        + [f"[TIMING] {en.timing}"]
        + [f"[FREQUENCY] {en.frequency}"]
    )

    report = state["safety_report"]
    logging.info(
        "Coach: score=%.2f, timing=%s, frequency=%s, %d warning(s).",
        report.safety_score,
        en.timing,
        en.frequency,
        len(all_warnings_en),
    )

    return {
        "coach_advice": coach_advice,
        "routine_recommendations": recommendations,
    }
