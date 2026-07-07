# Tests for the latency/cost benchmark aggregation in eval/evaluate.py: the
# per-tier summary and the graceful "no timing yet" path. The live capture
# (run_scanner_timed) is not exercised here — it needs a real Gemini call.
from eval import evaluate


def _perf(latency, cost):
    return {"latency_seconds": latency, "cost_usd": cost, "usage": {}}


def test_bench_summary_none_when_no_timing():
    assert evaluate._bench_summary([None, {}]) is None


def test_bench_summary_reports_percentiles():
    perfs = [_perf(3.0, 0.004), _perf(6.0, 0.005), _perf(15.0, 0.006)]
    summary = evaluate._bench_summary(perfs)
    assert summary["scans"] == 3
    assert summary["latency_seconds"]["p50"] == 6.0
    assert summary["latency_seconds"]["max"] == 15.0
    assert summary["cost_usd"]["mean"] == 0.005


def test_bench_summary_partial_timing():
    # One scan carries timing, one does not — the summary counts only the timed one.
    summary = evaluate._bench_summary([_perf(4.0, 0.004), None])
    assert summary["scans"] == 1
    assert summary["latency_seconds"]["p50"] == 4.0


def test_print_bench_empty(capsys):
    evaluate.print_bench({})
    assert "No timing recorded" in capsys.readouterr().out
