# Coach node: generates personalised, 薬機法-safe routine advice from the audit.
#
# Receives the safety_report from the auditor and the user_profile from state.
# Calls Gemini Flash with a tightly constrained system prompt that:
#   (a) enforces 薬機法-compliant language throughout, and
#   (b) restricts the model to only discussing ingredients that are actually
#       present in the product — no invented benefits.
import logging
from typing import List, Optional, cast

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

PREGNANCY: whenever relevant, include:
妊娠中・授乳中の方は医師にご相談の上ご使用ください

━━ SCOPE ━━
• ONLY reference ingredients listed in the product context below.
• Do NOT invent benefits not supported by the ingredient list.
• Output in English. Include Japanese terms where standard.
""".strip()


class CoachResponse(BaseModel):
    am_advice: str = Field(
        description=(
            "How to use this product in the AM routine: step order, "
            "what to layer before/after, any morning-specific notes. "
            "2-4 sentences. 薬機法-compliant."
        )
    )
    pm_advice: str = Field(
        description=(
            "How to use this product in the PM routine. Note any PM-only "
            "constraints (photosensitising citrus oils, retinoids, etc.). "
            "2-4 sentences. 薬機法-compliant."
        )
    )
    cautions: List[str] = Field(
        default_factory=list,
        description=(
            "User-profile-specific cautions: skin conditions, detected ingredient "
            "conflicts relevant to this user, sensitivity flags. "
            "One concern per item. 薬機法-compliant."
        ),
    )
    tips: List[str] = Field(
        default_factory=list,
        description=(
            "3-5 practical tips tailored to this user's skin type, goals, "
            "available routine time, and budget. 薬機法-compliant."
        ),
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


def _user_context(profile: Optional[UserProfile]) -> str:
    if profile is None:
        return (
            "User profile: not provided — "
            "give general-purpose advice suitable for all skin types."
        )

    lines = ["User profile:"]
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


def _pregnancy_cautions(state: AgentState, profile: Optional[UserProfile]) -> List[str]:
    """Hardcoded pregnancy flags for any high-risk INCI names present in the product."""
    if profile is None or not profile.is_pregnant:
        return []
    present = {
        i["name_standardized"]
        for i in (state.get("standardized_ingredients") or [])
        if i.get("name_standardized")
    }
    flagged = sorted(present & _PREGNANCY_FLAGGED_INCI)
    if flagged:
        return [
            f"Pregnancy caution: {', '.join(flagged)} should be avoided during "
            "pregnancy and breastfeeding. "
            "妊娠中・授乳中の方は医師にご相談の上ご使用ください。"
        ]
    return ["妊娠中・授乳中の方は医師にご相談の上ご使用ください。"]


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
    pregnancy_flags = _pregnancy_cautions(state, profile)

    human_prompt = (
        f"## Product Analysis\n{_product_context(state)}\n\n"
        f"## {_user_context(profile)}\n\n"
        "Provide AM routine advice, PM routine advice, "
        "user-specific cautions, and practical tips for this product."
    )

    model = ChatGoogleGenerativeAI(model=FLASH_MODEL, temperature=0.2)
    response: CoachResponse = cast(
        CoachResponse,
        model.with_structured_output(CoachResponse).invoke(
            [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=human_prompt)]
        ),
    )

    # Flatten into the two AgentState output fields.
    all_cautions = pregnancy_flags + response.cautions
    recommendations: List[str] = (
        [f"[AM] {response.am_advice}", f"[PM] {response.pm_advice}"]
        + all_cautions
        + response.tips
    )

    sections = [f"AM: {response.am_advice}", f"PM: {response.pm_advice}"]
    if all_cautions:
        sections.append(
            "Cautions:\n" + "\n".join(f"  • {c}" for c in all_cautions)
        )
    coach_advice = "\n\n".join(sections)

    report = state["safety_report"]
    logging.info(
        "Coach: score=%.2f, %d conflict(s), %d caution(s), %d tip(s).",
        report.safety_score,
        len(report.ingredient_conflicts),
        len(all_cautions),
        len(response.tips),
    )

    return {
        "coach_advice": coach_advice,
        "routine_recommendations": recommendations,
    }
