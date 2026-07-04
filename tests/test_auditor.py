# Tests for the deterministic safety auditor.
#
# The conflict matrix and irritant registry are injected into the module caches
# as small controlled fixtures, so penalties and findings are asserted exactly
# and the tests don't drift when the real data files change. One test loads the
# real data files to confirm they parse into the expected shapes.
import pytest

from src import conflicts
from src.config import CONFLICT_PENALTY, IRRITANT_PENALTY
from src.nodes import auditor
from tests.helpers import std_ingredients

CONFLICTS = {
    "groups": {
        "Retinoids": ["Retinol"],
        "AHA": ["Glycolic Acid", "Lactic Acid"],
        "Vitamin C": ["Ascorbic Acid"],
        "Copper Peptides": ["Copper Tripeptide-1"],
        "Peptides": ["Copper Tripeptide-1", "Palmitoyl Tripeptide-1"],
    },
    "rules": [
        {"groups": ["Retinoids", "AHA"], "severity": "high", "reason": "over-exfoliation"},
        {"groups": ["Vitamin C", "AHA"], "severity": "medium", "reason": "both acidic"},
        {"groups": ["Peptides", "Copper Peptides"], "severity": "medium", "reason": "overlap"},
    ],
}

IRRITANTS = {
    "Hydroquinone": {"ingredient": "Hydroquinone", "level": "high", "reason": "regulated"},
    "Ethanol": {"ingredient": "Ethanol", "level": "low", "reason": "drying"},
}


@pytest.fixture
def audit_data(monkeypatch):
    """Inject controlled conflict + irritant tables into the caches.

    The conflict matrix now lives in src.conflicts (shared with the routine
    advisor); the irritant registry stays local to the auditor.
    """
    monkeypatch.setattr(conflicts, "_CONFLICTS_CACHE", CONFLICTS)
    monkeypatch.setattr(auditor, "_IRRITANTS_CACHE", IRRITANTS)


def _audit(*inci_names, unmatched=None):
    """Run auditor_node over a set of present INCI names; return the report."""
    state = {
        "standardized_ingredients": std_ingredients(*[(n, n) for n in inci_names]),
        "unmatched_ingredients": unmatched or [],
    }
    return auditor.auditor_node(state)["safety_report"]


# --------------------------------------------------------------------------- #
# _present_inci
# --------------------------------------------------------------------------- #
def test_present_inci_skips_unmapped():
    state = {"standardized_ingredients": std_ingredients(("レチノール", "Retinol"), ("謎", None))}
    assert auditor._present_inci(state) == {"Retinol"}


def test_present_inci_empty_state():
    assert auditor._present_inci({}) == set()


# --------------------------------------------------------------------------- #
# scoring + findings
# --------------------------------------------------------------------------- #
def test_clean_product_scores_full(audit_data):
    report = _audit("Water", "Glycerin")
    assert report.safety_score == 1.0
    assert report.ingredient_conflicts == []
    assert report.risk_ingredients == []
    assert report.warnings == []


def test_high_conflict_penalised_and_messaged(audit_data):
    report = _audit("Retinol", "Glycolic Acid")
    assert report.safety_score == round(1.0 - CONFLICT_PENALTY["high"], 2)  # 0.70
    assert report.ingredient_conflicts == [
        "Retinoids (Retinol) + AHA (Glycolic Acid): over-exfoliation"
    ]
    assert report.warnings[0].startswith("[HIGH]")
    assert report.risk_ingredients == []


def test_single_irritant_flagged(audit_data):
    report = _audit("Hydroquinone")
    assert report.safety_score == round(1.0 - IRRITANT_PENALTY["high"], 2)  # 0.85
    assert report.risk_ingredients == ["Hydroquinone"]
    assert report.warnings == ["[HIGH] Hydroquinone: regulated"]


def test_conflict_and_irritant_penalties_stack(audit_data):
    report = _audit("Retinol", "Glycolic Acid", "Ethanol")
    expected = round(1.0 - CONFLICT_PENALTY["high"] - IRRITANT_PENALTY["low"], 2)
    assert report.safety_score == expected  # 0.67
    assert report.risk_ingredients == ["Ethanol"]
    assert len(report.ingredient_conflicts) == 1


def test_overlapping_groups_single_shared_ingredient_does_not_fire(audit_data):
    # Only Copper Tripeptide-1 is present: it is the sole member on both sides of
    # the Peptides/Copper-Peptides rule, so it must not self-conflict.
    report = _audit("Copper Tripeptide-1")
    assert report.ingredient_conflicts == []
    assert report.safety_score == 1.0


