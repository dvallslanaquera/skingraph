# Aggregates a user's saved routine into the "My Routine" dashboard payload:
# per-product cards (with a resolved AM/PM timing + amortized monthly cost), the
# routine's total monthly cost in USD, and a per-goal coverage list + 5-leaf score
# describing how well the shelf addresses the user's stated concerns.
#
# All of this is deterministic — it reuses the function/active taxonomy the
# routine advisor already loads (data/function_groups.json) rather than calling an
# LLM. Prices/timing/notes are read straight off the stored RoutineProduct rows
# (populated at scan-save time); timing falls back to a deterministic guess when a
# product was added manually and has none.
from typing import Dict, List, Optional, Set

from src.config import DEFAULT_MONTHS_SUPPLY, GOAL_COVERAGE
from src.nodes.routine_advisor import present_function_categories
from src.state import RoutineProduct
from src.user_store import get_routine, get_user

# Rough application-order rank by function category, so each AM/PM column lists
# products in the order they'd realistically be applied (cleanser → … → SPF).
_STEP_RANK = {
    "Cleanser": 0,
    "Vitamin C": 2,
    "Niacinamide": 2,
    "Retinoids": 2,
    "AHA": 2,
    "BHA": 2,
    "Peptides": 2,
    "Hydration": 3,
    "Barrier": 3,
    "Sunscreen": 5,
}
_DEFAULT_STEP = 2.5


def infer_timing(categories: Set[str]) -> str:
    """Deterministic AM/PM guess for a product with no stored timing.

    Photosensitising / exfoliating actives lean PM; sunscreens are AM; everything
    else is a gentle daily step usable AM & PM.
    """
    if categories & {"Retinoids", "AHA", "BHA"}:
        return "PM"
    if "Sunscreen" in categories:
        return "AM"
    return "AM & PM"


def _step_rank(categories: Set[str]) -> float:
    """Lowest (earliest) application-step rank among a product's categories."""
    ranks = [_STEP_RANK[c] for c in categories if c in _STEP_RANK]
    return min(ranks) if ranks else _DEFAULT_STEP


def _monthly_cost(product: RoutineProduct) -> Optional[float]:
    """Amortized monthly USD cost for one product, or None when unpriced."""
    if product.price_usd is None:
        return None
    months = product.months_supply or DEFAULT_MONTHS_SUPPLY
    if months <= 0:
        months = DEFAULT_MONTHS_SUPPLY
    return round(product.price_usd / months, 2)


def _product_card(product: RoutineProduct) -> dict:
    categories = set(present_function_categories(set(product.ingredients)))
    timing = product.timing or infer_timing(categories)
    return {
        "product_id": product.product_id,
        "brand": product.brand,
        "product_name": product.product_name,
        "ingredients": product.ingredients,
        "is_quasi_drug": product.is_quasi_drug,
        "timing": timing,
        "application_notes": product.application_notes,
        "price_usd": product.price_usd,
        "price_native": product.price_native,
        "price_currency": product.price_currency,
        "price_market": product.price_market,
        "months_supply": product.months_supply,
        "price_source": product.price_source,
        "monthly_cost_usd": _monthly_cost(product),
        "_step": _step_rank(categories),
    }


def _goal_coverage(
    goals: List[str], routine_categories: Set[str]
) -> List[dict]:
    """Per-goal coverage: which present categories address each stated goal.

    ``covered`` is None for goals we have no mapping for (shown as "not assessed").
    """
    out: List[dict] = []
    for goal in goals:
        cats = GOAL_COVERAGE.get(goal.strip().lower())
        if cats is None:
            out.append({"goal": goal, "covered": None, "addressed_by": []})
            continue
        addressed_by = [c for c in cats if c in routine_categories]
        out.append(
            {"goal": goal, "covered": bool(addressed_by), "addressed_by": addressed_by}
        )
    return out


def _leaf_score(goal_coverage: List[dict]) -> int:
    """0–5 leaves: share of assessable goals the routine covers, scaled to 5."""
    assessable = [g for g in goal_coverage if g["covered"] is not None]
    if not assessable:
        return 0
    covered = sum(1 for g in assessable if g["covered"])
    return round(5 * covered / len(assessable))


def build_dashboard(user_id: str) -> Optional[dict]:
    """Assemble the routine dashboard for a user, or None if the user is unknown."""
    profile = get_user(user_id)
    if profile is None:
        return None

    routine = get_routine(user_id)
    cards = [_product_card(p) for p in routine]
    # Within the page, list products in application order (cleanser → … → SPF).
    cards.sort(key=lambda c: c["_step"])

    routine_categories: Set[str] = set()
    for product in routine:
        routine_categories |= set(present_function_categories(set(product.ingredients)))

    monthly = [c["monthly_cost_usd"] for c in cards if c["monthly_cost_usd"] is not None]
    monthly_cost_usd = round(sum(monthly), 2) if monthly else None

    goal_coverage = _goal_coverage(profile.goals, routine_categories)

    for card in cards:  # internal sort key, not part of the response contract
        card.pop("_step", None)

    return {
        "products": cards,
        "monthly_cost_usd": monthly_cost_usd,
        "currency": "USD",
        "goals": goal_coverage,
        "leaf_score": _leaf_score(goal_coverage),
    }
