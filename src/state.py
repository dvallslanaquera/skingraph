# pydantic schemes
# define AgentState as a TypedDict for a controlled data flow between nodes

from typing import List, TypedDict, Optional, Literal
from pydantic import BaseModel, Field


#! Why keep everything in three different classes
#!. what are the different syntaxs of states
# pydantic models to force JSON output of the LLM nodes
class Ingredient(BaseModel):
    name_raw: str = Field(
        ..., description="original name of the ingredient as extracted from the image"
    )
    name_standardized: Optional[str] = Field(
        None, description="standardized name of the ingredient"
    )
    is_active: Optional[bool] = Field(
        None, description="whether the product is a quasi-drug or not"
    )
    source_language: str = Field(
        "JP", description="language of the ingredient name as extracted from the image"
    )


class ProductExtraction(BaseModel):
    brand: str = Field(
        ..., description="brand of the product as extracted from the image"
    )
    product_name: str = Field(
        ..., description="name of the product as extracted from the image"
    )
    jan_code: Optional[str] = Field(
        None, description="JAN code of the product as extracted from the image"
    )
    ingredients: list[Ingredient] = Field(
        ..., description="list of ingredients extracted from the image"
    )
    is_quasi_drug: Optional[bool] = Field(
        None, description="whether the product is a quasi-drug or not"
    )
    source_language: str = Field(
        ...,
        description=(
            "Primary language of the LABEL as a 2-letter uppercase code "
            "(JP=Japanese, EN=English, KO=Korean, FR=French, ZH=Chinese, etc.). "
            "Detect from the dominant script/text on the label, not from the brand origin."
        ),
    )
    extraction_confidence: float = Field(
        ..., description="confidence score of the extraction process"
    )
    system_status: Literal["SUCCESS", "INCOMPLETE", "RETAKE_REQUIRED"] = Field(
        ..., description="extraction quality status based on confidence and completeness"
    )


class SafetyAudit(BaseModel):
    conflicts_with_conditions: Optional[list[str]] = Field(
        None,
        description="list of health conditions that may conflict with the product's ingredients",
    )
    warnings: Optional[list[str]] = Field(
        None, description="list of warnings related to the product's ingredients"
    )
    safety_score: Optional[float] = Field(
        None, description="safety score of the product based on its ingredients"
    )
    risk_ingredients: Optional[list[str]] = Field(
        None, description="list of potentially risky ingredients found in the product"
    )


# graph state: shared memory bus between nodes, also used for routing decisions
class AgentState(TypedDict):
    # input data
    image_path: str
    image_type: Literal["front", "back"]

    # extraction state
    extracted_data: Optional[ProductExtraction]
    model_used: Literal["flash", "pro", "database"]
    inference_confidence: float

    # processed data
    standardized_ingredients: List[Ingredient]
    safety_report: Optional[SafetyAudit]

    # final output
    coach_advice: str
    routine_recommendations: List[str]

    # system flags
    is_ready_for_logic: bool
    retake_requested: bool
    correction_attempts: int
    correction_feedback: Optional[str]
    trace_id: Optional[str]

    # language gate
    detected_language: Optional[str]
    language_supported: Optional[bool]

    # registry + normalization
    registry_matched: Optional[bool]
    unmatched_ingredients: Optional[List[str]]