def test_overlapping_groups_fire_with_a_distinct_second_member(audit_data):
    report = _audit("Copper Tripeptide-1", "Palmitoyl Tripeptide-1")
    assert report.safety_score == round(1.0 - CONFLICT_PENALTY["medium"], 2)  # 0.85
    assert len(report.ingredient_conflicts) == 1


def test_unmatched_ingredients_add_info_warning_without_penalty(audit_data):
    report = _audit("Water", unmatched=["成分X", "成分Y"])
    assert report.safety_score == 1.0
    assert any(w.startswith("[INFO]") and "2 ingredient(s)" in w for w in report.warnings)


def test_risk_ingredients_reported_in_sorted_order(audit_data):
    report = _audit("Hydroquinone", "Ethanol")
    assert report.risk_ingredients == ["Ethanol", "Hydroquinone"]


def test_japanese_findings_use_localized_reason_and_labels(monkeypatch):
    # When the data files carry reason_ja / group_labels_ja, the parallel JA lists
    # use them (localized group name + reason), keep INCI hits canonical, and tag
    # severity with 高/中/低 — while the English lists are unchanged.
    conflicts_ja = {
        "groups": {"Retinoids": ["Retinol"], "AHA": ["Glycolic Acid"]},
        "group_labels_ja": {"Retinoids": "レチノイド", "AHA": "AHA"},
        "rules": [
            {
                "groups": ["Retinoids", "AHA"],
                "severity": "high",
                "reason": "over-exfoliation",
                "reason_ja": "過剰な角質ケアのおそれ",
            }
        ],
    }
    irritants_ja = {
        "Ethanol": {"ingredient": "Ethanol", "level": "low", "reason": "drying", "reason_ja": "乾燥"}
    }
    monkeypatch.setattr(conflicts, "_CONFLICTS_CACHE", conflicts_ja)
    monkeypatch.setattr(auditor, "_IRRITANTS_CACHE", irritants_ja)
    report = _audit("Retinol", "Glycolic Acid", "Ethanol")
    assert report.ingredient_conflicts_ja == [
        "レチノイド（Retinol） + AHA（Glycolic Acid）：過剰な角質ケアのおそれ"
    ]
    assert report.warnings_ja[0] == (
        "[高] レチノイド（Retinol） + AHA（Glycolic Acid）：過剰な角質ケアのおそれ"
    )
    assert "[低] Ethanol：乾燥" in report.warnings_ja


def test_japanese_findings_fall_back_to_english_when_untranslated(audit_data):
    # The audit_data fixture has no reason_ja / group_labels_ja, so the JA lists
    # fall back to the English group names and reasons (built, never dropped),
    # still with full-width punctuation and a localized severity tag.
    report = _audit("Retinol", "Glycolic Acid", unmatched=["成分X"])
    assert report.ingredient_conflicts_ja == [
        "Retinoids（Retinol） + AHA（Glycolic Acid）：over-exfoliation"
    ]
    assert report.warnings_ja[0].startswith("[高] ")
    assert any(w.startswith("[情報]") and "1件" in w for w in report.warnings_ja)


def test_score_is_clamped_to_zero(monkeypatch):
    # Ten high-severity irritants → 1.5 of penalty, clamped to 0.0 (never negative).
    irritants = {
        f"Bad{i}": {"ingredient": f"Bad{i}", "level": "high", "reason": "x"} for i in range(10)
    }
    monkeypatch.setattr(conflicts, "_CONFLICTS_CACHE", {"groups": {}, "rules": []})
    monkeypatch.setattr(auditor, "_IRRITANTS_CACHE", irritants)
    report = _audit(*irritants.keys())
    assert report.safety_score == 0.0


# --------------------------------------------------------------------------- #
# real data files load and parse
# --------------------------------------------------------------------------- #
def test_real_conflict_and_irritant_files_load(monkeypatch):
    # Reset caches so the loaders read the real on-disk files.
    monkeypatch.setattr(conflicts, "_CONFLICTS_CACHE", None)
    monkeypatch.setattr(auditor, "_IRRITANTS_CACHE", None)
    matrix = conflicts.load_conflict_matrix()
    irritants = auditor._load_irritants()
    assert matrix["rules"] and matrix["groups"]
    # Irritants are keyed by canonical INCI name.
    assert "Hydroquinone" in irritants
    assert irritants["Hydroquinone"]["level"] == "high"
