from typing import Literal, TypedDict, cast
from uuid import uuid4

from pydantic import BaseModel, Field


class Ingredient(BaseModel):
    name_raw: str = Field(
        ..., description="original name of the ingredient as extracted from the image"
    )
    name_standardized: str | None = Field(None, description="standardized name of the ingredient")
    is_active: bool | None = Field(
        None, description="whether this ingredient is an active (functional) ingredient"
    )
    source_language: str = Field(
        "JP", description="language of the ingredient name as extracted from the image"
    )
    confidence: float | None = Field(
        None,
        description=(
            "0.0-1.0 confidence that THIS ingredient name was read correctly off "
            "the label. Use < 0.7 when the name is blurry, curved, partially "
            "occluded, or was guessed from context."
        ),
    )


class ProductExtraction(BaseModel):
    brand: str = Field(..., description="brand of the product as extracted from the image")
    product_name: str = Field(..., description="name of the product as extracted from the image")
    jan_code: str | None = Field(
        None, description="JAN code of the product as extracted from the image"
    )
    ingredients: list[Ingredient] = Field(
        ..., description="list of ingredients extracted from the image"
    )
    is_quasi_drug: bool | None = Field(
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


class Notice(BaseModel):
    """A bilingual user-facing message for graceful-exit paths.

    Carries both languages so the UI can render the one matching its locale;
    the CLI prints ``en``.
    """

    en: str
    ja: str


class SafetyAudit(BaseModel):
    ingredient_conflicts: list[str] = Field(
        default_factory=list,
        description="pairwise ingredient conflicts found, e.g. 'Retinol + Ascorbic Acid: ...'",
    )
    risk_ingredients: list[str] = Field(
        default_factory=list,
        description="individual INCI names flagged as irritant, sensitizer, or regulated",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="human-readable, severity-tagged warning lines for the coach node",
    )
    # Japanese renderings of the two user-facing lists above, built deterministically
    # by the auditor from the hand-written reason_ja / group_labels_ja in the data
    # files (no LLM in the safety path). The English lists stay the coach's input;
    # the JA UI reads these. Empty when there are no findings.
    ingredient_conflicts_ja: list[str] = Field(default_factory=list)
    warnings_ja: list[str] = Field(default_factory=list)
    safety_score: float = Field(
        1.0,
        description="0.0 (high concern) to 1.0 (no flags); starts at 1.0, penalized per finding",
    )


class UserProfile(BaseModel):
    skin_type: Literal["dry", "oily", "combination", "normal", "sensitive"] | None = None
    age: int | None = None
    # "male" | "female" | "other" (non-binary / prefer not to disclose). Kept as a
    # free str (not a Literal) so older profiles and any future values still load.
    gender: str | None = None
    # Fitzpatrick phototype I–VI as an int 1–6, with the undertone palette the user
    # picked it from (Asian skins skew warm/olive, others cooler/pink at the same
    # phototype) — both feed the coach's sun-sensitivity guidance.
    fitzpatrick: int | None = Field(
        None, ge=1, le=6, description="Fitzpatrick phototype, 1 (I) to 6 (VI)"
    )
    skin_undertone: Literal["asian", "non_asian"] | None = None
    goals: list[str] = Field(
        default_factory=list,
        description="skin concerns, e.g. fine lines, hyperpigmentation, acne, redness",
    )
    is_pregnant: bool = False
    skin_conditions: list[str] = Field(
        default_factory=list,
        description="e.g. eczema, rosacea, acne, psoriasis, hyperpigmentation",
    )
    sun_damage_history: Literal["none", "mild", "moderate", "severe"] | None = None
    routine_time: Literal["minimal", "moderate", "extensive"] | None = None
    # When True, the coach may also suggest devices / at-home treatments (LED masks,
    # at-home IPL, microneedle stamps, gua sha, etc.) on top of topical products.
    consider_devices: bool = False
    # Monthly skincare budget in USD. 0 means no spend; 250 is treated as "$250+".
    budget: int | None = Field(None, ge=0, description="monthly budget in USD")


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
    ingredients: list[str] = Field(
        default_factory=list,
        description="canonical INCI names of the saved product",
    )
    is_quasi_drug: bool | None = Field(
        None, description="whether the saved product is a quasi-drug"
    )
    # When to use the product: "AM" | "PM" | "AM & PM". None until classified.
    timing: str | None = Field(None, description="best time to use: 'AM', 'PM', or 'AM & PM'")
    # Short application/sequencing cautions (e.g. "apply to completely dry skin",
    # "wait ~1 min before the next layer"), from the coach card. Stored per language
    # so the routine dashboard can show notes in the user's UI language; the legacy
    # ``application_notes`` field is the English copy (older rows only have this one).
    application_notes: list[str] = Field(
        default_factory=list,
        description="how-to-apply / sequencing notes for this product (English)",
    )
    application_notes_ja: list[str] = Field(
        default_factory=list,
        description="Japanese how-to-apply / sequencing notes for this product",
    )
    # Amortizable price info, looked up once at add-time (best-effort).
    price_usd: float | None = Field(None, description="unit price converted to USD")
    price_native: float | None = Field(None, description="unit price in its native market currency")
    price_currency: str | None = Field(
        None, description="native currency code, e.g. JPY, USD, EUR, KRW"
    )
    price_market: str | None = Field(
        None, description="market the price came from: 'JP' or the origin code"
    )
    months_supply: float | None = Field(
        None, description="estimated months one unit lasts for a daily user"
    )
    price_source: str | None = Field(None, description="URL the price was sourced from")


class CrossConflict(BaseModel):
    """One deterministic conflict between the new product and a shelf product."""

    with_product: str = Field(
        ..., description="the existing routine product the new one conflicts with"
    )
    severity: str = Field("medium", description="high | medium | low")
    groups: tuple[str, str] = Field(
        ..., description="the two conflicting active groups (new side, existing side)"
    )
    reason: str = Field(..., description="why the two groups conflict (from the matrix)")


class RoutineFit(BaseModel):
    """Deterministic evaluation of a new product against the user's routine.

    Computed by ``routine_advisor_node``; the coach turns these grounded findings
    into 薬機法-safe bilingual prose. Empty lists mean "nothing to report".
    """

    conflicts: list[CrossConflict] = Field(
        default_factory=list,
        description="cross-product active conflicts with existing routine products",
    )
    redundancy: list[str] = Field(
        default_factory=list,
        description="roles the new product duplicates from the existing routine",
    )
    value_add: list[str] = Field(
        default_factory=list,
        description="unmet user goals the new product would help target",
    )
    existing_products: list[str] = Field(
        default_factory=list,
        description="'Brand — Product' labels of the current routine, for context",
    )


class Recommendation(BaseModel):
    """One complete recommendation card, written entirely in a single language."""

    verdict: str = Field(
        default="",
        description=(
            "The headline: 1–2 warm, specific sentences giving the overall call "
            "on this product for this user — the main reason it does (or does "
            "not) suit them, plus the single most important caution if there is "
            "one. A knowledgeable friend's bottom line, not a summary of every "
            "field below."
        ),
    )
    product: str = Field(
        default="",
        description="The scanned product as 'Brand — Product Name'.",
    )
    purpose: str = Field(
        default="",
        description="ONE sentence describing what this product is intended for.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description=(
            "User-tailored cautions, one concern per item, ordered by importance "
            "to THIS user — the first three must be the ones they genuinely "
            "need. MUST flag if the product can make skin more prone to "
            "dehydration or sun damage. Empty list if there are genuinely none."
        ),
    )
    timing: str = Field(
        default="",
        description="Best time to use: exactly 'AM', 'PM', or 'AM & PM'.",
    )
    frequency: str = Field(
        default="",
        description="How often to use, e.g. 'Daily' or '2–3 times per week'.",
    )
    application_notes: list[str] = Field(
        default_factory=list,
        description=(
            "Short how-to-apply / sequencing cautions, one per item, e.g. "
            "'apply to completely dry skin', 'wait ~1 minute before the next "
            "layer', 'avoid if skin is irritated from a PM retinoid'. Empty if "
            "there is nothing special about how to apply it."
        ),
    )
    recommendation_rationale: str = Field(
        default="",
        description=(
            "ONE short sentence explaining the recommendation_score: why this "
            "product does (or does not) suit this user, citing the main driver "
            "— a goal it serves, a concern/skin-type it raises, or budget fit."
        ),
    )
    routine_integration: str = Field(
        default="",
        description=(
            "One or two sentences on how to slot THIS product into the user's "
            "CURRENT routine: where in the sequence it goes, which existing "
            "products to pair it with or alternate against, and its AM/PM "
            "placement relative to what they already use. Name the actual "
            "existing products when a Routine Context block is provided; "
            "otherwise describe where it fits in a typical routine."
        ),
    )


