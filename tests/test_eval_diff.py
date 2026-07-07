# Tests for the eval-diff renderer (eval/diff.py): aggregate delta, per-image
# regression ordering, and the added/removed cassette notes.
from eval import diff


def _res(id_, f1, recall=None, cost=None):
    r = {
        "id": id_,
        "brand_score": 100.0,
        "product_score": 100.0,
        "quasi_drug_correct": True,
        "ingredients": {"f1": f1, "recall": recall if recall is not None else f1},
    }
    if cost is not None:
        r["perf"] = {"cost_usd": cost}
    return r


def test_diff_flags_regression():
    base = [_res("a", 0.95), _res("b", 0.90)]
    head = [_res("a", 0.95), _res("b", 0.70)]
    d = diff.compute_diff(base, head)
    assert d["per_image"][0]["id"] == "b"  # regressions first
    assert d["per_image"][0]["delta"] < 0
    md = diff.render_markdown(d)
    assert "regression" in md
    assert "`b`" in md


def test_diff_improvement_verdict():
    base = [_res("a", 0.80)]
    head = [_res("a", 0.92)]
    md = diff.render_markdown(diff.compute_diff(base, head))
    assert "improvement" in md


def test_diff_reports_cost_when_present():
    base = [_res("a", 0.9, cost=0.004)]
    head = [_res("a", 0.9, cost=0.006)]
    md = diff.render_markdown(diff.compute_diff(base, head))
    assert "$/scan" in md


def test_diff_omits_cost_without_perf():
    md = diff.render_markdown(diff.compute_diff([_res("a", 0.9)], [_res("a", 0.9)]))
    assert "$/scan" not in md


def test_diff_notes_added_and_removed():
    base = [_res("a", 0.9), _res("gone", 0.9)]
    head = [_res("a", 0.9), _res("new", 0.9)]
    d = diff.compute_diff(base, head)
    assert d["added"] == ["new"]
    assert d["removed"] == ["gone"]


def test_diff_handles_empty_side():
    md = diff.render_markdown(diff.compute_diff([], [_res("a", 0.9)]))
    assert "cannot diff" in md
