# Tests for the deterministic routine advisor.
#
# Controlled conflict matrix, function-group taxonomy, and goal map are injected
# into the module caches so cross-product conflicts, redundancy, and value-add
# are asserted exactly without depending on the real data files.
import pytest

from src import conflicts
from src.nodes import routine_advisor
from src.state import RoutineProduct, UserProfile

from tests.helpers import std_ingredients

CONFLICTS = {
    "groups": {
        "Retinoids": ["Retinol"],
        "AHA": ["Glycolic Acid", "Lactic Acid"],
        "Vitamin C": ["Ascorbic Acid"],
    },
    "rules": [
        {"groups": ["Retinoids", "AHA"], "severity": "high", "reason": "over-exfoliation"},
    ],
}

FUNCTION_GROUPS = {
    "Vitamin C": ["Ascorbic Acid"],
    "Retinoids": ["Retinol"],
    "Niacinamide": ["Niacinamide"],
    "Hydration": ["Sodium Hyaluronate"],
    "BHA": ["Salicylic Acid"],
}

GOAL_TO_FUNCTION = {
    "brightening": ["Vitamin C", "Niacinamide"],
    "anti_aging": ["Retinoids"],
}


@pytest.fixture
def advisor_data(monkeypatch):
    """Inject controlled conflict + function-group + goal tables."""
    monkeypatch.setattr(conflicts, "_CONFLICTS_CACHE", CONFLICTS)
    monkeypatch.setattr(routine_advisor, "_FUNCTION_GROUPS_CACHE", FUNCTION_GROUPS)
    monkeypatch.setattr(routine_advisor, "GOAL_TO_FUNCTION", GOAL_TO_FUNCTION)


def _product(brand, name, *inci) -> RoutineProduct:
    return RoutineProduct(
        product_id=f"{brand}-{name}",
        brand=brand,
        product_name=name,
        ingredients=list(inci),
    )


def _run(new_inci, routine, goals=None):
    """Run the advisor with a new product (canonical INCI) against a routine."""
    state = {
        "standardized_ingredients": std_ingredients(*[(n, n) for n in new_inci]),
        "routine_products": routine,
        "user_profile": UserProfile(goals=goals or []) if goals is not None else None,
    }
    return routine_advisor.routine_advisor_node(state)["routine_fit"]


# --------------------------------------------------------------------------- #
# empty routine
# --------------------------------------------------------------------------- #
def test_empty_routine_returns_empty_fit(advisor_data):
    fit = _run(["Retinol"], routine=[])
    assert fit.conflicts == []
    assert fit.redundancy == []
    assert fit.value_add == []
    assert fit.existing_products == []


def test_missing_routine_key_returns_empty_fit(advisor_data):
    fit = routine_advisor.routine_advisor_node({})["routine_fit"]
    assert fit.conflicts == [] and fit.redundancy == [] and fit.value_add == []


# --------------------------------------------------------------------------- #
# cross-product conflicts
# --------------------------------------------------------------------------- #
def test_cross_product_conflict_detected(advisor_data):
    shelf = [_product("Acme", "Peel", "Glycolic Acid")]
    fit = _run(["Retinol"], routine=shelf)

    assert len(fit.conflicts) == 1
    c = fit.conflicts[0]
    assert c.severity == "high"
    assert c.with_product == "Acme — Peel"
    assert c.groups == ("Retinoids", "AHA")
    assert c.reason == "over-exfoliation"


def test_conflict_attributed_to_correct_shelf_product(advisor_data):
    shelf = [
        _product("Hydra", "Mist", "Sodium Hyaluronate"),  # no conflict
        _product("Acme", "Peel", "Lactic Acid"),           # AHA → conflicts
    ]
    fit = _run(["Retinol"], routine=shelf)
    assert [c.with_product for c in fit.conflicts] == ["Acme — Peel"]


def test_no_conflict_when_groups_dont_pair(advisor_data):
    shelf = [_product("Bright", "Serum", "Ascorbic Acid")]  # Vitamin C, no rule w/ Retinoids here
    fit = _run(["Retinol"], routine=shelf)
    assert fit.conflicts == []


# --------------------------------------------------------------------------- #
# redundancy
# --------------------------------------------------------------------------- #
def test_redundancy_two_vitamin_c_products(advisor_data):
    shelf = [_product("Bright", "Serum", "Ascorbic Acid")]
    fit = _run(["Ascorbic Acid"], routine=shelf)
    assert len(fit.redundancy) == 1
    assert "Bright — Serum" in fit.redundancy[0]
    assert "Vitamin C" in fit.redundancy[0]


def test_no_redundancy_for_distinct_functions(advisor_data):
    shelf = [_product("Hydra", "Mist", "Sodium Hyaluronate")]  # Hydration
    fit = _run(["Niacinamide"], routine=shelf)                  # Niacinamide
    assert fit.redundancy == []


# --------------------------------------------------------------------------- #
# value-add
# --------------------------------------------------------------------------- #
def test_value_add_when_goal_uncovered(advisor_data):
    shelf = [_product("Hydra", "Mist", "Sodium Hyaluronate")]
    fit = _run(["Niacinamide"], routine=shelf, goals=["brightening"])
    assert len(fit.value_add) == 1
    assert "Niacinamide" in fit.value_add[0]
    assert "brightening" in fit.value_add[0]


def test_no_value_add_when_goal_already_covered(advisor_data):
    # Shelf already has Niacinamide, so a new Niacinamide product adds no new role.
    shelf = [_product("Old", "Serum", "Niacinamide")]
    fit = _run(["Niacinamide"], routine=shelf, goals=["brightening"])
    assert fit.value_add == []


def test_no_value_add_without_matching_goal(advisor_data):
    shelf = [_product("Hydra", "Mist", "Sodium Hyaluronate")]
    fit = _run(["Niacinamide"], routine=shelf, goals=["anti_aging"])
    assert fit.value_add == []


# --------------------------------------------------------------------------- #
# existing products surfaced for the coach
# --------------------------------------------------------------------------- #
def test_existing_products_listed(advisor_data):
    shelf = [_product("Hydra", "Mist", "Sodium Hyaluronate"),
             _product("Acme", "Peel", "Glycolic Acid")]
    fit = _run(["Niacinamide"], routine=shelf, goals=["brightening"])
    assert fit.existing_products == ["Hydra — Mist", "Acme — Peel"]


# --------------------------------------------------------------------------- #
# real data files load and parse
# --------------------------------------------------------------------------- #
def test_real_function_groups_file_loads(monkeypatch):
    monkeypatch.setattr(routine_advisor, "_FUNCTION_GROUPS_CACHE", None)
    groups = routine_advisor._load_function_groups()
    assert "Vitamin C" in groups and "Hydration" in groups
    # The _comment key is dropped.
    assert not any(k.startswith("_") for k in groups)
