# Evaluate the vision layer's gates against a hand-labeled manifest.
#
# The scanner-extraction eval (eval/evaluate.py) covers back-label OCR quality;
# this harness covers everything *before* extraction — the parts that decide
# whether a frame is analysable at all:
#
#   Tier 1  assess_image_quality  (deterministic, offline, free)
#   Tier 2  classify_side_node    (content + side; needs GOOGLE_API_KEY, --live)
#
# Manifest: data/vision_eval_set.json — a JSON list of labeled frames:
#   [
#     {
#       "image": "data/vision_eval/reject_dark_01.jpg",
#       "tier1": "too_dark",          // expected Tier-1 verdict, or null (pass)
#       "content": null,              // expected Tier-2 content, or null (n/a)
#       "side": null                  // expected side, or null (n/a)
#     },
#     ...
#   ]
# Frames captured by the rejection flywheel (src/rejection_store.py) are the
# natural feed for this set — copy, label, commit the manifest (images stay
# out of git like the golden set).
#
# Usage:
#   poetry run python -m eval.vision_eval                     # Tier-1 only, offline
#   poetry run python -m eval.vision_eval --sweep             # threshold calibration aid
#   poetry run python -m eval.vision_eval --live              # + Tier-2 classification
#   poetry run python -m eval.vision_eval --min-tier1-acc 0.9 # CI-style gate
import argparse
import json
import logging
import os
import sys
from collections import Counter

from dotenv import load_dotenv

from src.preprocess import assess_image_quality, frame_stats

MANIFEST_PATH = "data/vision_eval_set.json"

TIER1_REASONS = ("too_dark", "too_bright", "blank", "blurry", "unreadable")


def load_manifest(path: str) -> list[dict]:
    if not os.path.exists(path):
        sys.exit(
            f"No vision eval manifest at {path}. Create it by labeling frames "
            "(rejection-store captures are a good source) — see the header of "
            "eval/vision_eval.py for the format."
        )
    with open(path, encoding="utf-8") as f:
        entries = json.load(f)
    missing = [e["image"] for e in entries if not os.path.exists(e["image"])]
    if missing:
        logging.warning("Skipping %d entry(ies) with missing images.", len(missing))
    return [e for e in entries if os.path.exists(e["image"])]


# --- Tier 1 -------------------------------------------------------------------


def eval_tier1(entries: list[dict]) -> dict:
    """Score the deterministic pixel gate: accuracy + per-reason confusion."""
    confusion: Counter = Counter()
    correct = 0
    labeled = [e for e in entries if "tier1" in e]
    for e in labeled:
        got = assess_image_quality(e["image"])
        expected = e.get("tier1")
        confusion[(str(expected), str(got))] += 1
        if got == expected:
            correct += 1
    accuracy = correct / len(labeled) if labeled else 0.0
    return {"n": len(labeled), "accuracy": accuracy, "confusion": confusion}


def sweep_tier1(entries: list[dict]) -> None:
    """Print the raw stat distributions per label so thresholds can be chosen
    from data instead of guessed. (No auto-tuning: with small sets, eyeballing
    the separation beats overfitting an optimizer.)"""
    groups: dict[str, list[dict]] = {}
    for e in entries:
        if "tier1" not in e:
            continue
        stats = frame_stats(e["image"])
        if stats is None:
            continue
        groups.setdefault(str(e.get("tier1")), []).append(stats)

    def _mmm(stats_list: list[dict], key: str) -> str:
        vals = sorted(s[key] for s in stats_list)
        med = vals[len(vals) // 2]
        return f"{vals[0]:7.1f}/{med:7.1f}/{vals[-1]:7.1f}"

    print("\nTier-1 stat distributions by expected verdict")
    print(f"{'label':<12} {'n':>3}  {'mean-lum (min/med/max)':>26}  "
          f"{'stddev':>20}  {'focus-var':>22}")
    for label, stats_list in sorted(groups.items()):
        print(
            f"{label:<12} {len(stats_list):>3}  {_mmm(stats_list, 'mean'):>26}  "
            f"{_mmm(stats_list, 'stddev'):>20}  {_mmm(stats_list, 'focus'):>22}"
        )
    print(
        "\nPick thresholds in the gap between the None (pass) row and each "
        "reject row; current values live in src/config.py."
    )


# --- Tier 2 (live) --------------------------------------------------------------


def eval_tier2(entries: list[dict]) -> dict:
    """Score the content/side classifier on labeled frames (one VLM call each)."""
    from src.nodes.scanner import classify_side_node  # deferred: needs API key

    labeled = [e for e in entries if e.get("content") or e.get("side")]
    content_ok = side_ok = content_n = side_n = 0
    confidences: list[float] = []
    for e in labeled:
        result = classify_side_node({"image_path": e["image"], "image_type": None})
        confidences.append(result.get("classify_confidence") or 0.0)
        if e.get("content"):
            content_n += 1
            content_ok += result.get("image_content") == e["content"]
        if e.get("side"):
            side_n += 1
            side_ok += result.get("image_type") == e["side"]
    return {
        "n": len(labeled),
        "content_accuracy": content_ok / content_n if content_n else None,
        "side_accuracy": side_ok / side_n if side_n else None,
        "confidences": confidences,
    }


# --- reporting / gate -----------------------------------------------------------


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Evaluate the vision-layer gates.")
    parser.add_argument("--manifest", default=MANIFEST_PATH)
    parser.add_argument("--sweep", action="store_true", help="Print Tier-1 stat distributions.")
    parser.add_argument(
        "--live", action="store_true", help="Also run the Tier-2 classifier (needs API key)."
    )
    parser.add_argument("--min-tier1-acc", type=float, default=None)
    parser.add_argument("--min-content-acc", type=float, default=None)
    args = parser.parse_args()

    entries = load_manifest(args.manifest)
    print(f"Vision eval set: {len(entries)} frame(s)")

    t1 = eval_tier1(entries)
    print(f"\nTier-1 pixel gate: accuracy {t1['accuracy']:.2f} over {t1['n']} labeled frame(s)")
    for (expected, got), n in sorted(t1["confusion"].items()):
        marker = "  " if expected == got else "❌"
        print(f"  {marker} expected={expected:<12} got={got:<12} × {n}")

    if args.sweep:
        sweep_tier1(entries)

    if args.live:
        t2 = eval_tier2(entries)
        print(f"\nTier-2 classifier over {t2['n']} labeled frame(s):")
        if t2["content_accuracy"] is not None:
            print(f"  content accuracy : {t2['content_accuracy']:.2f}")
        if t2["side_accuracy"] is not None:
            print(f"  side accuracy    : {t2['side_accuracy']:.2f}")
        if t2["confidences"]:
            lo = min(t2["confidences"])
            print(f"  confidence range : {lo:.2f}–{max(t2['confidences']):.2f}")
        content_acc = t2["content_accuracy"] or 0
        if args.min_content_acc is not None and content_acc < args.min_content_acc:
            sys.exit(
                f"VISION GATE FAILED: content accuracy "
                f"{t2['content_accuracy']:.2f} < {args.min_content_acc:.2f}"
            )

    if args.min_tier1_acc is not None and t1["accuracy"] < args.min_tier1_acc:
        sys.exit(
            f"VISION GATE FAILED: Tier-1 accuracy {t1['accuracy']:.2f} "
            f"< {args.min_tier1_acc:.2f}"
        )
    if args.min_tier1_acc is not None:
        print(f"\nVISION GATE PASSED: Tier-1 accuracy {t1['accuracy']:.2f}")


if __name__ == "__main__":
    main()
