from typing import List, Literal, Optional, Tuple, TypedDict

from pydantic import BaseModel, Field


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
    ingredient_conflicts: List[str] = Field(
        default_factory=list,
        description="pairwise ingredient conflicts found, e.g. 'Retinol + Ascorbic Acid: ...'",
    )
    risk_ingredients: List[str] = Field(
        default_factory=list,
        description="individual INCI names flagged as irritant, sensitizer, or regulated",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="human-readable, severity-tagged warning lines for the coach node",
    )
    safety_score: float = Field(
        1.0,
        description="0.0 (high concern) to 1.0 (no flags); starts at 1.0, penalized per finding",
    )


class UserProfile(BaseModel):
    skin_type: Optional[Literal["dry", "oily", "combination", "normal", "sensitive"]] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    goals: List[str] = Field(
        default_factory=list,
        description="e.g. anti_aging, brightening, hydration, acne_control, barrier_repair",
    )
    is_pregnant: bool = False
    skin_conditions: List[str] = Field(
        default_factory=list,
        description="e.g. eczema, rosacea, acne, psoriasis, hyperpigmentation",
    )
    sun_damage_history: Optional[Literal["none", "mild", "moderate", "severe"]] = None
    routine_time: Optional[Literal["minimal", "moderate", "extensive"]] = None
    budget: Optional[Literal["budget", "mid-range", "premium"]] = None


class RoutineProduct(BaseModel):
    """A product the user has saved into their current routine ("shelf").

    ``ingredients`` holds canonical INCI names (the same keys the auditor reasons
    over), so a saved product can be re-analysed against a new scan without
    re-running OCR.
    """

    product_id: str = Field(..., description="stable id of the saved product")
    brand: str = Field(..., description="brand of the saved product")
    product_name: str = Field(..., description="name of the saved product")
    ingredients: List[str] = Field(
        default_factory=list,
        description="canonical INCI names of the saved product",
    )
    is_quasi_drug: Optional[bool] = Field(
        None, description="whether the saved product is a quasi-drug"
    )


class CrossConflict(BaseModel):
    """One deterministic conflict between the new product and a shelf product."""

    with_product: str = Field(
        ..., description="the existing routine product the new one conflicts with"
    )
    severity: str = Field("medium", description="high | medium | low")
    groups: Tuple[str, str] = Field(
        ..., description="the two conflicting active groups (new side, existing side)"
    )
    reason: str = Field(..., description="why the two groups conflict (from the matrix)")


class RoutineFit(BaseModel):
    """Deterministic evaluation of a new product against the user's routine.

    Computed by ``routine_advisor_node``; the coach turns these grounded findings
    into 薬機法-safe bilingual prose. Empty lists mean "nothing to report".
    """

    conflicts: List[CrossConflict] = Field(
        default_factory=list,
        description="cross-product active conflicts with existing routine products",
    )
    redundancy: List[str] = Field(
        default_factory=list,
        description="roles the new product duplicates from the existing routine",
    )
    value_add: List[str] = Field(
        default_factory=list,
        description="unmet user goals the new product would help target",
    )
    existing_products: List[str] = Field(
        default_factory=list,
        description="'Brand — Product' labels of the current routine, for context",
    )


# graph state: shared memory bus between nodes, also used for routing decisions
class AgentState(TypedDict):
    # input data
    image_path: str
    # None on input → the classify_side node auto-detects front vs back.
    image_type: Optional[Literal["front", "back"]]

    # extraction state
    extracted_data: Optional[ProductExtraction]
    model_used: Literal["flash", "pro", "database", "web"]
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

    # web-search fallback (last resort when registry + photo both lack a list)
    identity_confidence: Optional[float]
    ingredient_source: Optional[str]  # "registry" | "label" | "web"
    web_sources: Optional[List[str]]

    # personalised coaching
    user_profile: Optional[UserProfile]
    user_name: Optional[str]

    # routine memory: the user's saved "shelf" (loaded at entry) and the
    # deterministic cross-product evaluation of the new scan against it.
    routine_products: Optional[List[RoutineProduct]]
    routine_fit: Optional[RoutineFit]
