# Tests for the drift canary (eval/canary.py): the divergence verdict rules and
# the summary rendering. The live read is not exercised (it needs Gemini); the
# dry-run path replays the cassette as the "live" read, so it is always green.
from eval import canary


def test_render_summary_green():
    results = [
        {
            "id": "a",
            "base_f1": 0.9,
            "live_f1": 0.9,
            "delta": 0.0,
            "latency": 2.0,
            "reasons": [],
            "diverged": False,
        }
    ]
    md = canary.render_summary(results)
    assert "Canary green" in md
    assert "`a`" in md


def test_render_summary_flags_drift():
    results = [
        {
            "id": "a",
            "base_f1": 0.90,
            "live_f1": 0.60,
            "delta": -0.30,
            "latency": 3.0,
            "reasons": ["F1 0.90 → 0.60 (-0.30, tol 0.05)"],
            "diverged": True,
        }
    ]
    md = canary.render_summary(results)
    assert "drift detected" in md
    assert "-0.30" in md


def test_check_image_dry_run_is_green(monkeypatch):
    # _load_cassette + score_extraction run against the committed prod_001 flash
    # cassette; dry-run uses it as both baseline and "live", so delta is 0.
    import json

    with open(canary.GROUND_TRUTH_PATH, encoding="utf-8") as f:
        by_id = {e["id"]: e for e in json.load(f)}
    result = canary.check_image(by_id["prod_001"], dry_run=True, tolerance=0.05, max_latency=30.0)
    assert result["diverged"] is False
    assert result["delta"] == 0.0
