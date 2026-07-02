# Request / response contracts for the HTTP layer.
#
# The graph already speaks in Pydantic models (ProductExtraction, SafetyAudit,
# RoutineFit, ...), so the response models below mostly re-expose those nested
# models. AgentState is a TypedDict of loosely-typed dicts; the response models
# pin down exactly which fields the API surfaces and coerce the normalizer's
# plain-dict ingredients into a typed shape.
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from src.state import (CoachResponse, Notice, ProductExtraction, RoutineFit,
                       SafetyAudit, UserProfile)

# --- /scan ------------------------------------------------------------------

# Where the final graph state landed, summarised for the client:
#   complete        — a full recommendation card was produced.
#   retake_required — the label couldn't be read; the user should retake.
#   action_needed   — identity/ingredients unresolved; notice says what to do.
#   incomplete      — the graph exited without advice (unexpected; inspect fields).
ScanStatus = Literal["complete", "retake_required", "action_needed", "incomplete"]


class NormalizedIngredient(BaseModel):
    """One normalizer output row (raw label name → canonical INCI key)."""

    name_raw: str
    name_standardized: Optional[str] = None
    is_active: Optional[bool] = None
    source_language: Optional[str] = None


class ScanResponse(BaseModel):
    """Serialised final graph state for a single scan."""

    status: ScanStatus = Field(description="High-level outcome of the scan.")
    trace_id: Optional[str] = None
    model_used: Optional[str] = Field(
        None, description="Which path produced the extraction: flash | pro | database | web."
    )
    inference_confidence: Optional[float] = None
    registry_matched: Optional[bool] = None
    ingredient_source: Optional[str] = Field(
        None, description="Where the ingredient list came from: registry | label | web."
    )
    detected_language: Optional[str] = None

    product: Optional[ProductExtraction] = Field(
        None, description="Brand, product name, and raw extracted ingredients."
    )
    standardized_ingredients: List[NormalizedIngredient] = Field(default_factory=list)
    unmatched_ingredients: List[str] = Field(
        default_factory=list, description="Raw names with no INCI mapping (surfaced, not fatal)."
    )
    safety_report: Optional[SafetyAudit] = None
    routine_fit: Optional[RoutineFit] = Field(
        None, description="Cross-product evaluation against the user's saved routine."
    )

    coach: Optional[CoachResponse] = Field(
        None,
        description=(
            "The coach's structured bilingual recommendation: one card per "
            "language (verdict, warnings, timing, ...) plus routine-fit notes. "
            "None on graceful exits."
        ),
    )
    notice: Optional[Notice] = Field(
        None,
        description=(
            "Bilingual graceful-exit message (retake / identity / search); "
            "the UI renders the language matching its locale."
        ),
    )
    web_sources: List[str] = Field(default_factory=list)

    added_product_id: Optional[str] = Field(
        None, description="Set when add_to_routine saved this product to the shelf."
    )


# --- users ------------------------------------------------------------------


class UserUpsertRequest(BaseModel):
    """Create or replace a user: an optional display name plus their profile."""

    name: Optional[str] = None
    profile: UserProfile


class UserCreateResponse(BaseModel):
    user_id: str


class UserSummary(BaseModel):
    user_id: str
    name: Optional[str] = None


class UserDetail(BaseModel):
    user_id: str
    name: Optional[str] = None
    profile: UserProfile


# --- routine ("shelf") ------------------------------------------------------


class RoutineProductRequest(BaseModel):
    """Manually add a product to a user's routine (without a scan)."""

    brand: str
    product_name: str
    ingredients: List[str] = Field(
        default_factory=list, description="Canonical INCI names of the product."
    )
    is_quasi_drug: Optional[bool] = None


class RoutineProductResponse(BaseModel):
    product_id: str


# --- routine dashboard ------------------------------------------------------


class RoutineDashboardCard(BaseModel):
    """One product on the routine dashboard: the saved row plus derived fields."""

    product_id: str
    brand: str
    product_name: str
    ingredients: List[str] = Field(default_factory=list)
    is_quasi_drug: Optional[bool] = None
    timing: str = Field(description="Resolved 'AM' | 'PM' | 'AM & PM'.")
    application_notes: List[str] = Field(default_factory=list)
    price_usd: Optional[float] = None
    price_native: Optional[float] = None
    price_currency: Optional[str] = None
    price_market: Optional[str] = None
    months_supply: Optional[float] = None
    price_source: Optional[str] = None
    monthly_cost_usd: Optional[float] = Field(
        None, description="Amortized monthly USD cost (price ÷ months of supply)."
    )
    monthly_cost_native: Optional[float] = Field(
        None, description="Amortized monthly cost in the product's native currency."
    )


class GoalCoverage(BaseModel):
    """Whether the routine addresses one stated goal, and via which categories."""

    goal: str
    covered: Optional[bool] = Field(
        None, description="True/False, or None when the goal can't be assessed."
    )
    addressed_by: List[str] = Field(
        default_factory=list,
        description="Function categories present in the routine that serve this goal.",
    )


class RoutineDashboard(BaseModel):
    """Aggregated 'My Routine' view: products, monthly cost, and goal coverage."""

    products: List[RoutineDashboardCard] = Field(default_factory=list)
    monthly_cost_usd: Optional[float] = Field(
        None, description="Amortized total monthly cost in USD; None if unpriced."
    )
    monthly_cost_jpy: Optional[float] = Field(
        None, description="Amortized total monthly cost in JPY (JPY-priced items only)."
    )
    currency: str = "USD"
    goals: List[GoalCoverage] = Field(default_factory=list)
    leaf_score: int = Field(
        0, ge=0, le=5, description="0–5 leaves: how well the routine covers the goals."
    )
