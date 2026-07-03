# Shared conflict-matrix helpers.
#
# The conflict matrix (data/conflict_matrix.json) groups canonical INCI names
# into active families (Retinoids, AHA, Vitamin C, ...) and lists pairwise rules
# between those families. Both the single-product auditor and the cross-product
# routine advisor reason over the same groups/rules, so the loading and group
# logic live here as one source of truth.
import json
import logging

from src.config import CONFLICT_MATRIX_PATH

# Loaded once on first call, then reused across invocations.
_CONFLICTS_CACHE: dict | None = None

# (new_group, new_hits, existing_group, existing_hits, severity, reason)
CrossFinding = tuple[str, list[str], str, list[str], str, str]


def load_conflict_matrix() -> dict:
    """Load the group-based conflict matrix: {"groups": {...}, "rules": [...]}."""
    global _CONFLICTS_CACHE
    if _CONFLICTS_CACHE is None:
        with open(CONFLICT_MATRIX_PATH, encoding="utf-8") as f:
            data = json.load(f)
        logging.info(
            "Conflicts: loaded %d rule(s) over %d group(s).",
            len(data.get("rules", [])),
            len(data.get("groups", {})),
        )
        _CONFLICTS_CACHE = data
    return _CONFLICTS_CACHE


def present_groups(inci: set[str]) -> dict[str, list[str]]:
    """Active conflict-groups present in ``inci``, mapped to their member hits.

    Only groups with at least one present member are returned.
    """
    groups = load_conflict_matrix().get("groups", {})
    result: dict[str, list[str]] = {}
    for name, members in groups.items():
        hits = [m for m in members if m in inci]
        if hits:
            result[name] = hits
    return result


def cross_conflicts(
    new_groups: dict[str, list[str]],
    existing_groups: dict[str, list[str]],
) -> list[CrossFinding]:
    """Conflict rules firing between two *separate* products' group sets.

    Each rule pairs two groups; it fires when one product carries a member of
    one group and the other product carries a member of the other. Both
    orientations are checked (the new product may sit on either side of a rule),
    but a rule yields at most one finding per product pair.
    """
    findings: list[CrossFinding] = []
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
