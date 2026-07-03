# Request / response contracts for the HTTP layer.
#
# The graph already speaks in Pydantic models (ProductExtraction, SafetyAudit,
# RoutineFit, ...), so the response models below mostly re-expose those nested
# models. AgentState is a TypedDict of loosely-typed dicts; the response models
# pin down exactly which fields the API surfaces and coerce the normalizer's
# plain-dict ingredients into a typed shape.
from typing import Literal

from pydantic import BaseModel, Field

from src.state import CoachResponse, Notice, ProductExtraction, RoutineFit, SafetyAudit, UserProfile

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
    name_standardized: str | None = None
    is_active: bool | None = None
    source_language: str | None = None


class ScanResponse(BaseModel):
    """Serialised final graph state for a single scan."""

    status: ScanStatus = Field(description="High-level outcome of the scan.")
    trace_id: str | None = None
    model_used: str | None = Field(
        None, description="Which path produced the extraction: flash | pro | database | web."
    )
    inference_confidence: float | None = None
    registry_matched: bool | None = None
    ingredient_source: str | None = Field(
        None, description="Where the ingredient list came from: registry | label | web."
    )
    detected_language: str | None = None

    product: ProductExtraction | None = Field(
        None, description="Brand, product name, and raw extracted ingredients."
    )
    standardized_ingredients: list[NormalizedIngredient] = Field(default_factory=list)
    unmatched_ingredients: list[str] = Field(
        default_factory=list, description="Raw names with no INCI mapping (surfaced, not fatal)."
    )
    safety_report: SafetyAudit | None = None
    routine_fit: RoutineFit | None = Field(
        None, description="Cross-product evaluation against the user's saved routine."
    )

    coach: CoachResponse | None = Field(
        None,
        description=(
            "The coach's structured bilingual recommendation: one card per "
            "language (verdict, warnings, timing, ...) plus routine-fit notes. "
            "None on graceful exits."
        ),
    )
    notice: Notice | None = Field(
        None,
        description=(
            "Bilingual graceful-exit message (retake / identity / search); "
            "the UI renders the language matching its locale."
        ),
    )
    web_sources: list[str] = Field(default_factory=list)

    added_product_id: str | None = Field(
        None, description="Set when add_to_routine saved this product to the shelf."
    )


# --- /scan/followup -----------------------------------------------------------


class FollowupRequest(BaseModel):
    """One follow-up question about a completed scan, plus its grounding.

    Stateless: the client sends back the scan results it already holds (product
    identity, verified ingredients, safety report, routine fit) so the server
    needs no conversation store and never re-scans.
    """

    brand: str = ""
    product_name: str = ""
    standardized_ingredients: list[NormalizedIngredient] = Field(default_factory=list)
    safety_report: SafetyAudit | None = None
    routine_fit: RoutineFit | None = None
    question: str = Field(min_length=1, max_length=500)
    lang: Literal["ja", "en"] = "ja"
    user_id: str | None = Field(None, description="Saved user id; reloads their profile + routine.")


class FollowupResponse(BaseModel):
    answer: str = Field(description="The grounded answer, in the requested language.")


# --- users ------------------------------------------------------------------


class UserUpsertRequest(BaseModel):
    """Create or replace a user: an optional display name plus their profile."""

    name: str | None = None
    profile: UserProfile


class UserCreateResponse(BaseModel):
    user_id: str


class UserSummary(BaseModel):
    user_id: str
    name: str | None = None


class UserDetail(BaseModel):
    user_id: str
    name: str | None = None
    profile: UserProfile


# --- routine ("shelf") ------------------------------------------------------


class RoutineProductRequest(BaseModel):
    """Manually add a product to a user's routine (without a scan)."""

    brand: str
    product_name: str
    ingredients: list[str] = Field(
        default_factory=list, description="Canonical INCI names of the product."
    )
    is_quasi_drug: bool | None = None


class RoutineProductResponse(BaseModel):
    product_id: str


# --- routine dashboard ------------------------------------------------------


class RoutineDashboardCard(BaseModel):
    """One product on the routine dashboard: the saved row plus derived fields."""

    product_id: str
    brand: str
    product_name: str
    ingredients: list[str] = Field(default_factory=list)
    is_quasi_drug: bool | None = None
    timing: str = Field(description="Resolved 'AM' | 'PM' | 'AM & PM'.")
    application_notes: list[str] = Field(default_factory=list)
    price_usd: float | None = None
    price_native: float | None = None
    price_currency: str | None = None
    price_market: str | None = None
    months_supply: float | None = None
    price_source: str | None = None
    monthly_cost_usd: float | None = Field(
        None, description="Amortized monthly USD cost (price ÷ months of supply)."
    )
    monthly_cost_native: float | None = Field(
        None, description="Amortized monthly cost in the product's native currency."
    )


class GoalCoverage(BaseModel):
    """Whether the routine addresses one stated goal, and via which categories."""

    goal: str
    covered: bool | None = Field(
        None, description="True/False, or None when the goal can't be assessed."
    )
    addressed_by: list[str] = Field(
        default_factory=list,
        description="Function categories present in the routine that serve this goal.",
    )


class RoutineDashboard(BaseModel):
    """Aggregated 'My Routine' view: products, monthly cost, and goal coverage."""

    products: list[RoutineDashboardCard] = Field(default_factory=list)
    monthly_cost_usd: float | None = Field(
        None, description="Amortized total monthly cost in USD; None if unpriced."
    )
    monthly_cost_jpy: float | None = Field(
        None, description="Amortized total monthly cost in JPY (JPY-priced items only)."
    )
    currency: str = "USD"
    goals: list[GoalCoverage] = Field(default_factory=list)
    leaf_score: int = Field(
        0, ge=0, le=5, description="0–5 leaves: how well the routine covers the goals."
    )
