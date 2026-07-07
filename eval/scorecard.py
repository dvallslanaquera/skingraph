# Eval scorecard — turn the replay gate's pass/fail line into a durable,
# comparable artifact: a per-commit Markdown table, a trend history, and badges.
#
#   # CI: render the scorecard onto the GitHub Actions run summary + append trend
#   poetry run python -m eval.scorecard --history eval/history.jsonl \
#       --commit "$GITHUB_SHA"
#   # Also emit shields.io endpoint JSON for README badges:
#   poetry run python -m eval.scorecard --badges docs/badges
#
# A single pass/fail line in a CI log scrolls away and hides *slow* regressions —
# a chain of PRs each dropping F1 half a point, individually passing the floor.
# A scorecard makes the number visible and trendable (EVAL-OPS.md §5). It reuses
# the offline replay path, so it needs no API key and no images.
import argparse
import json
import os
import sys
from datetime import datetime, timezone

from eval.evaluate import GROUND_TRUTH_PATH, _aggregate, run_replay


def _color(value: float, good: float, ok: float) -> str:
    """shields.io colour by band: brightgreen / green / yellow / red."""
    if value >= good:
        return "brightgreen"
    if value >= ok:
        return "green"
    if value >= ok - 0.1:
        return "yellow"
    return "red"


def render_markdown(results: list[dict], model: str, min_f1: float | None) -> str:
    agg = _aggregate(results)
    gate = ""
    if min_f1 is not None:
        passed = agg["ingredient_f1"] >= min_f1
        gate = f" · gate **{'PASS' if passed else 'FAIL'}** (floor {min_f1:.2f})"

    lines = [
        f"### 🌿 Eval scorecard — `{model}` tier",
        "",
        f"**Aggregate F1 {agg['ingredient_f1']:.3f}** · recall {agg['ingredient_recall']:.3f} "
        f"· brand {agg['brand_score']:.0f}/100 · product {agg['product_score']:.0f}/100 "
        f"· quasi-drug {agg['quasi_drug_correct']}/{agg['images']}{gate}",
        "",
        "| Image | Conf | P | R | F1 | Missed | Extra |",
        "|-------|-----:|---:|---:|---:|-------:|------:|",
    ]
    for r in sorted(results, key=lambda x: x["id"]):
        ing = r["ingredients"]
        lines.append(
            f"| `{r['id']}` | {r['confidence']:.2f} | {ing['precision']:.2f} | "
            f"{ing['recall']:.2f} | **{ing['f1']:.2f}** | {len(ing['missed'])} | "
            f"{len(ing['hallucinated'])} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_summary(markdown: str) -> None:
    """Append to the GitHub Actions run summary when in CI; else print."""
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(markdown + "\n")
        print(f"Scorecard written to $GITHUB_STEP_SUMMARY ({summary_path})")
    else:
        print(markdown)


def append_history(results: list[dict], model: str, path: str, commit: str | None) -> None:
    """Append the aggregate as one JSONL line so F1 can be trended across commits."""
    agg = _aggregate(results)
    row = {
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": (commit or os.getenv("GITHUB_SHA") or "local")[:12],
        "model": model,
        **agg,
    }
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Appended history row to {path}")


def write_badges(results: list[dict], out_dir: str) -> None:
    """Emit shields.io *endpoint* JSON so the README badges reflect real numbers.

    Point a README badge at the raw URL of each file via
    https://img.shields.io/endpoint?url=<raw-json-url>.
    """
    agg = _aggregate(results)
    badges = {
        "ingredient_f1": {
            "label": "ingredient F1",
            "message": f"{agg['ingredient_f1']:.3f}",
            "color": _color(agg["ingredient_f1"], 0.9, 0.8),
        },
        "recall": {
            "label": "recall",
            "message": f"{agg['ingredient_recall']:.3f}",
            "color": _color(agg["ingredient_recall"], 0.9, 0.8),
        },
    }
    os.makedirs(out_dir, exist_ok=True)
    for name, body in badges.items():
        body["schemaVersion"] = 1
        with open(os.path.join(out_dir, f"{name}.json"), "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(badges)} badge endpoint file(s) to {out_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish the replay eval as a Markdown scorecard, trend history, and badges."
    )
    parser.add_argument("--model", choices=["flash", "pro"], default="flash")
    parser.add_argument("--min-f1", type=float, default=0.90, help="Floor shown on the scorecard.")
    parser.add_argument(
        "--history", metavar="PATH", help="Append the aggregate to this JSONL file."
    )
    parser.add_argument("--badges", metavar="DIR", help="Write shields.io endpoint JSON here.")
    parser.add_argument(
        "--commit", help="Commit sha to stamp on the history row (default $GITHUB_SHA)."
    )
    return parser.parse_args()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()

    with open(GROUND_TRUTH_PATH, encoding="utf-8") as f:
        by_id = {e["id"]: e for e in json.load(f)}

    replay_args = argparse.Namespace(model=args.model, threshold=85, ids=None)
    results = run_replay(by_id, replay_args)

    write_summary(render_markdown(results, args.model, args.min_f1))
    if args.history:
        append_history(results, args.model, args.history, args.commit)
    if args.badges:
        write_badges(results, args.badges)


if __name__ == "__main__":
    main()
