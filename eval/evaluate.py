# Evaluate scanner extraction accuracy against the annotated ground truth.
#
# Live (needs GOOGLE_API_KEY in .env + the golden-set images on disk):
#   poetry run python -m eval.evaluate                # flash on all annotated images
#   poetry run python -m eval.evaluate --model pro    # use the pro scanner
#   poetry run python -m eval.evaluate --model both   # compare flash vs pro
#   poetry run python -m eval.evaluate --record       # live run + write replay cassettes
#
# Offline (the CI quality gate — no API key, no images needed):
#   poetry run python -m eval.evaluate --replay --min-f1 0.90
#
# --record captures each image's ProductExtraction into a JSON cassette under
# eval/cassettes/ (committed to git), plus a manifest.json with the aggregate
# scores at record time. --replay skips the VLM entirely, feeds the recorded
# extractions through the real scoring path (canonical-INCI resolution → fuzzy
# P/R/F1), and exits non-zero when the aggregate F1 drops below --min-f1 — or
# when the scanner prompt / model id no longer match what the cassettes were
# recorded with, so a prompt change can never ship with stale eval numbers.
#
# Ingredients are scored in canonical English-INCI space so the metric is
# language-independent: a Korean or English label can score against the same
# ground truth as a Japanese one. Each extracted ingredient is run through the
# translation-normalization layer (the VLM's own `name_standardized` INCI, with
# the normalizer ledger as a fallback) and compared against the `ingredient_inci`
# translations stored alongside each product in ground_truth.json.
import argparse
import hashlib
import json
import logging
import os
import sys
import unicodedata
from datetime import datetime, timezone

from dotenv import load_dotenv
from rapidfuzz import fuzz, process

from src.config import FLASH_MODEL, PRO_MODEL
from src.nodes.normalizer import _load_index
from src.nodes.normalizer import _normalize as _ledger_key
from src.nodes.scanner import flash_scanner_node, pro_scanner_node
from src.state import Ingredient, ProductExtraction

GROUND_TRUTH_PATH = "data/ground_truth.json"
GOLDEN_SET_DIR = "data/golden_set"
CASSETTE_DIR = os.path.join("eval", "cassettes")
MANIFEST_PATH = os.path.join(CASSETTE_DIR, "manifest.json")

# Fuzzy score (0-100) above which an extracted ingredient counts as a match.
INGREDIENT_MATCH_THRESHOLD = 85
# Fuzzy score above which a text field (brand/product) counts as correct.
TEXT_FIELD_THRESHOLD = 80

SCANNERS = {"flash": flash_scanner_node, "pro": pro_scanner_node}
MODEL_IDS = {"flash": FLASH_MODEL, "pro": PRO_MODEL}


def normalize(text: str) -> str:
    """NFKC folds full-width kana/digits to half-width so ２Ｋ == 2K."""
    return unicodedata.normalize("NFKC", text).strip().lower()


# Ledger index for the translation-normalization layer, loaded once.
_NORM_INDEX: dict | None = None


def canonical_inci(ingredient: Ingredient) -> str:
    """Resolve an extracted ingredient to a canonical English-INCI name.

    The VLM already standardizes any source language into an English INCI in
    `name_standardized` (e.g. 히드로퀴논 -> 'Hydroquinone'), so we try it first;
    both it and the raw name are looked up in the normalizer ledger so the
    extraction and the ground truth land on the *same* canonical key. Falls back
    to the best available raw string when nothing resolves.

    Only the ledger's exact tier is used — not the Qdrant semantic tier — so the
    metric is deterministic and runs offline in CI (no vector index, no embedding
    model). The fuzzy matcher in score_ingredients absorbs near-miss spellings.
    """
    global _NORM_INDEX
    if _NORM_INDEX is None:
        _NORM_INDEX = _load_index()
    for candidate in (ingredient.name_standardized, ingredient.name_raw):
        if candidate:
            inci = _NORM_INDEX.get(_ledger_key(candidate))
            if inci:
                return inci
    return ingredient.name_standardized or ingredient.name_raw or ""


def score_text_field(extracted: str, truth: str) -> float:
    """Truth fields are often bilingual ('Cetaphil / セタフィル'); match either side."""
    parts = [p.strip() for p in truth.split("/") if p.strip()]
    extracted_n = normalize(extracted)
    return max((fuzz.WRatio(extracted_n, normalize(p)) for p in parts), default=0.0)


