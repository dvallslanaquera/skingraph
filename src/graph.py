# stategraph definition
from langgraph.graph import StateGraph, END
from src.state import AgentState
from src.nodes.scanner import flash_scanner_node, pro_scanner_node


def inference_router(state: AgentState) -> str:
    if state["inference_confidence"] >= 0.85:
        return "accept"
    return "escalate"


def pro_scanner_router(state: AgentState) -> str:
    if state["inference_confidence"] < 0.7:
        return "retake"
    return "accept"


def retake_node(_: AgentState) -> dict:
    return {"retake_requested": True}


workflow = StateGraph(state_schema=AgentState)

workflow.add_node("flash_scanner", flash_scanner_node)
workflow.add_node("pro_scanner", pro_scanner_node)
workflow.add_node("retake_request", retake_node)

workflow.set_entry_point("flash_scanner")

workflow.add_conditional_edges(
    "flash_scanner",
    inference_router,
    {
        "accept": END,
        "escalate": "pro_scanner",
    },
)

workflow.add_conditional_edges(
    "pro_scanner",
    pro_scanner_router,
    {
        "accept": END,
        "retake": "retake_request",
    },
)

workflow.add_edge("retake_request", END)

app = workflow.compile()
