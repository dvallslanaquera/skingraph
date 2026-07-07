# Router threshold sweep — the Flash→Pro cost/accuracy Pareto frontier.
#
#   # First record BOTH tiers over the golden set (live, needs GOOGLE_API_KEY):
#   poetry run python -m eval.evaluate --model both --record
#   # Then sweep the escalation threshold entirely offline:
#   poetry run python -m eval.sweep
#   poetry run python -m eval.sweep --min-f1 0.90 --save data/sweep.json
#
# SkinGraph is a *cascade*: the cheap Flash scanner runs first and escalates to
# the expensive Pro scanner when its self-reported confidence falls below
# FLASH_ACCEPT_THRESHOLD (src/config.py). That threshold is a knob trading cost
# for accuracy, and a knob should be set from data, not by feel.
#
# This sweep replays the recorded Flash and Pro extractions over the golden set
# and, for each candidate threshold τ, decides per image which tier the cascade
# would have used (Flash if flash_confidence ≥ τ, else escalate to Pro), then
# computes the resulting aggregate F1 and $/scan. Plotting F1 against $/scan
# traces the Pareto frontier so you can pick the cheapest τ that clears a quality
# bar — "we ship τ = X because it buys F1 = Y at $Z/scan." Pure post-processing:
# no API calls per threshold. Report/decision only, never a CI gate.
import argparse
import json
import os
import sys

from eval.evaluate import (
    GROUND_TRUTH_PATH,
    INGREDIENT_MATCH_THRESHOLD,
    MANIFEST_PATH,
    RERECORD_HINT,
    _cassette_path,
    score_extraction,
)
from src.config import FLASH_ACCEPT_THRESHOLD
from src.state import ProductExtraction

# Illustrative per-scan list-price costs used only when a cassette carries no
# recorded token usage (record with --record after the benchmark landed to get
# real ones). A cascade that escalates pays BOTH tiers on that image.
DEFAULT_FLASH_COST = 0.004
DEFAULT_PRO_COST = 0.030


def _load_side(model: str, entry: dict) -> dict | None:
    """Load one tier's recorded extraction + confidence + cost for an image."""
    path = _cassette_path(model, entry)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    ext = ProductExtraction.model_validate(data["extraction"])
    perf = data.get("perf") or {}
    return {
        "extraction": ext,
        "confidence": ext.extraction_confidence,
        "cost_usd": perf.get("cost_usd"),
    }


def load_pairs(by_id: dict[str, dict]) -> list[dict]:
    """Pair each image's Flash and Pro cassettes; both tiers are required."""
    if not os.path.exists(MANIFEST_PATH):
        sys.exit(f"No cassette manifest at {MANIFEST_PATH} — {RERECORD_HINT}")
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest = json.load(f)
    models = manifest.get("models", {})
    if "flash" not in models or "pro" not in models:
        sys.exit(
            "The sweep needs BOTH flash and pro cassettes. Record them with:\n"
            "  poetry run python -m eval.evaluate --model both --record"
        )
    ids = [i for i in models["flash"]["ids"] if i in set(models["pro"]["ids"])]
    if not ids:
        sys.exit("No image has BOTH a flash and a pro cassette — re-record --model both.")

    pairs: list[dict] = []
    for id_ in ids:
        entry = by_id.get(id_)
        if entry is None:
            continue
        flash = _load_side("flash", entry)
        pro = _load_side("pro", entry)
        if flash and pro:
            pairs.append({"id": id_, "entry": entry, "flash": flash, "pro": pro})
    return pairs


def _f1(entry: dict, extraction: ProductExtraction, threshold: int) -> float:
    return score_extraction("sweep", entry, extraction, threshold)["ingredients"]["f1"]


def score_at_threshold(
    pairs: list[dict], tau: float, threshold: int, flash_cost: float, pro_cost: float
) -> dict:
    """Aggregate F1 + $/scan + escalation rate for one escalation threshold τ.

    An image uses Flash when its Flash confidence ≥ τ, else the cascade escalates
    and pays for BOTH the Flash attempt and the Pro re-scan.
    """
    f1s: list[float] = []
    costs: list[float] = []
    escalations = 0
    for pair in pairs:
        flash, pro, entry = pair["flash"], pair["pro"], pair["entry"]
        fc = flash["cost_usd"] if flash["cost_usd"] is not None else flash_cost
        pc = pro["cost_usd"] if pro["cost_usd"] is not None else pro_cost
        if flash["confidence"] >= tau:
            f1s.append(_f1(entry, flash["extraction"], threshold))
            costs.append(fc)
        else:
            escalations += 1
            f1s.append(_f1(entry, pro["extraction"], threshold))
            costs.append(fc + pc)  # cascade paid Flash then Pro
    n = len(pairs)
    return {
        "tau": round(tau, 3),
        "f1": round(sum(f1s) / n, 4) if n else 0.0,
        "cost_per_scan": round(sum(costs) / n, 5) if n else 0.0,
        "escalation_rate": round(escalations / n, 3) if n else 0.0,
    }