def score_ingredients(extracted: list[str], truth: list[str], threshold: int) -> dict:
    """Fuzzy set comparison → precision / recall / F1 plus diagnostic lists."""
    truth_n = [normalize(t) for t in truth]
    extracted_n = [normalize(e) for e in extracted]

    matched_truth_idx: set[int] = set()
    matched_extracted_idx: set[int] = set()

    for i, e in enumerate(extracted_n):
        if not truth_n:
            break
        best = process.extractOne(e, truth_n, scorer=fuzz.WRatio)
        if best and best[1] >= threshold:
            matched_extracted_idx.add(i)
            matched_truth_idx.add(best[2])

    recall = len(matched_truth_idx) / len(truth_n) if truth_n else 0.0
    precision = len(matched_extracted_idx) / len(extracted_n) if extracted_n else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    missed = [truth[i] for i in range(len(truth)) if i not in matched_truth_idx]
    hallucinated = [extracted[i] for i in range(len(extracted)) if i not in matched_extracted_idx]
    return {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "truth_count": len(truth),
        "extracted_count": len(extracted),
        "missed": missed,
        "hallucinated": hallucinated,
    }


def run_scanner(model: str, image_path: str) -> ProductExtraction | None:
    state = {
        "image_path": image_path,
        "image_type": "back",
        "extracted_data": None,
        "inference_confidence": 0.0,
        "correction_attempts": 0,
        "correction_feedback": None,
    }
    result = SCANNERS[model](state)
    return result.get("extracted_data")


def score_extraction(model: str, entry: dict, extracted: ProductExtraction, threshold: int) -> dict:
    """Score one extraction (live or replayed) against its ground-truth entry."""
    gt = entry["ground_truth"]

    brand_score = score_text_field(extracted.brand, gt["brand_name"])
    product_score = score_text_field(extracted.product_name, gt["product_name"])
    quasi_correct = extracted.is_quasi_drug == gt["is_medicated_quasi_drug"]

    # Score in canonical INCI space so the comparison is language-independent.
    extracted_inci = [canonical_inci(ing) for ing in extracted.ingredients]
    truth_inci = gt.get("ingredient_inci") or gt["full_ingredient_list"]
    ing = score_ingredients(extracted_inci, truth_inci, threshold)

    return {
        "id": entry["id"],
        "model": model,
        "difficulty": entry["metadata"].get("difficulty_score"),
        "confidence": round(extracted.extraction_confidence, 3),
        "system_status": extracted.system_status,
        "brand_score": round(brand_score, 1),
        "product_score": round(product_score, 1),
        "quasi_drug_correct": quasi_correct,
        "ingredients": ing,
    }


def evaluate_live(model: str, entry: dict, threshold: int, record: bool) -> dict | None:
    """Run the real scanner on one golden-set image; optionally write a cassette."""
    file_name = entry["metadata"]["file_name"]
    image_path = os.path.join(GOLDEN_SET_DIR, file_name)

    if not os.path.exists(image_path):
        logging.warning("Skipping %s — image not found at %s", entry["id"], image_path)
        return None

    try:
        extracted = run_scanner(model, image_path)
    except Exception as exc:  # noqa: BLE001 — surface API/parse failures per-item
        logging.error("Scanner failed on %s: %s", entry["id"], exc)
        return {"id": entry["id"], "model": model, "error": str(exc)}

    if extracted is None:
        return {"id": entry["id"], "model": model, "error": "no extraction returned"}

    if record:
        # Only successful reads are replayable: several golden-set photos show
        # the FRONT of the product (annotated from the physical label), so their
        # extractions carry no ingredients and their F1 is structurally zero —
        # replaying them would gate on photo composition, not on code.
        if extracted.system_status == "SUCCESS":
            _write_cassette(model, entry, extracted, image_path)
        else:
            logging.info(
                "Not recording %s (%s): no readable ingredient list to replay.",
                entry["id"],
                extracted.system_status,
            )

    return score_extraction(model, entry, extracted, threshold)


# --- cassettes (record / replay) ---------------------------------------------


def _prompt_sha256() -> str:
    """Hash of the scanner extraction prompt — the cassette staleness key."""
    from src.prompts.scanner import SCANNER_SYSTEM_PROMPT

    return hashlib.sha256(SCANNER_SYSTEM_PROMPT.encode("utf-8")).hexdigest()


def _file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cassette_path(model: str, entry: dict) -> str:
    stem = os.path.splitext(entry["metadata"]["file_name"])[0]
    return os.path.join(CASSETTE_DIR, f"{stem}.{model}.json")


RERECORD_HINT = "re-record locally with: poetry run python -m eval.evaluate --record"


def _write_cassette(model: str, entry: dict, extracted: ProductExtraction, image_path: str) -> None:
    payload = {
        "id": entry["id"],
        "image_sha256": _file_sha256(image_path),
        "model_id": MODEL_IDS[model],
        "prompt_sha256": _prompt_sha256(),
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "extraction": extracted.model_dump(),
    }
    os.makedirs(CASSETTE_DIR, exist_ok=True)
    path = _cassette_path(model, entry)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logging.info("Recorded cassette: %s", path)


