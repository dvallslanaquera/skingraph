# Tiny dependency-free stats helpers shared by the latency/cost benchmark
# (evaluate.py --bench) and the router threshold sweep (sweep.py). Kept out of
# evaluate.py so both can import them without a circular dependency.


def percentile(values: list[float], p: float) -> float:
    """The p-th percentile (0-100) via linear interpolation, numpy's default.

    Returns 0.0 for an empty input. p is clamped to [0, 100]. With a single
    value, every percentile is that value.
    """
    if not values:
        return 0.0
    p = max(0.0, min(100.0, p))
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    # Rank position on a 0..n-1 index scale, then interpolate between neighbours.
    rank = (p / 100.0) * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    return float(ordered[low] + (ordered[high] - ordered[low]) * frac)


def summarize(values: list[float]) -> dict:
    """p50/p95/p99 + mean/min/max over a list, all 0.0 when empty."""
    if not values:
        return {"n": 0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "mean": 0.0, "min": 0.0, "max": 0.0}
    return {
        "n": len(values),
        "p50": round(percentile(values, 50), 4),
        "p95": round(percentile(values, 95), 4),
        "p99": round(percentile(values, 99), 4),
        "mean": round(sum(values) / len(values), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }
