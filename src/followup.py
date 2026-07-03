# Post-scan follow-up Q&A: answers ONE user question about a product already
# scanned, grounded in the scan results the client sends back. Stateless — no
# server-side conversation store, no image, no re-scan.
#
# The same determinism-for-safety rule as the pipeline applies: pregnancy, sun/
# dryness, and active-introduction findings are computed here in code (reusing
# the coach's helpers) and handed to the model as authoritative context; the
# model only phrases them.
import logging
import re
from typing import List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from src.config import FLASH_MODEL
from src.nodes.coach import (_PREGNANCY_FLAGGED_INCI, _dehydration_sun_flags,
                             _introduction_pacing_flags, _pregnancy_cautions,
                             _product_context, _routine_context, _user_context)
from src.nodes.websearch import _text_of
from src.prompts.followup import FOLLOWUP_SYSTEM_PROMPT
from src.state import (ProductExtraction, RoutineFit, RoutineProduct,
                       SafetyAudit, UserProfile, inci_names)

# The question mentions pregnancy/breastfeeding → surface the deterministic
# pregnancy analysis even when the profile doesn't state a pregnancy.
_PREGNANCY_QUESTION = re.compile(
    r"妊娠|授乳|マタニティ|pregnan|breast.?feed|nursing", re.IGNORECASE
)


def _deterministic_findings(
    state: dict,
    profile: Optional[UserProfile],
    question: str,
    lang: str,
) -> List[str]:
    """The system-computed safety findings relevant to this product + question.

    Reuses the coach's deterministic helpers so the follow-up can never drift
    from what the scan itself would have flagged.
    """
    preg_ja, preg_en = _pregnancy_cautions(state, profile)
    sun_ja, sun_en = _dehydration_sun_flags(state)
    pace_ja, pace_en = _introduction_pacing_flags(state, profile)
    findings = list(
        (preg_ja + sun_ja + pace_ja) if lang == "ja" else (preg_en + sun_en + pace_en)
    )

    # Asked about pregnancy but the profile doesn't state one → the pregnancy
    # helper stayed silent, so add the deterministic analysis for the question.
    if _PREGNANCY_QUESTION.search(question) and not (profile and profile.is_pregnant):
        present = set(inci_names(state.get("standardized_ingredients")))
        flagged = sorted(present & _PREGNANCY_FLAGGED_INCI)
        if flagged:
            findings.append(
                f"妊娠中・授乳期は {', '.join(flagged)} のご使用をお控えください。"
                "妊娠中・授乳中の方は医師にご相談の上ご使用ください。"
                if lang == "ja"
                else f"Contains {', '.join(flagged)} — avoid during pregnancy and "
                "breastfeeding; consult a doctor before use."
            )
        else:
            findings.append(
                "確認済みの成分の中に妊娠中の使用が特に懸念されるものは見つかり"
                "ませんでしたが、妊娠中・授乳中の方は医師にご相談の上ご使用ください。"
                if lang == "ja"
                else "No pregnancy-flagged ingredients were found among the verified "
                "list, but if you are pregnant or breastfeeding, please consult "
                "a doctor before use."
            )
    return findings


def answer_followup(
    *,
    brand: str,
    product_name: str,
    standardized_ingredients: List[dict],
    safety_report: Optional[SafetyAudit],
    routine_fit: Optional[RoutineFit],
    question: str,
    lang: str,
    profile: Optional[UserProfile] = None,
    user_name: Optional[str] = None,
    routine_products: Optional[List[RoutineProduct]] = None,
) -> str:
    """Answer one grounded follow-up question in the requested language."""
    # Rebuild the coach-shaped state so its context builders can be reused as-is.
    state = {
        "extracted_data": ProductExtraction(
            brand=brand,
            product_name=product_name,
            ingredients=[],
            source_language="",
            extraction_confidence=1.0,
            system_status="SUCCESS",
        ),
        "standardized_ingredients": standardized_ingredients,
        "unmatched_ingredients": [],
        "safety_report": safety_report,
        "routine_products": routine_products,
    }

    blocks = [f"## Product Analysis\n{_product_context(state)}"]
    blocks.append(f"## {_user_context(profile, user_name)}")
    routine_context = _routine_context(routine_fit)
    if routine_context:
        blocks.append(routine_context)
    findings = _deterministic_findings(state, profile, question, lang)
    if findings:
        blocks.append(
            "## DETERMINISTIC SAFETY FINDINGS (authoritative — repeat, don't re-derive)\n"
            + "\n".join(f"• {f}" for f in findings)
        )
    language = "Japanese (敬体)" if lang == "ja" else "English"
    blocks.append(
        f"## Question\n{question.strip()}\n\n"
        f"Answer the question above, entirely in {language}."
    )
    human_prompt = "\n\n".join(blocks)

    logging.info(
        "Follow-up (%s): %s — %s: %.60s", lang, brand, product_name, question
    )
    llm = ChatGoogleGenerativeAI(
        model=FLASH_MODEL, temperature=0.2, timeout=120, max_retries=3
    )
    response = llm.invoke(
        [
            SystemMessage(content=FOLLOWUP_SYSTEM_PROMPT),
            HumanMessage(content=human_prompt),
        ]
    )
    return _text_of(response).strip()
