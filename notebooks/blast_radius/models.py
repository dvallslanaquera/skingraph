"""Model clients: Claude Opus 4.8 (Anthropic SDK) and GLM-5.2 (OpenAI-compatible).

Both are asked the identical question with the identical repo dump in context. The
only asymmetry is transport: Opus goes through the Anthropic SDK with prompt caching
on the big dump (so the 10 per-symbol calls reuse one cached prefix), GLM goes through
an OpenAI-compatible chat endpoint. Answers are parsed by the same tolerant JSON
extractor so neither model is advantaged by output formatting quirks.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field

from . import config

# --- Prompts ----------------------------------------------------------------
SYSTEM_PREAMBLE = (
    "You are a precise static-analysis assistant. You are given the COMPLETE source "
    "of a software repository. Each file appears under a header line\n"
    "    ===== FILE: <path> (<n> lines) =====\n"
    "and every source line is shown as `<line-number> | <code>`.\n\n"
    "Your job is to act like a refactoring tool's find-references pass."
)

USER_TEMPLATE = (
    "Target symbol: `{symbol}`\n\n"
    "If you rename `{symbol}` everywhere in this repository, list EVERY location that "
    "must change: its definition and every reference. Treat `{symbol}` as a whole "
    "identifier — do not include other identifiers that merely contain it as a "
    "substring.\n\n"
    "Respond with ONLY a JSON object, no prose, of the form:\n"
    '{{"references": [{{"file": "<exact path from a FILE header>", "line": '
    "<line number shown in the left margin>}}, ...]}}\n\n"
    "Use the exact file paths from the FILE headers and the exact line numbers from "
    "the left margin. Include one entry per occurrence."
)


@dataclass
class ModelResult:
    model_key: str
    symbol: str
    predictions: list[dict] = field(default_factory=list)
    raw_text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    latency_s: float = 0.0
    cost_usd: float = 0.0
    error: str | None = None


# --- Tolerant JSON parsing --------------------------------------------------
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def parse_references(text: str) -> list[dict]:
    """Extract a list of {file, line} dicts from a model's reply, defensively.

    Handles: <think> reasoning blocks, ```json fences, a top-level object with a
    ``references`` key, or a bare JSON array. Returns [] if nothing parseable.
    """
    if not text:
        return []
    cleaned = _THINK_BLOCK.sub("", text).strip()

    candidates: list[str] = []
    fence = _FENCE.search(cleaned)
    if fence:
        candidates.append(fence.group(1).strip())
    candidates.append(cleaned)
    # Last resort: the first {...} or [...] span in the text.
    obj = re.search(r"\{.*\}", cleaned, re.DOTALL)
    arr = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if obj:
        candidates.append(obj.group(0))
    if arr:
        candidates.append(arr.group(0))

    for cand in candidates:
        try:
            data = json.loads(cand)
        except (json.JSONDecodeError, ValueError):
            continue
        refs = data.get("references") if isinstance(data, dict) else data
        if isinstance(refs, list):
            return [r for r in refs if isinstance(r, dict)]
    return []


# --- Cost ------------------------------------------------------------------
def _anthropic_cost(cfg: config.ModelConfig, r: ModelResult) -> float:
    # Cache reads bill ~0.1x, cache writes ~1.25x, the rest at full input price.
    billed_input = (
        r.input_tokens
        + 1.25 * r.cache_creation_tokens
        + 0.10 * r.cache_read_tokens
    )
    return (
        billed_input / 1e6 * cfg.input_price_per_mtok
        + r.output_tokens / 1e6 * cfg.output_price_per_mtok
    )


def _simple_cost(cfg: config.ModelConfig, r: ModelResult) -> float:
    return (
        r.input_tokens / 1e6 * cfg.input_price_per_mtok
        + r.output_tokens / 1e6 * cfg.output_price_per_mtok
    )


# --- API key resolution -----------------------------------------------------
def resolve_api_key(cfg: config.ModelConfig) -> str | None:
    for env in cfg.api_key_env:
        val = os.getenv(env)
        if val:
            return val
    return None


def is_available(cfg: config.ModelConfig) -> bool:
    return resolve_api_key(cfg) is not None


# --- Clients ----------------------------------------------------------------
class OpusClient:
    """Claude Opus 4.8 via the Anthropic SDK, with the dump cached as a prefix."""

    def __init__(self, cfg: config.ModelConfig, context_text: str):
        import anthropic  # imported lazily so --demo works without the SDK

        self.cfg = cfg
        self.client = anthropic.Anthropic(api_key=resolve_api_key(cfg), timeout=600.0)
        # The big, stable prefix: preamble + the whole repo, cached for reuse across
        # all per-symbol calls (prompt caching is a prefix match).
        self.system = [
            {
                "type": "text",
                "text": f"{SYSTEM_PREAMBLE}\n\n--- REPOSITORY ---\n\n{context_text}",
                "cache_control": {"type": "ephemeral"},
            }
        ]

    def ask(self, symbol: str) -> ModelResult:
        r = ModelResult(model_key=self.cfg.key, symbol=symbol)
        t0 = time.perf_counter()
        try:
            resp = self.client.messages.create(
                model=self.cfg.model_id,
                max_tokens=config.MAX_OUTPUT_TOKENS,
                system=self.system,
                messages=[{"role": "user", "content": USER_TEMPLATE.format(symbol=symbol)}],
            )
            r.latency_s = time.perf_counter() - t0
            r.raw_text = "".join(b.text for b in resp.content if b.type == "text")
            u = resp.usage
            r.input_tokens = u.input_tokens
            r.output_tokens = u.output_tokens
            r.cache_read_tokens = getattr(u, "cache_read_input_tokens", 0) or 0
            r.cache_creation_tokens = getattr(u, "cache_creation_input_tokens", 0) or 0
            r.predictions = parse_references(r.raw_text)
            r.cost_usd = _anthropic_cost(self.cfg, r)
        except Exception as exc:  # noqa: BLE001 — surface any API failure per-symbol
            r.latency_s = time.perf_counter() - t0
            r.error = f"{type(exc).__name__}: {exc}"
        return r


class GLMClient:
    """GLM-5.2 via an OpenAI-compatible endpoint (z.ai / Zhipu)."""

    def __init__(self, cfg: config.ModelConfig, context_text: str):
        from openai import OpenAI  # lazy import

        self.cfg = cfg
        self.client = OpenAI(
            api_key=resolve_api_key(cfg), base_url=cfg.base_url, timeout=600.0
        )
        self.system_text = f"{SYSTEM_PREAMBLE}\n\n--- REPOSITORY ---\n\n{context_text}"

    def ask(self, symbol: str) -> ModelResult:
        r = ModelResult(model_key=self.cfg.key, symbol=symbol)
        t0 = time.perf_counter()
        try:
            resp = self.client.chat.completions.create(
                model=self.cfg.model_id,
                max_tokens=config.MAX_OUTPUT_TOKENS,
                temperature=0,
                messages=[
                    {"role": "system", "content": self.system_text},
                    {"role": "user", "content": USER_TEMPLATE.format(symbol=symbol)},
                ],
            )
            r.latency_s = time.perf_counter() - t0
            r.raw_text = resp.choices[0].message.content or ""
            if resp.usage:
                r.input_tokens = resp.usage.prompt_tokens
                r.output_tokens = resp.usage.completion_tokens
            r.predictions = parse_references(r.raw_text)
            r.cost_usd = _simple_cost(self.cfg, r)
        except Exception as exc:  # noqa: BLE001
            r.latency_s = time.perf_counter() - t0
            r.error = f"{type(exc).__name__}: {exc}"
        return r


def make_client(cfg: config.ModelConfig, context_text: str):
    if cfg.provider == "anthropic":
        return OpusClient(cfg, context_text)
    if cfg.provider == "openai_compatible":
        return GLMClient(cfg, context_text)
    raise ValueError(f"unknown provider: {cfg.provider}")
