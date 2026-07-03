# Custom Prometheus metrics for the scan pipeline.
#
# prometheus_client's default REGISTRY is the same one the Instrumentator in
# src/api/main.py already exposes at /metrics, so everything defined here shows
# up on that endpoint with zero extra wiring. Token usage is captured by
# attaching ScanUsageCallback to the graph run's config (src/observability.py's
# scan_run_config), which langchain propagates to every Gemini call in the run
# — no node-code changes.
from typing import Any

from langchain_core.callbacks import UsageMetadataCallbackHandler
from prometheus_client import Counter, Histogram

from src.config import MODEL_PRICES_USD_PER_MTOK

SCANS_TOTAL = Counter(
    "scans_total",
    "Scan requests by final status and entrypoint.",
    ["status", "entrypoint"],
)

# VLM nodes take seconds to tens of seconds; deterministic nodes milliseconds.
SCAN_NODE_DURATION = Histogram(
    "scan_node_duration_seconds",
    "Wall-clock time spent in each graph node.",
    ["node"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 40.0),
)

SCAN_ESCALATIONS = Counter(
    "scan_escalations_total",
    "Scans escalated from the flash scanner to the pro scanner.",
)

SCAN_CORRECTIONS = Counter(
    "scan_corrections_total",
    "Correction-loop retries across all scans.",
)

SCAN_TOKENS = Counter(
    "scan_tokens_total",
    "LLM tokens consumed by scans.",
    ["model", "direction"],
)

SCAN_COST = Counter(
    "scan_cost_usd_total",
    "Estimated LLM spend across scans, USD (list prices).",
    ["model"],
)


class ScanUsageCallback(UsageMetadataCallbackHandler):
    """Per-run usage aggregator: token counts per model plus a call counter."""

    def __init__(self) -> None:
        super().__init__()
        self.model_calls = 0

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        self.model_calls += 1
        super().on_llm_end(response, **kwargs)


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """List-price estimate for one model's token usage; 0 for unknown models."""
    prices = MODEL_PRICES_USD_PER_MTOK.get(model)
    if not prices:
        return 0.0
    return (input_tokens * prices["input"] + output_tokens * prices["output"]) / 1_000_000


def observe_node(node: str, seconds: float) -> None:
    SCAN_NODE_DURATION.labels(node=node).observe(seconds)


def observe_scan(*, status: str, entrypoint: str, final_state: dict, usage: dict) -> None:
    """Record one finished scan: outcome, escalation/correction counts, tokens, cost.

    ``usage`` is a UsageMetadataCallbackHandler.usage_metadata dict
    ({model_name: {input_tokens, output_tokens, ...}}).
    """
    SCANS_TOTAL.labels(status=status, entrypoint=entrypoint).inc()

    if final_state.get("model_used") == "pro":
        SCAN_ESCALATIONS.inc()
    corrections = final_state.get("correction_attempts") or 0
    if corrections:
        SCAN_CORRECTIONS.inc(corrections)

    for model, counts in (usage or {}).items():
        input_tokens = counts.get("input_tokens", 0)
        output_tokens = counts.get("output_tokens", 0)
        SCAN_TOKENS.labels(model=model, direction="input").inc(input_tokens)
        SCAN_TOKENS.labels(model=model, direction="output").inc(output_tokens)
        cost = estimate_cost_usd(model, input_tokens, output_tokens)
        if cost:
            SCAN_COST.labels(model=model).inc(cost)
