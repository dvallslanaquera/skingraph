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
    # "male" | "female" | "other" (non-binary / prefer not to disclose). Kept as a
    # free str (not a Literal) so older profiles and any future values still load.
    gender: Optional[str] = None
    # Fitzpatrick phototype I–VI as an int 1–6, with the undertone palette the user
    # picked it from (Asian skins skew warm/olive, others cooler/pink at the same
    # phototype) — both feed the coach's sun-sensitivity guidance.
    fitzpatrick: Optional[int] = Field(
        None, ge=1, le=6, description="Fitzpatrick phototype, 1 (I) to 6 (VI)"
    )
    skin_undertone: Optional[Literal["asian", "non_asian"]] = None
    goals: List[str] = Field(
        default_factory=list,
        description="skin concerns, e.g. fine lines, hyperpigmentation, acne, redness",
    )
    is_pregnant: bool = False
    skin_conditions: List[str] = Field(
        default_factory=list,
        description="e.g. eczema, rosacea, acne, psoriasis, hyperpigmentation",
    )
    sun_damage_history: Optional[Literal["none", "mild", "moderate", "severe"]] = None
    routine_time: Optional[Literal["minimal", "moderate", "extensive"]] = None
    # When True, the coach may also suggest devices / at-home treatments (LED masks,
    # at-home IPL, microneedle stamps, gua sha, etc.) on top of topical products.
    consider_devices: bool = False
    # Monthly skincare budget in USD. 0 means no spend; 250 is treated as "$250+".
    budget: Optional[int] = Field(None, ge=0, description="monthly budget in USD")


class RoutineProduct(BaseModel):
    """A product the user has saved into their current routine ("shelf").

    ``ingredients`` holds canonical INCI names (the same keys the auditor reasons
    over), so a saved product can be re-analysed against a new scan without
    re-running OCR.

    The ``timing`` / ``application_notes`` / price fields are populated when the
    product is added via a scan (from the coach card + a web price lookup); they
    stay ``None``/empty for products added manually, and the dashboard fills in a
    deterministic timing fallback when ``timing`` is missing.
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
    # When to use the product: "AM" | "PM" | "AM & PM". None until classified.
    timing: Optional[str] = Field(
        None, description="best time to use: 'AM', 'PM', or 'AM & PM'"
    )
    # Short application/sequencing cautions (e.g. "apply to completely dry skin",
    # "wait ~1 min before the next layer"), from the coach card.
    application_notes: List[str] = Field(
        default_factory=list,
        description="how-to-apply / sequencing notes for this product",
    )
    # Amortizable price info, looked up once at add-time (best-effort).
    price_usd: Optional[float] = Field(
        None, description="unit price converted to USD"
    )
    price_native: Optional[float] = Field(
        None, description="unit price in its native market currency"
    )
    price_currency: Optional[str] = Field(
        None, description="native currency code, e.g. JPY, USD, EUR, KRW"
    )
    price_market: Optional[str] = Field(
        None, description="market the price came from: 'JP' or the origin code"
    )
    months_supply: Optional[float] = Field(
        None, description="estimated months one unit lasts for a daily user"
    )
    price_source: Optional[str] = Field(
        None, description="URL the price was sourced from"
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

    # input gating
    # Tier-1 pixel pre-flight verdict (set by the image-quality gate): None when
    # the frame passed, else a reason code ("too_dark" | "too_bright" | "blank" |
    # "unreadable") used to craft the retake message.
    image_quality_issue: Optional[str]
    # Tier-2 content classification from the side/content classifier: "product",
    # "not_a_product", or "multiple_products". Non-product / multi-product frames
    # are rejected before extraction so the scanner never fabricates a product.
    image_content: Optional[str]

    # extraction state
    extracted_data: Optional[ProductExtraction]
    model_used: Literal["flash", "pro", "database", "web"]
    inference_confidence: float

    # processed data
    standardized_ingredients: List[Ingredient]
    safety_report: Optional[SafetyAudit]

    # final output
    coach_advice: str
    # Single-language renderings of the coach card (the UI shows one per its
    # selected language); coach_advice keeps the combined bilingual blob.
    coach_advice_ja: Optional[str]
    coach_advice_en: Optional[str]
    routine_recommendations: List[str]
    # Structured English coach card (timing / application_notes / warnings) used
    # to persist per-product routine metadata when a scan is saved to the shelf.
    coach_card: Optional[dict]
    # 0–5 "leaf" recommendability score for THIS user (goals / concerns / budget)
    # plus a one-sentence rationale in each language. None for anonymous scans.
    recommendation_score: Optional[int]
    recommendation_rationale_ja: Optional[str]
    recommendation_rationale_en: Optional[str]

    # system flags
    is_ready_for_logic: bool
    retake_requested: bool
    correction_attempts: int
    correction_feedback: Optional[str]
    trace_id: Optional[str]

    # detected label language (recorded for reporting; no longer gated on)
    detected_language: Optional[str]

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


def inci_names(standardized: Optional[List[dict]]) -> List[str]:
    """Canonical INCI names from a normalizer-shaped ingredient list.

    Each normalizer row carries a ``name_standardized`` field that is the INCI
    key, or ``None`` when the name could not be mapped. Unmapped rows are dropped
    so callers always see auditable canonical names. Order is preserved.
    """
    return [
        item["name_standardized"]
        for item in (standardized or [])
        if item.get("name_standardized")
    ]


def build_initial_state(
    image_path: str,
    image_type: Optional[str] = None,
    *,
    user_profile: Optional[UserProfile] = None,
    user_name: Optional[str] = None,
    routine_products: Optional[List[RoutineProduct]] = None,
) -> dict:
    """Assemble the graph's initial state with all flags at their defaults.

    Single source of truth for the entry-point dict so the CLI, the API service,
    and the interactive scripts can't drift on which keys the graph expects.
    """
    return {
        "image_path": image_path,
        "image_type": image_type,
        "extracted_data": None,
        "inference_confidence": 0.0,
        "correction_attempts": 0,
        "correction_feedback": None,
        "retake_requested": False,
        "is_ready_for_logic": False,
        "user_profile": user_profile,
        "user_name": user_name,
        "routine_products": routine_products,
    }
