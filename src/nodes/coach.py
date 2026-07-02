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
from src.messages import COACH_UNAVAILABLE
from src.nodes.routine_advisor import present_function_categories
from src.prompts.coach import COACH_SYSTEM_PROMPT
from src.state import (AgentState, CoachResponse, Notice, RoutineFit,
                       UserProfile, inci_names)

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

# Function categories treated as "strong actives" for introduction pacing: the
# retinoids and exfoliating acids that warrant easing in one at a time.
_STRONG_ACTIVE_CATEGORIES = {"Retinoids", "AHA", "BHA"}


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


def _introduction_pacing_flags(
    state: AgentState, profile: Optional[UserProfile]
) -> Tuple[List[str], List[str]]:
    """Deterministic 'one active at a time + patch-test' caution.

    Fires when the new product introduces a strong active (retinoid / AHA / BHA)
    AND either the saved shelf already carries a strong active or the user is
    sensitive-skinned — the classic over-exfoliation / irritation risk. Safety-
    adjacent (same rationale as the pregnancy / sun flags), so it is computed in
    code, not left to the model.
    """
    new_cats = set(present_function_categories(
        set(inci_names(state.get("standardized_ingredients")))
    ))
    if not (new_cats & _STRONG_ACTIVE_CATEGORIES):
        return [], []

    shelf_has_strong = any(
        set(present_function_categories(set(p.ingredients)))
        & _STRONG_ACTIVE_CATEGORIES
        for p in (state.get("routine_products") or [])
    )
    is_sensitive = bool(profile and profile.skin_type == "sensitive")
    if not (shelf_has_strong or is_sensitive):
        return [], []

    ja = [
        "導入の注意: 新しい活性成分は一度に1つずつ取り入れ、はじめは"
        "腕の内側で24時間パッチテストを行ってからご使用ください。"
    ]
    en = [
        "Introduction caution: introduce one new active at a time, and patch-test "
        "on your inner arm for 24 hours before applying to the face."
    ]
    return ja, en


def coach_node(state: AgentState) -> dict:
    if state.get("safety_report") is None:
        logging.warning("Coach reached without safety_report — returning placeholder.")
        return {"notice": Notice(**COACH_UNAVAILABLE), "coach_cards": None}

    profile: Optional[UserProfile] = state.get("user_profile")
    user_name = state.get("user_name")
    preg_ja, preg_en = _pregnancy_cautions(state, profile)
    sun_ja, sun_en = _dehydration_sun_flags(state)
    pace_ja, pace_en = _introduction_pacing_flags(state, profile)
    extra_ja = preg_ja + sun_ja + pace_ja
    extra_en = preg_en + sun_en + pace_en

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
            [SystemMessage(content=COACH_SYSTEM_PROMPT), HumanMessage(content=human_prompt)]
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
