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
from src.state import AgentState, RoutineFit, UserProfile, inci_names

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

━━ DEVICES / AT-HOME TREATMENTS (only if the profile opts in) ━━
ONLY when the user profile says they are open to devices / at-home treatments,
you MAY add at most one short, optional suggestion for a device or at-home tool
that genuinely complements THIS product (e.g. an LED mask after a soothing
serum, a gua sha with a facial oil for a slip medium, an at-home microneedle
stamp paired with a hydrating serum, an at-home IPL on body areas). Keep it
薬機法-safe (整える / なめらかな印象, never 治療 / medical claims), frame it as
optional ("〜と組み合わせるのもおすすめです" / "you could also pair this with..."),
and never imply the device is required. If the profile does NOT opt in, never
mention devices at all.

━━ ASIAN-TYPE SKIN (only if the profile indicates it) ━━
ONLY when the user profile says the user may have Asian-type skin, weave in
Asian-skin-aware guidance where genuinely relevant, kept 薬機法-safe:
• Asian skin is often more prone to post-inflammatory darkening (くすみ・色むら
  の跡が残りやすい印象) after irritation — favour gentle introduction of strong
  actives (retinoids, exfoliating acids) and emphasise diligent daily sun care
  to help keep an even-looking tone.
• Prefer 明るい印象 / なめらかに整える phrasings; never claim to treat
  pigmentation or "whiten" the skin.
If the profile does NOT indicate Asian-type skin, do not mention it at all.

━━ HOW-TO-APPLY NOTES (application_notes) ━━
Fill application_notes with short, practical cautions about HOW to apply THIS
product — distinct from the risk-focused 'warnings'. Each note is one line, e.g.:
• application surface: "apply to completely dry skin" (e.g. for retinoids/some
  vitamin C) or "apply to slightly damp skin" (humectant layers).
• sequencing / wait times: "wait ~1 minute before the next layer", "let it
  absorb before sunscreen".
• combination cautions: "avoid on the same night as a PM retinoid / strong acid
  if your skin feels irritated".
Keep them 薬機法-safe and specific to this product's type and ingredients. Leave
the list empty if there is nothing special about how to apply it.

━━ TEXTURE & NIGHTTIME FEEL ━━
Some products feel tacky or sticky on the skin — humectant-rich serums/essences
(high glycerin, honey/Mel, large amounts of Sodium Hyaluronate), film-formers,
and heavy occlusive balms. If this product is likely to feel sticky AND you are
recommending PM use, add ONE friendly heads-up warning (not a deterrent): note
that it can feel tacky before bed and suggest letting it absorb for a few
minutes or applying a thinner layer / sealing with a light moisturiser. This is
a comfort tip, NOT a reason to avoid the product — never discourage its use.

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

━━ ROUTINE FIT (only when a "Routine Context" block is provided) ━━
When the user message includes a "Routine Context" block, ALSO fill the
routine_japanese and routine_english cards. Ground EVERY line ONLY in the
findings listed there — never invent a conflict, overlap, or benefit that is
not in the context. If NO Routine Context block is provided, leave both routine
cards completely empty.
• risks      — one line per cross-product CONFLICT listed. Name the existing
               product it clashes with and say why, using 注意が必要です (never
               危険 / 有害). Include EVERY conflict listed; omit none.
• redundancy — gentle overlap notes (役割が重なります / "overlaps with ...");
               state which existing product shares the role. Not alarming.
• value_add  — how this product complements the routine toward a stated goal
               (〜の目標に役立つ可能性があります / "supports..."). Never promise outcomes.
Both routine cards follow the same bilingual rule: 'routine_japanese' entirely
in Japanese, 'routine_english' entirely in English, conveying the same content.

━━ RECOMMENDABILITY SCORE (0–5 leaves) ━━
Score how well THIS product suits THIS user as an integer 0–5, weighing three
things together:
• goals    — does it contain ingredients that genuinely serve the user's goals?
• concerns / skin type — is it appropriate (or risky/irritating) for their skin
             type and conditions?
