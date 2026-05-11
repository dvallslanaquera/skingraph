# stategraph definition
import logging
from langgraph.graph import StateGraph, END
from src.state import AgentState
from src.nodes.scanner import flash_scanner_node, pro_scanner_node
from src.config import FLASH_ACCEPT_THRESHOLD, FLASH_ESCALATE_THRESHOLD, MAX_CORRECTIONS
from src.nodes.registry import registry_lookup_node, early_registry_check_node


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


workflow = StateGraph(state_schema=AgentState)

workflow.add_node("flash_scanner", flash_scanner_node)
workflow.add_node("early_registry_check", early_registry_check_node)
workflow.add_node("correction", correction_node)
workflow.add_node("pro_scanner", pro_scanner_node)
workflow.add_node("registry_lookup", registry_lookup_node)
workflow.add_node("retake_request", retake_node)

workflow.set_entry_point("flash_scanner")

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
        "registry_hit": END,
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

workflow.add_edge("registry_lookup", END)
workflow.add_edge("retake_request", END)

app = workflow.compile()
