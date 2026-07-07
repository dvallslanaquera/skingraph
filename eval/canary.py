# Nightly live canary — drift detection against a pinned baseline.
#
#   # Live (needs GOOGLE_API_KEY + the golden images on disk):
#   poetry run python -m eval.canary --limit 2 --tolerance 0.05
#   # Offline self-test (replays the cassette as the "live" read; always green):
#   poetry run python -m eval.canary --dry-run
#
# The replay gate never calls the API, so by construction it cannot see the API
# *change*. We do not control Gemini: a model behind an endpoint can silently
# regress. This canary runs a *handful* of golden images LIVE, diffs the fresh
# extraction against the committed cassette baseline, and exits non-zero on
# divergence — an F1 drop beyond tolerance, a latency blow-out, or a
# schema-invalid read. .github/workflows/canary.yml runs it on a schedule and
# opens an issue when it trips (EVAL-OPS.md §7). Cheap early-warning sensor, not
# the full suite.
import argparse
import json
import os
import sys

from dotenv import load_dotenv

from eval.evaluate import (
    GOLDEN_SET_DIR,
    GROUND_TRUTH_PATH,
    MANIFEST_PATH,
    RERECORD_HINT,
    _load_cassette,
    run_scanner_timed,
    score_extraction,
)
from src.state import ProductExtraction

# A live read slower than this (seconds) is itself a drift signal worth a look.
DEFAULT_MAX_LATENCY = 30.0
# F1 may drop this far below the pinned baseline before we call it drift; below
# that is provider noise, not a regression.
DEFAULT_TOLERANCE = 0.05


def _canary_ids(limit: int, ids: list[str] | None) -> list[str]:
    if not os.path.exists(MANIFEST_PATH):
        sys.exit(f"No cassette manifest at {MANIFEST_PATH} — {RERECORD_HINT}")
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest = json.load(f)
    available = manifest.get("models", {}).get("flash", {}).get("ids", [])
    if ids:
        return [i for i in ids if i in available]
    return available[:limit]


def check_image(entry: dict, *, dry_run: bool, tolerance: float, max_latency: float) -> dict:
    """Score a fresh live read against the pinned cassette; flag divergence."""
    baseline = _load_cassette("flash", entry)
    base_f1 = score_extraction("flash", entry, baseline, 85)["ingredients"]["f1"]

    reasons: list[str] = []
    if dry_run:
        live, latency = baseline, 0.0
    else:
        image_path = os.path.join(GOLDEN_SET_DIR, entry["metadata"]["file_name"])
        if not os.path.exists(image_path):
            sys.exit(f"Canary image missing: {image_path} (live run needs the golden images).")
        raw, perf = run_scanner_timed("flash", image_path)
        latency = perf["latency_seconds"]
        if not isinstance(raw, ProductExtraction):
            reasons.append("schema-invalid extraction")
            live = baseline  # score something; the reason above already trips it
        else:
            live = raw

    live_f1 = score_extraction("flash", entry, live, 85)["ingredients"]["f1"]
    delta = round(live_f1 - base_f1, 3)
    if delta < -tolerance:
        reasons.append(f"F1 {base_f1:.2f} → {live_f1:.2f} ({delta:+.2f}, tol {tolerance:.2f})")
    if latency > max_latency:
        reasons.append(f"latency {latency:.1f}s > {max_latency:.0f}s")

    return {
        "id": entry["id"],
        "base_f1": base_f1,
        "live_f1": live_f1,
        "delta": delta,
        "latency": latency,
        "reasons": reasons,
        "diverged": bool(reasons),
    }


def render_summary(results: list[dict]) -> str:
    diverged = [r for r in results if r["diverged"]]
    head = "🚨 Canary drift detected" if diverged else "✅ Canary green"
    lines = [
        f"## {head}",
        "",
        "| Image | Base F1 | Live F1 | Δ | Latency | Status |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for r in results:
        status = "; ".join(r["reasons"]) if r["reasons"] else "ok"
        lines.append(
            f"| `{r['id']}` | {r['base_f1']:.2f} | {r['live_f1']:.2f} | {r['delta']:+.2f} | "
            f"{r['latency']:.1f}s | {status} |"
        )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Live drift canary against the pinned cassettes.")
    parser.add_argument("--limit", type=int, default=2, help="How many golden images to run live.")
    parser.add_argument(
        "--id", action="append", dest="ids", help="Run these ids instead. Repeatable."
    )
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    parser.add_argument("--max-latency", type=float, default=DEFAULT_MAX_LATENCY)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Replay cassettes as the live read (offline self-test).",
    )
    parser.add_argument(
        "--summary", metavar="PATH", help="Write the Markdown summary here (issue body)."
    )
    return parser.parse_args()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv()
    args = parse_args()

    with open(GROUND_TRUTH_PATH, encoding="utf-8") as f:
        by_id = {e["id"]: e for e in json.load(f)}

    ids = _canary_ids(args.limit, args.ids)
    if not ids:
        sys.exit("No canary ids resolved from the manifest.")

    results = [
        check_image(
            by_id[i], dry_run=args.dry_run, tolerance=args.tolerance, max_latency=args.max_latency
        )
        for i in ids
        if i in by_id
    ]
    summary = render_summary(results)
    print(summary)
    if args.summary:
        with open(args.summary, "w", encoding="utf-8") as f:
            f.write(summary + "\n")

    if any(r["diverged"] for r in results):
        sys.exit("CANARY DIVERGED: live extraction drifted from the pinned baseline.")


if __name__ == "__main__":
    main()
