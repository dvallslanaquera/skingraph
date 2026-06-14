# stategraph definition
import logging

from langgraph.graph import END, StateGraph

from src.config import (FLASH_ACCEPT_THRESHOLD, FLASH_ESCALATE_THRESHOLD,
                        IDENTITY_CONFIDENCE_THRESHOLD, MAX_CORRECTIONS,
                        MIN_INGREDIENTS_FOR_AUDIT, SUPPORTED_LANGUAGES)
from src.nodes.auditor import auditor_node
from src.nodes.coach import coach_node
from src.nodes.normalizer import normalizer_node
from src.nodes.registry import early_registry_check_node, registry_lookup_node
from src.nodes.scanner import flash_scanner_node, pro_scanner_node
from src.nodes.websearch import (confirm_identity_node, search_failed_node,
                                 verify_identity_node, web_search_node)
from src.state import AgentState


def inference_router(state: AgentState) -> str:
    conf = state["inference_confidence"]
    attempts = state.get("correction_attempts", 0)
    if conf >= FLASH_ACCEPT_THRESHOLD:
        return "accept"
    if conf >= FLASH_ESCALATE_THRESHOLD and attempts < MAX_CORRECTIONS:
        return "correct"
    return "escalate"


def early_registry_router(state: AgentState) -> str:
    if state.get("is_ready_for_logic", False):
        return "registry_hit"
    return "continue"


def pro_scanner_router(state: AgentState) -> str:
    if state["inference_confidence"] >= FLASH_ACCEPT_THRESHOLD:
        return "accept"
    return "retake"


def correction_node(state: AgentState) -> dict:
    extracted = state["extracted_data"]
    if extracted is None:
        raise ValueError("correction_node reached with no extracted_data")
    feedback = (
        f"Confidence was {extracted.extraction_confidence:.2f} "
        f"(status: {extracted.system_status}). "
        "Re-examine any blurry, curved, or partially visible text more carefully."
    )
    return {
        "correction_feedback": feedback,
        "correction_attempts": state.get("correction_attempts", 0) + 1,
    }


def retake_node(state: AgentState) -> dict:
    logging.warning("Extraction failed on both models — triggering retake prompt.")
    return {
        "retake_requested": True,
        "is_ready_for_logic": False,
        "coach_advice": (
            "I couldn't read the label clearly. "
            "Could you please retake the photo with less glare and flatter alignment?"
        ),
    }


def language_gate_node(state: AgentState) -> dict:
    """Record the detected label language and whether it's supported downstream.

    Runs only after a confident extraction (flash- or pro-accept), so the
    language read here comes from a reliable scan rather than a noisy one.
    """
    extracted = state["extracted_data"]
    lang = (extracted.source_language or "").strip().upper() if extracted else ""
    supported = lang in SUPPORTED_LANGUAGES
    if not supported:
        logging.info(
            "Language gate: detected '%s', not in supported set %s.",
            lang or "unknown",
            sorted(SUPPORTED_LANGUAGES),
        )
    return {"detected_language": lang, "language_supported": supported}


def language_router(state: AgentState) -> str:
    return "supported" if state.get("language_supported") else "unsupported"


def unsupported_language_node(state: AgentState) -> dict:
    lang = state.get("detected_language") or "unknown"
    return {
        "is_ready_for_logic": False,
        "coach_advice": (
            f"This label appears to be in '{lang}'. SkinGraph currently supports "
            "Japanese (JP) labels only, so ingredient verification and safety "
            "analysis aren't available for this product yet."
        ),
    }


def post_registry_router(state: AgentState) -> str:
    """After the registry lookup, decide whether we already have a usable list.

    A registry hit is always enough. On a miss we trust the photo only if it
    yielded enough ingredients; otherwise we fall through to the web search.
    """
    if state.get("registry_matched"):
        return "have_ingredients"
    data = state.get("extracted_data")
    count = len(data.ingredients) if data else 0
    return "have_ingredients" if count >= MIN_INGREDIENTS_FOR_AUDIT else "need_search"


def identity_router(state: AgentState) -> str:
    conf = state.get("identity_confidence") or 0.0
    return "confident" if conf >= IDENTITY_CONFIDENCE_THRESHOLD else "uncertain"


def web_result_router(state: AgentState) -> str:
    data = state.get("extracted_data")
    count = len(data.ingredients) if data else 0
    return "found" if count >= MIN_INGREDIENTS_FOR_AUDIT else "not_found"


workflow = StateGraph(state_schema=AgentState)

workflow.add_node("flash_scanner", flash_scanner_node)
workflow.add_node("early_registry_check", early_registry_check_node)
workflow.add_node("correction", correction_node)
workflow.add_node("pro_scanner", pro_scanner_node)
workflow.add_node("language_gate", language_gate_node)
workflow.add_node("registry_lookup", registry_lookup_node)
workflow.add_node("normalizer", normalizer_node)
workflow.add_node("auditor", auditor_node)
workflow.add_node("coach", coach_node)
workflow.add_node("verify_identity", verify_identity_node)
workflow.add_node("web_search", web_search_node)
workflow.add_node("confirm_identity", confirm_identity_node)
workflow.add_node("search_failed", search_failed_node)
workflow.add_node("retake_request", retake_node)
workflow.add_node("unsupported_language", unsupported_language_node)

workflow.set_entry_point("flash_scanner")

workflow.add_conditional_edges(
    "flash_scanner",
    inference_router,
    {
        "accept": "language_gate",
        "correct": "early_registry_check",
        "escalate": "pro_scanner",
    },
)

workflow.add_conditional_edges(
    "early_registry_check",
    early_registry_router,
    {
        "registry_hit": "normalizer",
        "continue": "correction",
    },
)

workflow.add_edge("correction", "flash_scanner")

workflow.add_conditional_edges(
    "pro_scanner",
    pro_scanner_router,
    {
        "accept": "language_gate",
        "retake": "retake_request",
    },
)

workflow.add_conditional_edges(
    "language_gate",
    language_router,
    {
        "supported": "registry_lookup",
        "unsupported": "unsupported_language",
    },
)

workflow.add_conditional_edges(
    "registry_lookup",
    post_registry_router,
    {
        "have_ingredients": "normalizer",
        "need_search": "verify_identity",
    },
)

workflow.add_conditional_edges(
    "verify_identity",
    identity_router,
    {
        "confident": "web_search",
        "uncertain": "confirm_identity",
    },
)

workflow.add_conditional_edges(
    "web_search",
    web_result_router,
    {
        "found": "normalizer",
        "not_found": "search_failed",
    },
)

workflow.add_edge("normalizer", "auditor")
workflow.add_edge("auditor", "coach")
workflow.add_edge("coach", END)
workflow.add_edge("confirm_identity", END)
workflow.add_edge("search_failed", END)
workflow.add_edge("retake_request", END)
workflow.add_edge("unsupported_language", END)

app = workflow.compile()
