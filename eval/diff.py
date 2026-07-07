# Eval-diff — compare two eval result sets and render a PR-comment Markdown
# block showing the before/after impact of a change.
#
#   poetry run python -m eval.diff --base base.json --head head.json
#   poetry run python -m eval.diff --base base.json --head head.json > comment.md
#
# Produce the inputs with the offline replay path on each ref:
#   python -m eval.evaluate --replay --save base.json   (on the base branch)
#   python -m eval.evaluate --replay --save head.json   (on the PR branch)
#
# This puts eval *in code review*: when a PR changes the scanner prompt or the
# cassettes, the .github/workflows/eval-diff.yml job scores both versions and
# posts "this change moved F1 0.94 → 0.91 and regressed prod_003" as a comment,
# so a probabilistic change is reviewable like any diff (EVAL-OPS.md §6). The
# staleness guard already *forces* a re-record on a prompt change — this surfaces
# the impact of that re-record instead of only demanding it.
import argparse
import json
import sys

from eval.evaluate import _aggregate


def _by_id(results: list[dict]) -> dict[str, dict]:
    return {r["id"]: r for r in results if "error" not in r}


def _f1(r: dict) -> float:
    return r["ingredients"]["f1"]


def _cost(results: list[dict]) -> float | None:
    """Mean recorded $/scan, or None when the results carry no timing."""
    costs = [
        r["perf"]["cost_usd"] for r in results if r.get("perf", {}).get("cost_usd") is not None
    ]
    return sum(costs) / len(costs) if costs else None


def _delta_str(delta: float, unit: str = "", places: int = 3) -> str:
    arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "▬")
    return f"{arrow} {delta:+.{places}f}{unit}"


def compute_diff(base: list[dict], head: list[dict]) -> dict:
    base_by, head_by = _by_id(base), _by_id(head)
    base_agg, head_agg = _aggregate(base) if base else None, _aggregate(head) if head else None

    common = sorted(set(base_by) & set(head_by))
    per_image = []
    for id_ in common:
        d = round(_f1(head_by[id_]) - _f1(base_by[id_]), 3)
        if d != 0:
            per_image.append(
                {"id": id_, "base": _f1(base_by[id_]), "head": _f1(head_by[id_]), "delta": d}
            )
    per_image.sort(key=lambda x: x["delta"])  # regressions (most negative) first

    return {
        "base_agg": base_agg,
        "head_agg": head_agg,
        "per_image": per_image,
        "added": sorted(set(head_by) - set(base_by)),
        "removed": sorted(set(base_by) - set(head_by)),
        "base_cost": _cost(base),
        "head_cost": _cost(head),
    }


def render_markdown(diff: dict) -> str:
    base_agg, head_agg = diff["base_agg"], diff["head_agg"]
    lines = ["## 🌿 Eval diff — scanner extraction", ""]

    if base_agg is None or head_agg is None:
        lines.append("_One side had no scored cassettes; cannot diff._")
        return "\n".join(lines)

    f1_delta = round(head_agg["ingredient_f1"] - base_agg["ingredient_f1"], 3)
    recall_delta = round(head_agg["ingredient_recall"] - base_agg["ingredient_recall"], 3)
    verdict = (
        "no change" if f1_delta == 0 else ("regression ⚠️" if f1_delta < 0 else "improvement ✅")
    )
    lines += [
        f"**Aggregate F1 {base_agg['ingredient_f1']:.3f} → {head_agg['ingredient_f1']:.3f}** "
        f"({_delta_str(f1_delta)}) — {verdict}",
        "",
        "| Metric | Base | Head | Δ |",
        "|--------|-----:|-----:|---:|",
        f"| Ingredient F1 | {base_agg['ingredient_f1']:.3f} | "
        f"{head_agg['ingredient_f1']:.3f} | {_delta_str(f1_delta)} |",
        f"| Recall | {base_agg['ingredient_recall']:.3f} | "
        f"{head_agg['ingredient_recall']:.3f} | {_delta_str(recall_delta)} |",
    ]
    if diff["base_cost"] is not None and diff["head_cost"] is not None:
        cost_delta = round(diff["head_cost"] - diff["base_cost"], 5)
        lines.append(
            f"| $/scan | {diff['base_cost']:.4f} | {diff['head_cost']:.4f} | "
            f"{_delta_str(cost_delta, places=4)} |"
        )
    lines.append("")

    if diff["per_image"]:
        lines += [
            "<details><summary>Per-image F1 changes</summary>",
            "",
            "| Image | Base | Head | Δ |",
            "|-------|-----:|-----:|---:|",
        ]
        for p in diff["per_image"]:
            d = _delta_str(p["delta"], places=2)
            lines.append(f"| `{p['id']}` | {p['base']:.2f} | {p['head']:.2f} | {d} |")
        lines += ["", "</details>"]
    else:
        lines.append("_No per-image F1 changes._")

    if diff["added"]:
        lines.append(f"\n➕ New cassettes scored: {', '.join(f'`{i}`' for i in diff['added'])}")
    if diff["removed"]:
        lines.append(
            f"\n➖ Cassettes no longer scored: {', '.join(f'`{i}`' for i in diff['removed'])}"
        )

    return "\n".join(lines)


def _load(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diff two eval result JSON files into a PR comment."
    )
    parser.add_argument(
        "--base", required=True, help="Base-branch results JSON (from --replay --save)."
    )
    parser.add_argument(
        "--head", required=True, help="PR-branch results JSON (from --replay --save)."
    )
    parser.add_argument("--out", help="Write the Markdown here as well as to stdout.")
    return parser.parse_args()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    diff = compute_diff(_load(args.base), _load(args.head))
    markdown = render_markdown(diff)
    print(markdown)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(markdown + "\n")


if __name__ == "__main__":
    main()
