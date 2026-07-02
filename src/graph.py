# stategraph definition
import logging

from langgraph.graph import END, StateGraph

from src.config import (FLASH_ACCEPT_THRESHOLD, FLASH_ESCALATE_THRESHOLD,
                        IDENTITY_CONFIDENCE_THRESHOLD, MAX_CORRECTIONS,
                        MIN_INGREDIENTS_FOR_AUDIT)
from src.messages import REJECTION_MESSAGES, RETAKE_DEFAULT
from src.nodes.auditor import auditor_node
from src.nodes.coach import coach_node
from src.nodes.normalizer import normalizer_node
from src.nodes.registry import early_registry_check_node, registry_lookup_node
from src.nodes.routine_advisor import routine_advisor_node
from src.nodes.scanner import (classify_side_node, flash_scanner_node,
                               pro_scanner_node)
from src.nodes.websearch import (confirm_identity_node, search_failed_node,
                                 web_search_node)
from src.preprocess import assess_image_quality
from src.state import AgentState, Notice


def quality_gate_node(state: AgentState) -> dict:
    """Tier-1 entry node: reject degenerate images on raw pixels (no VLM call)."""
    issue = assess_image_quality(state["image_path"])
    if issue:
        logging.warning("Image failed Tier-1 pixel pre-check: %s", issue)
    return {"image_quality_issue": issue}


def quality_router(state: AgentState) -> str:
    """Send pixel-degenerate frames straight to retake; otherwise classify them."""
    return "reject" if state.get("image_quality_issue") else "ok"


def side_router(state: AgentState) -> str:
    """Route on the detected image side.

    A front photo (branding only) has no readable ingredient list, so we go
    straight to identity verification + web search. A back photo carries the
    ingredient list, so we scan it off the label.
    """
    return "front" if state.get("image_type") == "front" else "back"


def classify_router(state: AgentState) -> str:
    """Route after the Tier-2 content + side classification.

    A non-product or multi-product frame is rejected before any extraction runs
    (the structured-output scanner cannot say "no product" — it would fabricate
    one). A back photo carries the ingredient list, so it goes to the scanner. A
    front photo has no readable list, so it skips straight to the identity-gated
    web fallback — the classifier already read the branding, so we reuse
    identity_router here instead of a separate verify_identity VLM call.
    """
    if state.get("image_content") in ("not_a_product", "multiple_products"):
        return "reject"
    if side_router(state) == "front":
        return identity_router(state)
    return "back"


def inference_router(state: AgentState) -> str:
    conf = state["inference_confidence"]
    attempts = state.get("correction_attempts", 0)
    if conf >= FLASH_ACCEPT_THRESHOLD:
        return "accept"
    if conf >= FLASH_ESCALATE_THRESHOLD and attempts < MAX_CORRECTIONS:
        return "correct"
    return "escalate"


def early_registry_router(state: AgentState) -> str:
    return "registry_hit" if state.get("is_ready_for_logic", False) else "continue"


def pro_scanner_router(state: AgentState) -> str:
    accept = state["inference_confidence"] >= FLASH_ACCEPT_THRESHOLD
    return "accept" if accept else "retake"


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
    """Graceful exit for any unusable input: pixel-degenerate (Tier 1),
    non/multi-product (Tier 2), or unreadable after both scanners (confidence)."""
    reason = state.get("image_quality_issue")
    if not reason and state.get("image_content") in (
        "not_a_product",
        "multiple_products",
    ):
        reason = state.get("image_content")
    logging.warning(
        "Bouncing input back to user (reason: %s).", reason or "low_confidence"
    )
    message = REJECTION_MESSAGES.get(reason or "", RETAKE_DEFAULT)
    return {
        "retake_requested": True,
        "is_ready_for_logic": False,
        "notice": Notice(**message),
    }


def post_registry_router(state: AgentState) -> str:
    """After the registry lookup, decide whether we already have a usable list.

    A registry hit is always enough. On a miss we trust the photo only if it
    yielded enough ingredients; otherwise we fall through to the identity-gated
    web search (identity_router reuses the scanner's extraction_confidence).
    """
    if state.get("registry_matched"):
        return "have_ingredients"
    data = state.get("extracted_data")
    count = len(data.ingredients) if data else 0
    if count >= MIN_INGREDIENTS_FOR_AUDIT:
        return "have_ingredients"
    return identity_router(state)


def identity_router(state: AgentState) -> str:
    """Gate the web-search fallback on how confidently we know the product name.

    Front photos carry the classifier's ``identity_confidence`` (its branding
    read, seeded by classify_side_node). The back-path web fallback has none, so
    we fall back to the scanner's ``extraction_confidence`` — it already read the
    brand/product off the label.
    """
    conf = state.get("identity_confidence")
    if conf is None:
        data = state.get("extracted_data")
        conf = data.extraction_confidence if data else 0.0
    return "confident" if conf >= IDENTITY_CONFIDENCE_THRESHOLD else "uncertain"


def web_result_router(state: AgentState) -> str:
    data = state.get("extracted_data")
    count = len(data.ingredients) if data else 0
    return "found" if count >= MIN_INGREDIENTS_FOR_AUDIT else "not_found"


workflow = StateGraph(state_schema=AgentState)

workflow.add_node("image_quality_gate", quality_gate_node)
workflow.add_node("classify_side", classify_side_node)
workflow.add_node("flash_scanner", flash_scanner_node)
workflow.add_node("early_registry_check", early_registry_check_node)
workflow.add_node("correction", correction_node)
workflow.add_node("pro_scanner", pro_scanner_node)
workflow.add_node("registry_lookup", registry_lookup_node)
workflow.add_node("normalizer", normalizer_node)
workflow.add_node("auditor", auditor_node)
workflow.add_node("routine_advisor", routine_advisor_node)
workflow.add_node("coach", coach_node)
workflow.add_node("web_search", web_search_node)
workflow.add_node("confirm_identity", confirm_identity_node)
workflow.add_node("search_failed", search_failed_node)
workflow.add_node("retake_request", retake_node)

workflow.set_entry_point("image_quality_gate")

# Tier 1: deterministic pixel gate runs first, even on the CLI/API override path
# (which skips the Tier-2 classifier). Degenerate frames never reach the VLM.
workflow.add_conditional_edges(
    "image_quality_gate",
    quality_router,
    {
        "ok": "classify_side",
        "reject": "retake_request",
    },
)

# Tier 2: the classifier's content verdict rejects non-product / multi-product
# frames before extraction. A back photo goes to the scanner; a front photo has
# no ingredient list, so it routes straight to the identity-gated web fallback
# (confident → search, uncertain → confirm) without a separate verify VLM call.
workflow.add_conditional_edges(
    "classify_side",
    classify_router,
    {
        "back": "flash_scanner",
        "confident": "web_search",
        "uncertain": "confirm_identity",
        "reject": "retake_request",
    },
)

workflow.add_conditional_edges(
    "flash_scanner",
    inference_router,
    {
        "accept": "registry_lookup",
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
        "accept": "registry_lookup",
        "retake": "retake_request",
    },
)

# On a registry miss with too few photo ingredients, the same identity gate the
# front path uses decides whether to web-search or ask the user to confirm.
workflow.add_conditional_edges(
    "registry_lookup",
    post_registry_router,
    {
        "have_ingredients": "normalizer",
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
workflow.add_edge("auditor", "routine_advisor")
workflow.add_edge("routine_advisor", "coach")
workflow.add_edge("coach", END)
workflow.add_edge("confirm_identity", END)
workflow.add_edge("search_failed", END)
workflow.add_edge("retake_request", END)

app = workflow.compile()