class RoutineFitCard(BaseModel):
    """How the product fits the user's existing routine, in a single language.

    Populated only when a Routine Context block is provided; otherwise empty.
    """

    risks: list[str] = Field(
        default_factory=list,
        description=(
            "One line per cross-product conflict from the routine context, "
            "naming the existing product. Empty if none."
        ),
    )
    redundancy: list[str] = Field(
        default_factory=list,
        description="Gentle notes that the product overlaps an existing one.",
    )
    value_add: list[str] = Field(
        default_factory=list,
        description="How the product helps an otherwise-uncovered user goal.",
    )


class CoachResponse(BaseModel):
    """The coach's full structured output: one card per language + routine fit.

    Doubles as the LLM's structured-output schema and the API's coach payload —
    the single source of truth the UI, the CLI renderer, and shelf persistence
    all read from. ``recommendation_score`` is cleared (None) for anonymous
    scans, where a personal fit score has no meaning.
    """

    recommendation_score: int | None = Field(
        default=None,
        ge=0,
        le=5,
        description=(
            "0–5 leaves: how well THIS product suits THIS user, weighing their "
            "goals (does it contain ingredients that serve them), concerns / "
            "skin type (appropriate or risky), and budget (does its price band "
            "fit). 5 = excellent fit on all three; 0 = poorly suited or risky. "
            "Set once; it is language-independent."
        ),
    )
    japanese: Recommendation = Field(
        description="The card written ONLY in Japanese (敬体, 薬機法-compliant)."
    )
    english: Recommendation = Field(description="The same card written ONLY in English.")
    routine_japanese: RoutineFitCard = Field(
        default_factory=RoutineFitCard,
        description="Routine-fit notes in Japanese; empty if no routine context.",
    )
    routine_english: RoutineFitCard = Field(
        default_factory=RoutineFitCard,
        description="Routine-fit notes in English; empty if no routine context.",
    )


