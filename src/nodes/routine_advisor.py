# Routine advisor: deterministic evaluation of a new product against the user's
# saved routine ("shelf"). Like the auditor, it runs no LLM — every finding is
# traceable to the conflict matrix, the function-group taxonomy, or the user's
# stated goals. The coach turns these grounded findings into 薬機法-safe prose.
#
# Three axes:
#   1. Conflicts — the new product's actives clash with an existing product's
#      actives (reuses conflict_matrix.json via src.conflicts).
#   2. Redundancy — the new product duplicates a function category already on the
#      shelf (function_groups.json).
#   3. Value-add — the new product introduces a category that serves a stated
#      user goal the existing routine does not cover yet.
import json
import logging

from src.config import FUNCTION_GROUPS_PATH, GOAL_TO_FUNCTION
from src.conflicts import cross_conflicts, present_groups
from src.state import AgentState, CrossConflict, RoutineFit, RoutineProduct

# Loaded once on first call, then reused across invocations.
_FUNCTION_GROUPS_CACHE: dict[str, list[str]] | None = None


def _load_function_groups() -> dict[str, list[str]]:
    """Load the function/active taxonomy, dropping the leading _comment key."""
    global _FUNCTION_GROUPS_CACHE
    if _FUNCTION_GROUPS_CACHE is None:
        with open(FUNCTION_GROUPS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        _FUNCTION_GROUPS_CACHE = {k: v for k, v in data.items() if not k.startswith("_")}
        logging.info(
            "Routine advisor: loaded %d function category(ies).",
            len(_FUNCTION_GROUPS_CACHE),
        )
    return _FUNCTION_GROUPS_CACHE


def present_function_categories(inci: set[str]) -> dict[str, list[str]]:
    """Function categories present in ``inci``, mapped to their member hits.

    Only categories with at least one present marker are returned.
    """
    result: dict[str, list[str]] = {}
    for name, markers in _load_function_groups().items():
        hits = [m for m in markers if m in inci]
        if hits:
            result[name] = hits
    return result


def _inci_set(ingredients) -> set[str]:
    """Canonical INCI set from either state dicts or a RoutineProduct list."""
    out: set[str] = set()
    for item in ingredients or []:
        if isinstance(item, str):
            out.add(item)
        elif isinstance(item, dict):
            name = item.get("name_standardized")
            if name:
                out.add(name)
    return out


def _label(product: RoutineProduct) -> str:
    return f"{product.brand} — {product.product_name}".strip(" —")


def routine_advisor_node(state: AgentState) -> dict:
    routine: list[RoutineProduct] = state.get("routine_products") or []
    if not routine:
        # No shelf to compare against — nothing to report. Coach skips the section.
        return {"routine_fit": RoutineFit()}

    new_inci = _inci_set(state.get("standardized_ingredients"))
    new_conflict_groups = present_groups(new_inci)
    new_func_cats = present_function_categories(new_inci)

    conflicts: list[CrossConflict] = []
    redundancy: list[str] = []
    shelf_categories: set[str] = set()

    for product in routine:
        label = _label(product)
        ex_inci = _inci_set(product.ingredients)

        # 1. Cross-product safety conflicts.
        for new_g, _new_hits, ex_g, _ex_hits, severity, reason in cross_conflicts(
            new_conflict_groups, present_groups(ex_inci)
        ):
            conflicts.append(
                CrossConflict(
                    with_product=label,
                    severity=severity,
                    groups=(new_g, ex_g),
                    reason=reason,
                )
            )

        # 2. Redundancy: function categories shared with this shelf product.
        ex_func_cats = present_function_categories(ex_inci)
        shelf_categories |= set(ex_func_cats)
        shared = sorted(set(new_func_cats) & set(ex_func_cats))
        if shared:
            redundancy.append(f"Overlaps with {label} — both provide {', '.join(shared)}.")

    # 3. Value-add: categories the new product introduces that serve a stated
    #    goal and are absent from the entire shelf.
    value_add: list[str] = []
    profile = state.get("user_profile")
    goals = profile.goals if profile else []
    for goal in goals:
        for category in GOAL_TO_FUNCTION.get(goal.strip().lower(), []):
            if category in new_func_cats and category not in shelf_categories:
                value_add.append(
                    f"Introduces {category}, targeting your '{goal}' goal "
                    "not yet covered by your routine."
                )

    fit = RoutineFit(
        conflicts=conflicts,
        redundancy=redundancy,
        value_add=value_add,
        existing_products=[_label(p) for p in routine],
    )
    logging.info(
        "Routine advisor: %d shelf product(s), %d conflict(s), %d redundancy, %d value-add.",
        len(routine),
        len(conflicts),
        len(redundancy),
        len(value_add),
    )
    return {"routine_fit": fit}