def sweep(
    pairs: list[dict], taus: list[float], threshold: int, flash_cost: float, pro_cost: float
) -> list[dict]:
    return [score_at_threshold(pairs, t, threshold, flash_cost, pro_cost) for t in taus]


def pareto_front(points: list[dict]) -> list[dict]:
    """Non-dominated (cost, F1) points: no cheaper point scores at least as high.

    A point is dominated when another costs no more AND scores at least as high
    (and is strictly better on one axis). The survivors are the only settings
    worth shipping.
    """
    front: list[dict] = []
    for p in points:
        dominated = any(
            q is not p
            and q["cost_per_scan"] <= p["cost_per_scan"]
            and q["f1"] >= p["f1"]
            and (q["cost_per_scan"] < p["cost_per_scan"] or q["f1"] > p["f1"])
            for q in points
        )
        if not dominated:
            front.append(p)
    # De-dup identical (cost, f1) survivors, keep the lowest τ.
    seen: set[tuple[float, float]] = set()
    unique: list[dict] = []
    for p in sorted(front, key=lambda x: (x["cost_per_scan"], -x["f1"], x["tau"])):
        key = (p["cost_per_scan"], p["f1"])
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def cheapest_meeting_bar(points: list[dict], min_f1: float) -> dict | None:
    """The lowest-cost threshold whose F1 clears the bar — the recommendation."""
    qualifying = [p for p in points if p["f1"] >= min_f1]
    return min(qualifying, key=lambda p: p["cost_per_scan"]) if qualifying else None


def print_report(points: list[dict], min_f1: float | None, recorded_cost: bool) -> None:
    print("\n" + "=" * 70)
    print("  ROUTER THRESHOLD SWEEP — Flash→Pro cost/accuracy frontier")
    print("=" * 70)
    print(f"\n  {'τ':>5}  {'F1':>7}  {'$/scan':>9}  {'escalation':>11}")
    print("  " + "-" * 40)
    for p in points:
        marker = "  <- ships now" if abs(p["tau"] - FLASH_ACCEPT_THRESHOLD) < 1e-9 else ""
        print(
            f"  {p['tau']:>5.2f}  {p['f1']:>7.3f}  {p['cost_per_scan']:>9.5f}  "
            f"{p['escalation_rate'] * 100:>9.0f}%{marker}"
        )
    front = pareto_front(points)
    print("\n  Pareto frontier (non-dominated τ):")
    print(
        "    "
        + ", ".join(f"τ={p['tau']:.2f}→F1={p['f1']:.3f}@${p['cost_per_scan']:.4f}" for p in front)
    )
    if min_f1 is not None:
        pick = cheapest_meeting_bar(points, min_f1)
        if pick:
            print(
                f"\n  Cheapest τ with F1 ≥ {min_f1:.2f}: τ={pick['tau']:.2f} "
                f"→ F1={pick['f1']:.3f} at ${pick['cost_per_scan']:.4f}/scan "
                f"({pick['escalation_rate'] * 100:.0f}% escalate)."
            )
        else:
            print(f"\n  No threshold reaches F1 ≥ {min_f1:.2f} on this set.")
    if not recorded_cost:
        print("\n  NOTE: costs are illustrative list-price defaults — no token usage was")
        print("        recorded in the cassettes. Re-record after the benchmark for real $.")
    print("=" * 70 + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sweep the Flash→Pro escalation threshold over recorded cassettes."
    )
    parser.add_argument("--start", type=float, default=0.0, help="Lowest τ (default 0.0).")
    parser.add_argument("--stop", type=float, default=1.0, help="Highest τ (default 1.0).")
    parser.add_argument("--step", type=float, default=0.05, help="τ step (default 0.05).")
    parser.add_argument(
        "--min-f1",
        type=float,
        default=None,
        help="Report the cheapest τ whose F1 clears this bar (a decision aid, not a gate).",
    )
    parser.add_argument("--flash-cost", type=float, default=DEFAULT_FLASH_COST)
    parser.add_argument("--pro-cost", type=float, default=DEFAULT_PRO_COST)
    parser.add_argument("--save", metavar="PATH", help="Write the sweep points as JSON to PATH.")
    return parser.parse_args()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()

    with open(GROUND_TRUTH_PATH, encoding="utf-8") as f:
        by_id = {e["id"]: e for e in json.load(f)}

    pairs = load_pairs(by_id)
    recorded_cost = any(p["flash"]["cost_usd"] is not None for p in pairs)

    taus: list[float] = []
    t = args.start
    while t <= args.stop + 1e-9:
        taus.append(round(t, 4))
        t += args.step

    points = sweep(pairs, taus, INGREDIENT_MATCH_THRESHOLD, args.flash_cost, args.pro_cost)
    print_report(points, args.min_f1, recorded_cost)

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(
                {"points": points, "pareto": pareto_front(points)},
                f,
                ensure_ascii=False,
                indent=2,
            )
        print(f"Sweep written to {args.save}")


if __name__ == "__main__":
    main()