# graph state: shared memory bus between nodes, also used for routing decisions
class AgentState(TypedDict):
    # input data
    image_path: str
    # None on input → the classify_side node auto-detects front vs back.
    image_type: Literal["front", "back"] | None

    # input gating
    # Tier-1 pixel pre-flight verdict (set by the image-quality gate): None when
    # the frame passed, else a reason code ("too_dark" | "too_bright" | "blank" |
    # "blurry" | "unreadable") used to craft the retake message.
    image_quality_issue: str | None
    # Tier-2 content classification from the side/content classifier: "product",
    # "not_a_product", "non_skincare_product", or "multiple_products". Frames
    # that aren't a single skincare product are rejected before extraction so
    # the scanner never fabricates one.
    image_content: str | None
    # The Tier-2 classifier's own 0-1 confidence in its content+side verdict;
    # verdicts below CLASSIFY_CONFIDENCE_THRESHOLD are bounced for a retake.
    classify_confidence: float | None
    # JAN/EAN barcode digits decoded deterministically from the frame (pyzbar,
    # when installed) — the strongest identity key for the registry lookup.
    jan_code: str | None

    # extraction state
    extracted_data: ProductExtraction | None
    model_used: Literal["flash", "pro", "database", "web"]
    inference_confidence: float
    # Grounded extraction-quality signal: fraction of extracted ingredient names
    # that resolve in the normalizer ledger's exact tier (None when there are no
    # ingredients to check, e.g. front photos). Unlike inference_confidence this
    # cannot be hallucinated by the model.
    ledger_match_rate: float | None
    # Advisory OCR cross-check (opt-in): fraction of the VLM's ingredient names
    # also found by the local OCR pass. None when the check is disabled.
    ocr_agreement: float | None

    # processed data — normalizer rows are plain dicts
    # ({name_raw, name_standardized, is_active, source_language}), not Ingredient models.
    standardized_ingredients: list[dict]
    safety_report: SafetyAudit | None

    # final output
    # Bilingual channel for graceful exits (retake / identity / search miss):
    # a short message telling the user what to do. Complete scans carry their
    # result in coach_cards instead.
    notice: Notice | None
    # The coach's structured bilingual output — the single source of truth the
    # API, the web UI, the CLI renderer, and shelf persistence all read from.
    coach_cards: CoachResponse | None

    # system flags
    is_ready_for_logic: bool
    retake_requested: bool
    correction_attempts: int
    correction_feedback: str | None
    trace_id: str | None

    # registry + normalization
    registry_matched: bool | None
    unmatched_ingredients: list[str] | None

    # web-search fallback (last resort when registry + photo both lack a list)
    identity_confidence: float | None
    ingredient_source: str | None  # "registry" | "label" | "web"
    web_sources: list[str] | None
    # True when the web search found *a* product but its identity did not match
    # what was read off the photo — the list is not adopted and the user is
    # asked to confirm instead (never audit another product's ingredients).
    web_identity_mismatch: bool | None

    # personalised coaching
    user_profile: UserProfile | None
    user_name: str | None

    # routine memory: the user's saved "shelf" (loaded at entry) and the
    # deterministic cross-product evaluation of the new scan against it.
    routine_products: list[RoutineProduct] | None
    routine_fit: RoutineFit | None


