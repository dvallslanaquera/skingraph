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

from src.config import (
    CONFLICT_PENALTY,
    IRRITANT_PENALTY,
    IRRITANT_REGISTRY_PATH,
)
from src.conflicts import load_conflict_matrix
from src.state import AgentState, SafetyAudit, inci_names

# Loaded once on first call, then reused across invocations.
_IRRITANTS_CACHE: dict[str, dict] | None = None

# Japanese severity tags for the JA warning lines (English uses level.upper()).
# Mirrors the high/medium/low labels the UI's TERMS_JA already shows elsewhere.
_SEVERITY_JA = {"high": "高", "medium": "中", "low": "低"}


def _load_irritants() -> dict[str, dict]:
    """Load the irritant registry, keyed by canonical INCI name."""
    global _IRRITANTS_CACHE
    if _IRRITANTS_CACHE is None:
        with open(IRRITANT_REGISTRY_PATH, encoding="utf-8") as f:
            rows = json.load(f)
        _IRRITANTS_CACHE = {row["ingredient"]: row for row in rows}
        logging.info("Auditor: loaded %d irritant entry(ies).", len(_IRRITANTS_CACHE))
    return _IRRITANTS_CACHE


def _present_inci(state: AgentState) -> set[str]:
    """Collect the canonical INCI keys present on the product.

    The normalizer writes dict entries with a ``name_standardized`` field that
    is the INCI key, or ``None`` when the name could not be mapped. Only mapped
    names can be audited reliably, so unmapped ones are skipped here and
    surfaced separately via ``unmatched_ingredients``.
    """
    return set(inci_names(state.get("standardized_ingredients")))


def auditor_node(state: AgentState) -> dict:
    present = _present_inci(state)
    conflicts = load_conflict_matrix()
    irritants = _load_irritants()

    score = 1.0
    ingredient_conflicts: list[str] = []
    risk_ingredients: list[str] = []
    warnings: list[str] = []
    # Japanese parallels of the two user-facing lists, built from the data files'
    # reason_ja / group_labels_ja (falling back to the English text when absent).
    ingredient_conflicts_ja: list[str] = []
    warnings_ja: list[str] = []
    group_labels_ja = conflicts.get("group_labels_ja", {})

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
        # JA rendering: localized group names + reason; INCI hits stay canonical.
        label_a_ja = group_labels_ja.get(name_a, name_a)
        label_b_ja = group_labels_ja.get(name_b, name_b)
        reason_ja = rule.get("reason_ja", rule["reason"])
        message_ja = (
            f"{label_a_ja}（{', '.join(found_a)}） + "
            f"{label_b_ja}（{', '.join(found_b)}）：{reason_ja}"
        )
        ingredient_conflicts_ja.append(message_ja)
        warnings_ja.append(f"[{_SEVERITY_JA.get(severity, severity)}] {message_ja}")

    # Pass 2: single-ingredient risks — sorted for stable, readable output.
    for inci in sorted(present):
        row = irritants.get(inci)
        if row is None:
            continue
        level = row.get("level", "low")
        score -= IRRITANT_PENALTY.get(level, 0.03)
        risk_ingredients.append(inci)
        warnings.append(f"[{level.upper()}] {inci}: {row['reason']}")
        reason_ja = row.get("reason_ja", row["reason"])
        warnings_ja.append(f"[{_SEVERITY_JA.get(level, level)}] {inci}：{reason_ja}")

    # Be explicit about ingredients we could not audit (no INCI mapping).
    unmatched = state.get("unmatched_ingredients") or []
    if unmatched:
        warnings.append(
            f"[INFO] {len(unmatched)} ingredient(s) had no INCI mapping and were "
            "not safety-audited."
        )
        warnings_ja.append(
            f"[情報] {len(unmatched)}件の成分はINCI名に対応づけできず、"
            "安全性監査の対象外です。"
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
        ingredient_conflicts_ja=ingredient_conflicts_ja,
        warnings_ja=warnings_ja,
        safety_score=score,
    )
    return {"safety_report": report}
