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

from src.config import FLASH_MODEL
from src.state import (AgentState, CoachResponse, RoutineFit, UserProfile,
                       inci_names)

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

━━ VERDICT (the headline) ━━
Open the card with 'verdict': 1–2 sentences giving your overall call on this
product for THIS user — a knowledgeable friend's bottom line, e.g. "Nice pick
for your dry skin — just keep it to evenings and wear SPF the next morning."
Name the main reason it does (or doesn't) suit them and the single most
important caution, if any. Warm and specific; no hedging boilerplate, and do
not repeat the full warnings list. 薬機法-safe like everything else.

━━ OUTPUT CONTRACT ━━
• ONLY reference ingredients listed in the product context below.
• Do NOT invent benefits not supported by the ingredient list.
• Produce a single recommendation card with exactly these fields:
    verdict   — the 1–2 sentence headline per the VERDICT rules above.
    product   — "Brand — Product Name" as given in the context.
    recommendation_rationale — ONE sentence justifying the recommendation_score.
    purpose   — ONE sentence on what this product is for.
    warnings  — user-tailored cautions; one concern per item, ORDERED BY
                IMPORTANCE to this user — the first three must be the ones they
                genuinely need to know. MUST call out if the product can make
                skin more prone to dehydration or to sun damage (raised sun
                sensitivity). Include the sticky/tacky nighttime heads-up here
                when it applies (as a comfort tip, never a deterrent). [] if
                genuinely none.
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


def coach_node(state: AgentState) -> dict:
    if state.get("safety_report") is None:
        logging.warning("Coach reached without safety_report — returning placeholder.")
        return {
            "coach_advice": (
                "Safety audit data unavailable; "
                "unable to generate personalised advice."
            ),
            "coach_cards": None,
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

    # Parity with the scanner/websearch nodes: bound the Gemini call so a hung
    # request can never keep the pipeline (and thus the HTTP request) open
    # indefinitely. The coach's structured-output call is the slowest step, so an
    # unbounded call here is what tipped the old single-shot /scan past the
    # platform's request ceiling.
    model = ChatGoogleGenerativeAI(
        model=FLASH_MODEL, temperature=0.2, timeout=120, max_retries=3
    )
    response: CoachResponse = cast(
        CoachResponse,
        model.with_structured_output(CoachResponse).invoke(
            [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=human_prompt)]
        ),
    )

    ja, en = response.japanese, response.english

    # The deterministic safety cautions (pregnancy / dehydration / sun) lead
    # each card's warnings: they are computed by the system, never left to the
    # model's discretion, and they are what the user most needs to see first.
    ja.warnings = extra_ja + ja.warnings
    en.warnings = extra_en + en.warnings

    # The 0–5 recommendability score only makes sense against a user's goals /
    # concerns / budget, so it (and its rationale) is cleared for anonymous scans.
    if profile is not None:
        response.recommendation_score = max(0, min(5, response.recommendation_score or 0))
    else:
        response.recommendation_score = None
        ja.recommendation_rationale = ""
        en.recommendation_rationale = ""

    report = state["safety_report"]
    logging.info(
        "Coach: score=%.2f, timing=%s, frequency=%s, %d warning(s).",
        report.safety_score,
        en.timing,
        en.frequency,
        len(en.warnings),
    )

    return {"coach_cards": response}
