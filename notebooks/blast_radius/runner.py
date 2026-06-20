"""Orchestrate the benchmark and write a results JSON the notebook can render.

Flow: build the line-numbered repo dump once → build the deterministic oracle →
for each available model, ask the blast-radius question for every target symbol →
score file- and line-level P/R/F1 → aggregate (macro + micro) → dump to JSON.

Run ``python run_benchmark.py --help`` from the notebooks/ directory for options.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import config, models
from .oracle import SymbolOracle, build_oracle
from .repo_context import build_context
from .scoring import Score, micro_average, normalize_path, score_symbol


def _predicted_sets(predictions: list[dict]) -> tuple[set, set]:
    """(files, (file,line) keys) from raw predictions, path-normalized."""
    files: set[str] = set()
    lines: set[tuple[str, int]] = set()
    for ref in predictions:
        f = normalize_path(str(ref.get("file", "")))
        if not f:
            continue
        files.add(f)
        ln = ref.get("line")
        if isinstance(ln, int) or (isinstance(ln, str) and str(ln).isdigit()):
            lines.add((f, int(ln)))
    return files, lines


# --- Synthetic predictions for --demo --------------------------------------
def _synthetic_predictions(
    oracle: SymbolOracle, profile: dict, rng: random.Random
) -> list[dict]:
    """Fabricate a plausible, clearly-synthetic answer derived from the oracle.

    Used only by --demo so the full pipeline + notebook can be exercised without API
    keys. These numbers are NOT real model outputs — results are tagged synthetic.
    """
    preds: list[dict] = []
    for ref in oracle.references:
        if rng.random() < profile["line_recall"]:
            line = ref.line
            # Occasionally drift the line number to model imperfect line counting.
            if rng.random() < profile["line_jitter"]:
                line += rng.choice((-1, 1))
            preds.append({"file": ref.file, "line": line})
    # A few hallucinated references into real files.
    files = sorted(oracle.files) or ["src/state.py"]
    for _ in range(profile["hallucinations"]):
        preds.append({"file": rng.choice(files), "line": rng.randint(1, 300)})
    return preds


_DEMO_PROFILES = {
    "opus-4-8": {"line_recall": 0.97, "line_jitter": 0.02, "hallucinations": 0},
    "glm-5-2": {"line_recall": 0.86, "line_jitter": 0.10, "hallucinations": 2},
}


def _score_to_dict(s: Score) -> dict:
    return {
        "precision": round(s.precision, 4),
        "recall": round(s.recall, 4),
        "f1": round(s.f1, 4),
        "tp": s.tp,
        "fp": s.fp,
        "fn": s.fn,
        "n_pred": s.n_pred,
        "n_truth": s.n_truth,
    }


def run_model(
    cfg: config.ModelConfig,
    oracle,
    symbols: tuple[str, ...],
    context_text: str,
    *,
    demo: bool,
    rng: random.Random | None = None,
) -> dict:
    per_symbol: list[dict] = []
    file_pairs: list[tuple[set, set]] = []
    line_pairs: list[tuple[set, set]] = []

    client = None
    if not demo:
        client = models.make_client(cfg, context_text)

    for sym in symbols:
        so = oracle[sym]
        if demo:
            preds = _synthetic_predictions(so, _DEMO_PROFILES[cfg.key], rng)
            result = models.ModelResult(model_key=cfg.key, symbol=sym, predictions=preds)
        else:
            print(f"    [{cfg.key}] querying '{sym}' ...", flush=True)
            result = client.ask(sym)
            if result.error:
                print(f"      ! error: {result.error}", flush=True)

        scores = score_symbol(result.predictions, so)
        pf, pl = _predicted_sets(result.predictions)
        file_pairs.append((pf, so.files))
        line_pairs.append((pl, so.line_keys))

        per_symbol.append(
            {
                "symbol": sym,
                "oracle_files": len(so.files),
                "oracle_lines": len(so.references),
                "file": _score_to_dict(scores["file"]),
                "line": _score_to_dict(scores["line"]),
                "n_pred": len(result.predictions),
                "latency_s": round(result.latency_s, 3),
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cache_read_tokens": result.cache_read_tokens,
                "cost_usd": round(result.cost_usd, 6),
                "error": result.error,
            }
        )

    n = len(symbols) or 1
    aggregate = {
        "file": {
            "macro": _score_to_dict(
                _macro([s["file"] for s in per_symbol])
            ),
            "micro": _score_to_dict(micro_average(file_pairs)),
        },
        "line": {
            "macro": _score_to_dict(_macro([s["line"] for s in per_symbol])),
            "micro": _score_to_dict(micro_average(line_pairs)),
        },
        "latency_s_mean": round(sum(s["latency_s"] for s in per_symbol) / n, 3),
        "total_cost_usd": round(sum(s["cost_usd"] for s in per_symbol), 6),
        "total_input_tokens": sum(s["input_tokens"] for s in per_symbol),
        "total_output_tokens": sum(s["output_tokens"] for s in per_symbol),
        "n_errors": sum(1 for s in per_symbol if s["error"]),
    }

    return {
        "label": cfg.label,
        "model_id": cfg.model_id,
        "per_symbol": per_symbol,
        "aggregate": aggregate,
    }


def _macro(score_dicts: list[dict]) -> Score:
    """Macro-average a list of already-serialized score dicts back into a Score."""
    n = len(score_dicts) or 1
    return Score(
        precision=sum(d["precision"] for d in score_dicts) / n,
        recall=sum(d["recall"] for d in score_dicts) / n,
        f1=sum(d["f1"] for d in score_dicts) / n,
        tp=sum(d["tp"] for d in score_dicts),
        fp=sum(d["fp"] for d in score_dicts),
        fn=sum(d["fn"] for d in score_dicts),
        n_pred=sum(d["n_pred"] for d in score_dicts),
        n_truth=sum(d["n_truth"] for d in score_dicts),
    )


def run(
    model_keys: list[str],
    symbols: tuple[str, ...],
    *,
    demo: bool,
    out_path: Path,
    seed: int = 7,
) -> dict:
    print("Building repository context ...", flush=True)
    ctx = build_context()
    print(
        f"  {len(ctx.files)} files, {ctx.char_count:,} chars "
        f"(~{ctx.est_tokens:,} tokens)",
        flush=True,
    )

    print("Building deterministic oracle ...", flush=True)
    oracle = build_oracle(symbols)
    for sym in symbols:
        so = oracle[sym]
        print(f"  {sym:<32} {len(so.files):>3} files  {len(so.references):>3} lines")

    rng = random.Random(seed)
    results_models: dict[str, dict] = {}
    for key in model_keys:
        cfg = config.MODELS[key]
        if not demo and not models.is_available(cfg):
            envs = " or ".join(cfg.api_key_env)
            print(f"  - skipping {cfg.label}: no API key ({envs})", flush=True)
            results_models[key] = {
                "label": cfg.label,
                "model_id": cfg.model_id,
                "skipped": "no_api_key",
            }
            continue
        print(f"Running {cfg.label} ({'demo' if demo else 'live'}) ...", flush=True)
        results_models[key] = run_model(
            cfg, oracle, symbols, ctx.text, demo=demo, rng=rng
        )

    payload = {
        "schema_version": 1,
        "mode": "demo" if demo else "live",
        "synthetic": demo,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo": {
            "n_files": len(ctx.files),
            "char_count": ctx.char_count,
            "est_tokens": ctx.est_tokens,
        },
        "symbols": list(symbols),
        "oracle": {
            sym: {
                "files": len(oracle[sym].files),
                "lines": len(oracle[sym].references),
            }
            for sym in symbols
        },
        "models": results_models,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWrote results -> {out_path}", flush=True)
    return payload


def _print_summary(payload: dict) -> None:
    print("\n" + "=" * 64)
    print(f"SUMMARY ({payload['mode']}{' / SYNTHETIC' if payload['synthetic'] else ''})")
    print("=" * 64)
    hdr = f"{'model':<18}{'file F1':>10}{'line F1':>10}{'lat(s)':>9}{'cost$':>10}"
    print(hdr)
    print("-" * 64)
    for key, m in payload["models"].items():
        if "aggregate" not in m:
            print(f"{m['label']:<18}{'(skipped: ' + m.get('skipped', '?') + ')':>41}")
            continue
        agg = m["aggregate"]
        print(
            f"{m['label']:<18}"
            f"{agg['file']['macro']['f1']:>10.3f}"
            f"{agg['line']['macro']['f1']:>10.3f}"
            f"{agg['latency_s_mean']:>9.2f}"
            f"{agg['total_cost_usd']:>10.4f}"
        )
    print("(file/line F1 are macro-averaged across symbols)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Blast Radius benchmark: GLM-5.2 vs Claude Opus 4.8 long-context "
        "code comprehension."
    )
    parser.add_argument(
        "--models",
        default=",".join(config.MODELS),
        help="comma-separated model keys to run (default: all). "
        f"choices: {', '.join(config.MODELS)}",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="offline mode: synthesize clearly-labeled fake answers so the pipeline "
        "and notebook run without API keys. Results are tagged synthetic.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="only probe the first N target symbols (quick smoke test).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output JSON path (default: results/<mode>_<timestamp>.json + "
        "results/latest.json).",
    )
    args = parser.parse_args(argv)

    model_keys = [k.strip() for k in args.models.split(",") if k.strip()]
    bad = [k for k in model_keys if k not in config.MODELS]
    if bad:
        parser.error(f"unknown model key(s): {bad}. choices: {list(config.MODELS)}")

    symbols = config.TARGET_SYMBOLS
    if args.limit:
        symbols = symbols[: args.limit]

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    mode = "demo" if args.demo else "live"
    out_path = args.out or (config.RESULTS_DIR / f"{mode}_{stamp}.json")

    payload = run(model_keys, symbols, demo=args.demo, out_path=out_path)

    # Also refresh results/latest.json so the notebook always finds the newest run.
    latest = config.RESULTS_DIR / "latest.json"
    latest.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    _print_summary(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