• budget   — does its likely price band fit the user's monthly budget?
5 = an excellent fit across all three; 3 ≈ a reasonable but imperfect fit; 0 =
poorly suited or risky for this user. Put the integer in 'recommendation_score'
(set ONCE — it is language-independent). In EACH card's
'recommendation_rationale', write ONE short sentence (in that card's language)
explaining the score, naming the main driver (a goal it serves, a concern it
raises, or budget fit). If no user profile is provided, base the score on
general suitability and keep the rationale generic.

━━ ROUTINE INTEGRATION (routine_integration) ━━
Say how the user could actually fit THIS product into their routine: where in
the sequence it goes, which existing products to pair it with or alternate
against, and its AM/PM placement relative to what they already use. When a
"Routine Context" block is provided, name the actual existing products from it;
otherwise describe where it slots into a typical routine. Keep it 薬機法-safe and
never promise outcomes. Fill it in both the Japanese and English cards.

━━ OUTPUT CONTRACT ━━
• ONLY reference ingredients listed in the product context below.
• Do NOT invent benefits not supported by the ingredient list.
• Produce a single recommendation card with exactly these fields:
    product   — "Brand — Product Name" as given in the context.
    recommendation_rationale — ONE sentence justifying the recommendation_score.
    purpose   — ONE sentence on what this product is for.
    warnings  — user-tailored cautions; one concern per item. MUST call out if
                the product can make skin more prone to dehydration or to sun
                damage (raised sun sensitivity). Include the sticky/tacky
                nighttime heads-up here when it applies (as a comfort tip, never
                a deterrent). [] if genuinely none.
    timing    — "AM", "PM", or "AM & PM" per the rules above.
    frequency — e.g. "Daily" or "2–3 times per week".
    application_notes — short how-to-apply / sequencing cautions per the
                "HOW-TO-APPLY NOTES" rules above; [] if nothing special.
    routine_integration — how to slot it into the user's routine per the
                "ROUTINE INTEGRATION" rules above.
• Set 'recommendation_score' once at the top level (0–5), per the score rules.
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
    application_notes: List[str] = Field(
        default_factory=list,
        description=(
            "Short how-to-apply / sequencing cautions, one per item, e.g. "
            "'apply to completely dry skin', 'wait ~1 minute before the next "
            "layer', 'avoid if skin is irritated from a PM retinoid'. Empty if "
            "there is nothing special about how to apply it."
        ),
    )
    recommendation_rationale: str = Field(
        default="",
        description=(
            "ONE short sentence explaining the recommendation_score: why this "
            "product does (or does not) suit this user, citing the main driver "
            "— a goal it serves, a concern/skin-type it raises, or budget fit."
        ),
    )
    routine_integration: str = Field(
        default="",
        description=(
            "One or two sentences on how to slot THIS product into the user's "
            "CURRENT routine: where in the sequence it goes, which existing "
            "products to pair it with or alternate against, and its AM/PM "
            "placement relative to what they already use. Name the actual "
            "existing products when a Routine Context block is provided; "
            "otherwise describe where it fits in a typical routine."
        ),
    )


class RoutineFitCard(BaseModel):
    """How the product fits the user's existing routine, in a single language.

    Populated only when a Routine Context block is provided; otherwise empty.
    """

    risks: List[str] = Field(
        default_factory=list,
        description=(
            "One line per cross-product conflict from the routine context, "
            "naming the existing product. Empty if none."
        ),
    )
    redundancy: List[str] = Field(
        default_factory=list,
        description="Gentle notes that the product overlaps an existing one.",
    )
    value_add: List[str] = Field(
        default_factory=list,
        description="How the product helps an otherwise-uncovered user goal.",
    )


class CoachResponse(BaseModel):
    recommendation_score: int = Field(
        default=0,
        ge=0,
        le=5,
        description=(
            "0–5 leaves: how well THIS product suits THIS user, weighing their "
            "goals (does it contain ingredients that serve them), concerns / "
            "skin type (appropriate or risky), and budget (does its price band "
            "fit). 5 = excellent fit on all three; 0 = poorly suited or risky. "
            "Set once; it is language-independent."
        ),
    )
    japanese: Recommendation = Field(
        description="The card written ONLY in Japanese (敬体, 薬機法-compliant)."
    )
    english: Recommendation = Field(
        description="The same card written ONLY in English."
    )
    routine_japanese: RoutineFitCard = Field(
        default_factory=RoutineFitCard,
        description="Routine-fit notes in Japanese; empty if no routine context.",
    )
    routine_english: RoutineFitCard = Field(
        default_factory=RoutineFitCard,
        description="Routine-fit notes in English; empty if no routine context.",
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

    inci = inci_names(state.get("standardized_ingredients"))
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
    if profile.fitzpatrick is not None:
        roman = ["", "I", "II", "III", "IV", "V", "VI"][profile.fitzpatrick]
        undertone = {"asian": "Asian", "non_asian": "non-Asian"}.get(
            profile.skin_undertone or "", ""
        )
        tone = f" ({undertone} undertone)" if undertone else ""
        lines.append(
            f"  Fitzpatrick phototype: {roman}{tone} — lower types (I–III) burn "
            "more easily and are more prone to sun damage"
        )
    if profile.skin_undertone == "asian":
        lines.append(
            "  May have ASIAN-TYPE skin (picked an Asian-undertone swatch) — apply "
            "the Asian-skin guidance: introduce strong actives gently and "
            "emphasise sun care to help keep an even-looking tone"
        )
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
    if profile.consider_devices:
        lines.append(
            "  Open to devices / at-home treatments (LED masks, at-home IPL, "
            "microneedle stamps, gua sha, etc.) — may suggest these to enrich "
            "the routine where genuinely complementary"
        )
    if profile.budget is not None:
        amount = "$250+/month" if profile.budget >= 250 else f"${profile.budget}/month"
        lines.append(f"  Monthly budget: {amount} (factor product selection to fit)")

    return "\n".join(lines)


def _has_routine_findings(fit: Optional[RoutineFit]) -> bool:
    return bool(fit and (fit.conflicts or fit.redundancy or fit.value_add))


def _routine_context(fit: Optional[RoutineFit]) -> str:
    """Grounding block describing the new product vs the user's saved routine.

    Returns "" when there is nothing to report, so the coach can omit the whole
    Routine Fit section (and tell the model to leave the routine cards empty).
    """
    if not _has_routine_findings(fit):
        return ""

    lines = ["## Routine Context (the user's CURRENT routine — ground every routine line in these findings ONLY)"]
    if fit.existing_products:
        lines.append("Current products: " + "; ".join(fit.existing_products))
    if fit.conflicts:
        lines.append(
            "Cross-product CONFLICTS (surface EVERY one as a risk line, both languages):"
        )
        for c in fit.conflicts:
            lines.append(
                f"  • [{c.severity.upper()}] new product's {c.groups[0]} vs "
                f"{c.with_product}'s {c.groups[1]}: {c.reason}"
            )
    if fit.redundancy:
        lines.append("Redundancy candidates (phrase as gentle overlap notes):")
        lines.extend(f"  • {r}" for r in fit.redundancy)
    if fit.value_add:
        lines.append("Value-add candidates (phrase as how it complements the goal):")
        lines.extend(f"  • {v}" for v in fit.value_add)
    return "\n".join(lines)


def _pregnancy_cautions(
    state: AgentState, profile: Optional[UserProfile]
) -> Tuple[List[str], List[str]]:
    """Deterministic pregnancy flags as (japanese, english) caution lists."""
    if profile is None or not profile.is_pregnant:
        return [], []
    present = set(inci_names(state.get("standardized_ingredients")))
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
    present = set(inci_names(state.get("standardized_ingredients")))
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


# Field labels + "none" placeholder per language, hoisted so the renderers don't
# rebuild these tables on every call.
_REC_LABELS = {
    "ja": ("製品", "用途", "注意事項", "使用タイミング", "使用頻度", "ルーティンへの取り入れ方"),
    "en": ("Product", "Purpose", "Warnings", "Best timing", "Frequency", "Fitting it into your routine"),
}
_FIT_LABELS = {
    "ja": ("リスク", "重複", "追加価値"),
    "en": ("Risks", "Redundancy", "Adds value"),
}
_NONE_TEXT = {"ja": "特になし", "en": "None"}


def _render_recommendation(
    card: Recommendation, lang: str, extra_warnings: List[str]
) -> str:
    """Render one single-language Recommendation as the recommendation card."""
    prod_l, purp_l, warn_l, time_l, freq_l, fit_l = _REC_LABELS[lang]
    warnings = extra_warnings + card.warnings

    none_text = _NONE_TEXT[lang]
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
    if card.routine_integration:
        lines.append(f"6. {fit_l}: {card.routine_integration}")
    return "\n".join(lines)


def _render_routine_fit(card: RoutineFitCard, lang: str) -> str:
    """Render one single-language routine-fit card (risks / redundancy / value)."""
    risk_l, red_l, val_l = _FIT_LABELS[lang]
    none_text = _NONE_TEXT[lang]

    lines: List[str] = []
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

    routine_fit: Optional[RoutineFit] = state.get("routine_fit")
    routine_context = _routine_context(routine_fit)

    human_prompt = (
        f"## Product Analysis\n{_product_context(state)}\n\n"
        f"## {_user_context(profile, user_name)}\n\n"
        "Fill the recommendation card for this product and user: the product "
        "name (brand + product name), a 0–5 recommendability score with a "
        "one-sentence rationale, its purpose in one sentence, user-tailored "
        "warnings (including dehydration or sun-sensitivity risk where "
        "relevant), the best timing (AM / PM / AM & PM), the use frequency, and "
        "how to fit it into the user's routine. Produce the WHOLE card twice: "
        "once entirely in Japanese ('japanese'), once entirely in English "
        "('english'), and set 'recommendation_score' once."
    )
    if routine_context:
        human_prompt += (
            f"\n\n{routine_context}\n\n"
            "ALSO fill the routine_japanese and routine_english cards from the "
            "Routine Context above (risks, redundancy, value_add), grounded only "
            "in those findings."
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

    # Routine Fit section (only when there is a routine to compare against).
    if routine_context:
        rf_ja = _render_routine_fit(response.routine_japanese, "ja")
        rf_en = _render_routine_fit(response.routine_english, "en")
        coach_advice += (
            "\n\n" + "=" * 60 + "\n\n"
            "【ルーティン適合 / Routine Fit】\n\n"
            "[日本語]\n" + rf_ja + "\n\n"
            "[English]\n" + rf_en
        )

    # Recommendability score (0–5) only makes sense against a user's goals /
    # concerns / budget, so it is suppressed for anonymous scans.
    if profile is not None:
        reco_score: Optional[int] = max(0, min(5, response.recommendation_score))
        reco_rationale: Optional[str] = en.recommendation_rationale or None
    else:
        reco_score = None
        reco_rationale = None

    # Machine-readable card keeps the English fields for downstream consumers.
    all_warnings_en = extra_en + en.warnings
    recommendations: List[str] = (
        [f"[PRODUCT] {en.product}"]
        + ([f"[SCORE] {reco_score}/5"] if reco_score is not None else [])
        + [f"[PURPOSE] {en.purpose}"]
        + [f"[WARNING] {w}" for w in all_warnings_en]
        + [f"[TIMING] {en.timing}"]
        + [f"[FREQUENCY] {en.frequency}"]
        + ([f"[ROUTINE-INTEGRATION] {en.routine_integration}"] if en.routine_integration else [])
    )

    # Deterministic routine findings, always emitted regardless of LLM phrasing,
    # so the machine-readable trace never drops a cross-product risk.
    if _has_routine_findings(routine_fit):
        recommendations += [
            f"[ROUTINE-RISK] {c.severity.upper()} vs {c.with_product} "
            f"({c.groups[0]} ↔ {c.groups[1]}): {c.reason}"
            for c in routine_fit.conflicts
        ]
        recommendations += [f"[ROUTINE-REDUNDANCY] {r}" for r in routine_fit.redundancy]
        recommendations += [f"[ROUTINE-VALUE] {v}" for v in routine_fit.value_add]

    report = state["safety_report"]
    logging.info(
        "Coach: score=%.2f, timing=%s, frequency=%s, %d warning(s).",
        report.safety_score,
        en.timing,
        en.frequency,
        len(all_warnings_en),
    )

    # Structured English card persisted onto the shelf row when the scan is saved
    # to the routine (timing + how-to-apply notes + risk warnings).
    coach_card = {
        "timing": en.timing,
        "application_notes": list(en.application_notes),
        "warnings": all_warnings_en,
    }

    return {
        "coach_advice": coach_advice,
        "routine_recommendations": recommendations,
        "coach_card": coach_card,
        "recommendation_score": reco_score,
        "recommendation_rationale": reco_rationale,
    }
