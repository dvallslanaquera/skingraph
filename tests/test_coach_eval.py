# Tests for the coach faithfulness eval (eval/coach_eval.py). The eval itself
# runs the coach with a stubbed Gemini call, so these tests confirm (a) the
# real fixtures all pass at full coverage, and (b) the gate actually CATCHES a
# regression — i.e. it is not tautological: if the coach stops injecting a
# mandated safety caution, coverage drops below 1.0 and the gate exits non-zero.
import pytest

from eval import coach_eval
from src.nodes import coach


def test_all_fixtures_fully_covered():
    results = [coach_eval.run_fixture(f) for f in coach_eval.FIXTURES]
    agg = coach_eval._aggregate(results)
    assert agg["coverage"] == 1.0
    assert agg["failing"] == []


def test_gate_passes_at_full_coverage():
    results = [coach_eval.run_fixture(f) for f in coach_eval.FIXTURES]
    coach_eval.apply_gate(results, 1.0)  # must not raise


def test_gate_catches_dropped_pregnancy_caution(monkeypatch):
    # Simulate a regression: the coach stops emitting pregnancy cautions.
    monkeypatch.setattr(coach, "_pregnancy_cautions", lambda state, profile: ([], []))
    results = [coach_eval.run_fixture(f) for f in coach_eval.FIXTURES]
    agg = coach_eval._aggregate(results)
    assert agg["coverage"] < 1.0
    assert "pregnant_clean" in agg["failing"]
    with pytest.raises(SystemExit, match="COACH FAITHFULNESS GATE FAILED"):
        coach_eval.apply_gate(results, 1.0)


def test_clean_anonymous_fixture_requires_nothing():
    result = coach_eval.run_fixture(
        next(f for f in coach_eval.FIXTURES if f["id"] == "clean_no_profile")
    )
    assert result["required"] == 0
    assert result["missing"] == []
