import os
from dotenv import load_dotenv
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, END
from pydantic import BaseModel

load_dotenv()


# state definition
class AgentState(TypedDict):
    input_image: str
    extraction_confidence: float
    analysis: str


# dummy node definition
def init_node(state: AgentState):
    print("---Initiliazing graph---")
    return {"analysis": "Env correctly setup!"}


# graph building
workflow = StateGraph(state_schema=AgentState)
workflow.add_node("init", init_node)
workflow.set_entry_point(key="init")
workflow.add_edge("init", END)

app = workflow.compile()

if __name__ == "__main__":
    app.invoke(
        {
            "input_image": "../data/prod_001.jpg",
            "extraction_confidence": 0.0,
            "analysis": "",
        }
    )
    print("LangGraph env is ready!")