def inci_names(standardized: list[dict] | None) -> list[str]:
    """Canonical INCI names from a normalizer-shaped ingredient list.

    Each normalizer row carries a ``name_standardized`` field that is the INCI
    key, or ``None`` when the name could not be mapped. Unmapped rows are dropped
    so callers always see auditable canonical names. Order is preserved.
    """
    return [
        item["name_standardized"] for item in (standardized or []) if item.get("name_standardized")
    ]


def build_initial_state(
    image_path: str,
    image_type: str | None = None,
    *,
    user_profile: UserProfile | None = None,
    user_name: str | None = None,
    routine_products: list[RoutineProduct] | None = None,
) -> AgentState:
    """Assemble the graph's initial state with all flags at their defaults.

    Single source of truth for the entry-point dict so the CLI, the API service,
    and the interactive scripts can't drift on which keys the graph expects.
    Deliberately partial: the graph fills the remaining AgentState keys.
    """
    return cast(
        AgentState,
        {
            "image_path": image_path,
            "image_type": image_type,
            "extracted_data": None,
            "inference_confidence": 0.0,
            "correction_attempts": 0,
            "correction_feedback": None,
            "retake_requested": False,
            "is_ready_for_logic": False,
            # Assigned here (not in the scanners) so every path — including front
            # photos, which skip the scanners entirely — carries a trace id.
            "trace_id": str(uuid4()),
            "user_profile": user_profile,
            "user_name": user_name,
            "routine_products": routine_products,
        },
    )
