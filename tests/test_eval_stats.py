# Tests for the shared percentile/summary helpers (eval/_stats.py).
from eval._stats import percentile, summarize


def test_percentile_empty_is_zero():
    assert percentile([], 50) == 0.0


def test_percentile_single_value():
    assert percentile([7.0], 95) == 7.0


def test_percentile_median_interpolates():
    # numpy 'linear': p50 of 1..4 is 2.5.
    assert percentile([1, 2, 3, 4], 50) == 2.5


def test_percentile_endpoints():
    vals = [10, 20, 30, 40, 50]
    assert percentile(vals, 0) == 10
    assert percentile(vals, 100) == 50


def test_percentile_clamps_out_of_range():
    assert percentile([1, 2, 3], 150) == 3
    assert percentile([1, 2, 3], -10) == 1


def test_summarize_empty():
    s = summarize([])
    assert s["n"] == 0 and s["p95"] == 0.0


def test_summarize_orders_and_reports():
    s = summarize([5, 1, 3, 2, 4])
    assert s["n"] == 5
    assert s["min"] == 1 and s["max"] == 5
    assert s["p50"] == 3.0
    assert s["mean"] == 3.0
