# Safety auditor: deterministic analysis over the normalized INCI names.
#
# Runs after the normalizer, so it sees canonical INCI keys rather than raw
# label text. Two passes:
#   1. Pairwise conflicts  — both members of a conflict rule present together.
#   2. Single-ingredient risks — irritants, sensitizers, or regulated agents.
# Produces a SafetyAudit the coach node can turn into grounded advice. No LLM
# call — every finding is traceable to a row in the data files.
import json
import logging
from typing import Dict, List, Optional, Set

from src.conflicts import load_conflict_matrix
from src.state import AgentState, SafetyAudit
from src.config import (
    IRRITANT_REGISTRY_PATH,
    CONFLICT_PENALTY,
    IRRITANT_PENALTY,
)

# Loaded once on first call, then reused across invocations.
_IRRITANTS_CACHE: Optional[Dict[str, dict]] = None


def _load_irritants() -> Dict[str, dict]:
    """Load the irritant registry, keyed by canonical INCI name."""
    global _IRRITANTS_CACHE
    if _IRRITANTS_CACHE is None:
        with open(IRRITANT_REGISTRY_PATH, "r", encoding="utf-8") as f:
            rows = json.load(f)
        _IRRITANTS_CACHE = {row["ingredient"]: row for row in rows}
        logging.info("Auditor: loaded %d irritant entry(ies).", len(_IRRITANTS_CACHE))
    return _IRRITANTS_CACHE


def _present_inci(state: AgentState) -> Set[str]:
    """Collect the canonical INCI keys present on the product.

    The normalizer writes dict entries with a ``name_standardized`` field that
    is the INCI key, or ``None`` when the name could not be mapped. Only mapped
    names can be audited reliably, so unmapped ones are skipped here and
    surfaced separately via ``unmatched_ingredients``.
    """
    items = state.get("standardized_ingredients") or []
    return {
        item["name_standardized"]
        for item in items
        if item.get("name_standardized")
    }


def auditor_node(state: AgentState) -> dict:
    present = _present_inci(state)
    conflicts = load_conflict_matrix()
    irritants = _load_irritants()

    score = 1.0
    ingredient_conflicts: List[str] = []
    risk_ingredients: List[str] = []
    warnings: List[str] = []

    # Pass 1: group conflicts — fire when an ingredient from each group is present.
    groups = conflicts.get("groups", {})
    for rule in conflicts.get("rules", []):
        name_a, name_b = rule["groups"]
        found_a = [inci for inci in groups.get(name_a, []) if inci in present]
        found_b = [inci for inci in groups.get(name_b, []) if inci in present]
        if not (found_a and found_b):
            continue
        # If groups overlap and the only hit is the same single ingredient on
        # both sides, that's not a real pairing — skip it.
        if found_a == found_b and len(found_a) == 1:
            continue
        severity = rule.get("severity", "medium")
        score -= CONFLICT_PENALTY.get(severity, 0.15)
        detail_a = f"{name_a} ({', '.join(found_a)})"
        detail_b = f"{name_b} ({', '.join(found_b)})"
        message = f"{detail_a} + {detail_b}: {rule['reason']}"
        ingredient_conflicts.append(message)
        warnings.append(f"[{severity.upper()}] {message}")

    # Pass 2: single-ingredient risks — sorted for stable, readable output.
    for inci in sorted(present):
        row = irritants.get(inci)
        if row is None:
            continue
        level = row.get("level", "low")
        score -= IRRITANT_PENALTY.get(level, 0.03)
        risk_ingredients.append(inci)
        warnings.append(f"[{level.upper()}] {inci}: {row['reason']}")

    # Be explicit about ingredients we could not audit (no INCI mapping).
    unmatched = state.get("unmatched_ingredients") or []
    if unmatched:
        warnings.append(
            f"[INFO] {len(unmatched)} ingredient(s) had no INCI mapping and were "
            "not safety-audited."
        )

    score = max(0.0, min(1.0, round(score, 2)))

    total = len(state.get("standardized_ingredients") or [])
    logging.info(
        "Auditor: %d/%d audited, %d conflict(s), %d risk ingredient(s), score=%.2f.",
        len(present),
        total,
        len(ingredient_conflicts),
        len(risk_ingredients),
        score,
    )

    report = SafetyAudit(
        ingredient_conflicts=ingredient_conflicts,
        risk_ingredients=risk_ingredients,
        warnings=warnings,
        safety_score=score,
    )
    return {"safety_report": report}