def _load_cassette(model: str, entry: dict) -> ProductExtraction:
    """Load one cassette, refusing to replay stale recordings."""
    path = _cassette_path(model, entry)
    if not os.path.exists(path):
        sys.exit(f"Cassette missing for {entry['id']} ({path}) — {RERECORD_HINT}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if data["prompt_sha256"] != _prompt_sha256() or data["model_id"] != MODEL_IDS[model]:
        sys.exit(
            f"STALE CASSETTE {path}: the scanner prompt or model id changed since "
            f"this was recorded — the recorded scores no longer describe the current "
            f"pipeline; {RERECORD_HINT}"
        )
    # Images stay out of git; verify only when present (i.e. locally).
    image_path = os.path.join(GOLDEN_SET_DIR, entry["metadata"]["file_name"])
    if os.path.exists(image_path) and _file_sha256(image_path) != data["image_sha256"]:
        sys.exit(f"{image_path} changed since its cassette was recorded — {RERECORD_HINT}")

    return ProductExtraction.model_validate(data["extraction"])


def _aggregate(scored: list[dict]) -> dict:
    n = len(scored)
    return {
        "images": n,
        "ingredient_f1": round(sum(r["ingredients"]["f1"] for r in scored) / n, 3),
        "ingredient_recall": round(sum(r["ingredients"]["recall"] for r in scored) / n, 3),
        "brand_score": round(sum(r["brand_score"] for r in scored) / n, 1),
        "product_score": round(sum(r["product_score"] for r in scored) / n, 1),
        "quasi_drug_correct": sum(r["quasi_drug_correct"] for r in scored),
    }


def write_manifest(results: list[dict], models: list[str], threshold: int) -> None:
    """Aggregate scores + covered ids at record time, one block per model."""
    manifest: dict = {
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "prompt_sha256": _prompt_sha256(),
        "threshold": threshold,
        "models": {},
    }
    for model in models:
        # The manifest lists only the replayable (SUCCESS) cassettes — see
        # evaluate_live for why non-SUCCESS extractions are not recorded.
        scored = [
            r
            for r in results
            if r["model"] == model and "error" not in r and r["system_status"] == "SUCCESS"
        ]
        if not scored:
            continue
        manifest["models"][model] = {
            "model_id": MODEL_IDS[model],
            "ids": [r["id"] for r in scored],
            "aggregate": _aggregate(scored),
        }
    os.makedirs(CASSETTE_DIR, exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"Manifest written to {MANIFEST_PATH}")


def run_replay(by_id: dict[str, dict], args: argparse.Namespace) -> list[dict]:
    """Score every recorded cassette through the real scoring path, VLM skipped."""
    if args.model == "both":
        sys.exit("--replay gates one model at a time; pass --model flash or --model pro.")
    if not os.path.exists(MANIFEST_PATH):
        sys.exit(f"No cassette manifest at {MANIFEST_PATH} — {RERECORD_HINT}")
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest = json.load(f)

    spec = manifest.get("models", {}).get(args.model)
    if not spec:
        sys.exit(f"No '{args.model}' cassettes in the manifest — {RERECORD_HINT}")

    ids = spec["ids"]
    if args.ids:
        ids = [i for i in ids if i in set(args.ids)]

    results = []
    for id_ in ids:
        entry = by_id.get(id_)
        if entry is None:
            sys.exit(
                f"{id_} has a cassette but no ground_truth.json entry — the golden "
                f"set and the cassettes have drifted apart; {RERECORD_HINT}"
            )
        extracted = _load_cassette(args.model, entry)
        results.append(score_extraction(args.model, entry, extracted, args.threshold))
    return results


def apply_gate(results: list[dict], min_f1: float | None) -> None:
    """Exit non-zero when the aggregate ingredient F1 is below the floor."""
    if min_f1 is None:
        return
    errored = [r for r in results if "error" in r]
    if errored:
        sys.exit(f"EVAL GATE FAILED: {len(errored)} cassette(s) could not be scored.")
    if not results:
        sys.exit("EVAL GATE FAILED: no cassettes were scored.")
    f1 = _aggregate(results)["ingredient_f1"]
    if f1 < min_f1:
        sys.exit(f"EVAL GATE FAILED: aggregate ingredient F1 {f1:.3f} < floor {min_f1:.2f}")
    print(f"EVAL GATE PASSED: aggregate ingredient F1 {f1:.3f} >= floor {min_f1:.2f}")


# --- reporting ----------------------------------------------------------------


def print_report(results: list[dict]) -> None:
    scored = [r for r in results if "error" not in r]
    errored = [r for r in results if "error" in r]

    print("\n" + "=" * 70)
    print("  SCANNER EXTRACTION EVALUATION")
    print("=" * 70)

    for r in scored:
        ing = r["ingredients"]
        print(f"\n[{r['id']}]  model={r['model']}  difficulty={r['difficulty']}")
        print(f"  confidence reported : {r['confidence']:.2f}  ({r['system_status']})")
        print(f"  brand match         : {r['brand_score']:.0f}/100")
        print(f"  product match       : {r['product_score']:.0f}/100")
        print(f"  quasi-drug flag     : {'OK' if r['quasi_drug_correct'] else 'WRONG'}")
        print(
            f"  ingredients         : P={ing['precision']:.2f} "
            f"R={ing['recall']:.2f} F1={ing['f1']:.2f}  "
            f"({ing['extracted_count']} extracted / {ing['truth_count']} truth)"
        )
        if ing["missed"]:
            print(
                f"    missed ({len(ing['missed'])}): {', '.join(ing['missed'][:10])}"
                + (" ..." if len(ing["missed"]) > 10 else "")
            )
        if ing["hallucinated"]:
            print(
                f"    extra  ({len(ing['hallucinated'])}): {', '.join(ing['hallucinated'][:10])}"
                + (" ..." if len(ing["hallucinated"]) > 10 else "")
            )

    for r in errored:
        print(f"\n[{r['id']}]  model={r['model']}  ERROR: {r['error']}")

    if scored:
        agg = _aggregate(scored)
        print("\n" + "-" * 70)
        print(f"  AGGREGATE over {agg['images']} image(s)")
        print(f"    ingredient F1     : {agg['ingredient_f1']:.2f}")
        print(f"    ingredient recall : {agg['ingredient_recall']:.2f}")
        print(f"    brand match       : {agg['brand_score']:.0f}/100")
        print(f"    product match     : {agg['product_score']:.0f}/100")
        print(f"    quasi-drug correct: {agg['quasi_drug_correct']}/{agg['images']}")
    print("=" * 70 + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score scanner extraction against data/ground_truth.json."
    )
    parser.add_argument(
        "--model",
        choices=["flash", "pro", "both"],
        default="flash",
        help="Which scanner to evaluate (default: flash).",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=INGREDIENT_MATCH_THRESHOLD,
        help=f"Fuzzy match cutoff for ingredients (default: {INGREDIENT_MATCH_THRESHOLD}).",
    )
    parser.add_argument(
        "--id",
        action="append",
        dest="ids",
        help="Only evaluate these ground-truth id(s). Repeatable.",
    )
    parser.add_argument(
        "--save",
        metavar="PATH",
        help="Write full results as JSON to PATH.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--record",
        action="store_true",
        help="Live run that also writes replay cassettes to eval/cassettes/.",
    )
    mode.add_argument(
        "--replay",
        action="store_true",
        help="Offline: score the recorded cassettes instead of calling the VLM.",
    )
    parser.add_argument(
        "--min-f1",
        type=float,
        default=None,
        help="With --replay: fail (exit 1) if aggregate ingredient F1 is below this.",
    )
    return parser.parse_args()


def main() -> None:
    # Windows consoles default to a legacy code page; force UTF-8 so the
    # Japanese ingredient diagnostics render instead of mojibake.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args()

    with open(GROUND_TRUTH_PATH, encoding="utf-8") as f:
        entries = json.load(f)
    by_id = {e["id"]: e for e in entries}

    if args.replay:
        results = run_replay(by_id, args)
        print_report(results)
        apply_gate(results, args.min_f1)
        return

    if args.ids:
        wanted = set(args.ids)
        entries = [e for e in entries if e["id"] in wanted]

    models = ["flash", "pro"] if args.model == "both" else [args.model]

    if args.record and not args.ids and os.path.isdir(CASSETTE_DIR):
        # Full-set re-record: drop this model's old cassettes so images that no
        # longer qualify (or were renamed) don't linger as orphans.
        for model in models:
            for name in os.listdir(CASSETTE_DIR):
                if name.endswith(f".{model}.json"):
                    os.remove(os.path.join(CASSETTE_DIR, name))

    results: list[dict] = []
    for model in models:
        for entry in entries:
            logging.info("Evaluating %s with %s scanner...", entry["id"], model)
            res = evaluate_live(model, entry, args.threshold, record=args.record)
            if res is not None:
                results.append(res)

    print_report(results)

    if args.record:
        if args.ids:
            print("Skipping manifest write: --record with --id covers only a subset.")
        else:
            write_manifest(results, models, args.threshold)

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"Results written to {args.save}")


if __name__ == "__main__":
    main()
