# Shared conflict-matrix helpers.
#
# The conflict matrix (data/conflict_matrix.json) groups canonical INCI names
# into active families (Retinoids, AHA, Vitamin C, ...) and lists pairwise rules
# between those families. Both the single-product auditor and the cross-product
# routine advisor reason over the same groups/rules, so the loading and group
# logic live here as one source of truth.
import json
import logging
from typing import Dict, List, Optional, Set, Tuple

from src.config import CONFLICT_MATRIX_PATH

# Loaded once on first call, then reused across invocations.
_CONFLICTS_CACHE: Optional[dict] = None

# (new_group, new_hits, existing_group, existing_hits, severity, reason)
CrossFinding = Tuple[str, List[str], str, List[str], str, str]


def load_conflict_matrix() -> dict:
    """Load the group-based conflict matrix: {"groups": {...}, "rules": [...]}."""
    global _CONFLICTS_CACHE
    if _CONFLICTS_CACHE is None:
        with open(CONFLICT_MATRIX_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        logging.info(
            "Conflicts: loaded %d rule(s) over %d group(s).",
            len(data.get("rules", [])),
            len(data.get("groups", {})),
        )
        _CONFLICTS_CACHE = data
    return _CONFLICTS_CACHE


def present_groups(inci: Set[str]) -> Dict[str, List[str]]:
    """Active conflict-groups present in ``inci``, mapped to their member hits.

    Only groups with at least one present member are returned.
    """
    groups = load_conflict_matrix().get("groups", {})
    result: Dict[str, List[str]] = {}
    for name, members in groups.items():
        hits = [m for m in members if m in inci]
        if hits:
            result[name] = hits
    return result


def cross_conflicts(
    new_groups: Dict[str, List[str]],
    existing_groups: Dict[str, List[str]],
) -> List[CrossFinding]:
    """Conflict rules firing between two *separate* products' group sets.

    Each rule pairs two groups; it fires when one product carries a member of
    one group and the other product carries a member of the other. Both
    orientations are checked (the new product may sit on either side of a rule),
    but a rule yields at most one finding per product pair.
    """
    findings: List[CrossFinding] = []
    for rule in load_conflict_matrix().get("rules", []):
        name_a, name_b = rule["groups"]
        for new_name, ex_name in ((name_a, name_b), (name_b, name_a)):
            new_hits = new_groups.get(new_name)
            ex_hits = existing_groups.get(ex_name)
            if new_hits and ex_hits:
                findings.append(
                    (
                        new_name,
                        new_hits,
                        ex_name,
                        ex_hits,
                        rule.get("severity", "medium"),
                        rule["reason"],
                    )
                )
                break  # one finding per rule, regardless of orientation
    return findings
