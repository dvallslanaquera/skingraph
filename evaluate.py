# Evaluate scanner extraction accuracy against the annotated ground truth.
#   poetry run python evaluate.py                 # flash on all annotated images
#   poetry run python evaluate.py --model pro      # use the pro scanner
#   poetry run python evaluate.py --model both     # compare flash vs pro
#   poetry run python evaluate.py --save results.json
import argparse
import json
import logging
import os
import sys
import unicodedata
from typing import Optional

from dotenv import load_dotenv
from rapidfuzz import fuzz, process

from src.nodes.scanner import flash_scanner_node, pro_scanner_node
from src.state import ProductExtraction

GROUND_TRUTH_PATH = "data/ground_truth.json"
GOLDEN_SET_DIR = "data/golden_set"

# Fuzzy score (0-100) above which an extracted ingredient counts as a match.
INGREDIENT_MATCH_THRESHOLD = 85
# Fuzzy score above which a text field (brand/product) counts as correct.
TEXT_FIELD_THRESHOLD = 80

SCANNERS = {"flash": flash_scanner_node, "pro": pro_scanner_node}


def normalize(text: str) -> str:
    """NFKC folds full-width kana/digits to half-width so ２Ｋ == 2K."""
    return unicodedata.normalize("NFKC", text).strip().lower()


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
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )

    missed = [truth[i] for i in range(len(truth)) if i not in matched_truth_idx]
    hallucinated = [
        extracted[i] for i in range(len(extracted)) if i not in matched_extracted_idx
    ]
    return {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "truth_count": len(truth),
        "extracted_count": len(extracted),
        "missed": missed,
        "hallucinated": hallucinated,
    }


def run_scanner(model: str, image_path: str) -> Optional[ProductExtraction]:
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


def evaluate_one(model: str, entry: dict, threshold: int) -> Optional[dict]:
    gt = entry["ground_truth"]
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

    brand_score = score_text_field(extracted.brand, gt["brand_name"])
    product_score = score_text_field(extracted.product_name, gt["product_name"])
    quasi_correct = extracted.is_quasi_drug == gt["is_medicated_quasi_drug"]

    raw_ingredients = [ing.name_raw for ing in extracted.ingredients]
    ing = score_ingredients(raw_ingredients, gt["full_ingredient_list"], threshold)

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
            print(f"    missed ({len(ing['missed'])}): {', '.join(ing['missed'][:10])}"
                  + (" ..." if len(ing["missed"]) > 10 else ""))
        if ing["hallucinated"]:
            print(f"    extra  ({len(ing['hallucinated'])}): "
                  f"{', '.join(ing['hallucinated'][:10])}"
                  + (" ..." if len(ing["hallucinated"]) > 10 else ""))

    for r in errored:
        print(f"\n[{r['id']}]  model={r['model']}  ERROR: {r['error']}")

    if scored:
        n = len(scored)
        avg_f1 = sum(r["ingredients"]["f1"] for r in scored) / n
        avg_recall = sum(r["ingredients"]["recall"] for r in scored) / n
        avg_brand = sum(r["brand_score"] for r in scored) / n
        avg_product = sum(r["product_score"] for r in scored) / n
        quasi_ok = sum(r["quasi_drug_correct"] for r in scored)
        print("\n" + "-" * 70)
        print(f"  AGGREGATE over {n} image(s)")
        print(f"    ingredient F1     : {avg_f1:.2f}")
        print(f"    ingredient recall : {avg_recall:.2f}")
        print(f"    brand match       : {avg_brand:.0f}/100")
        print(f"    product match     : {avg_product:.0f}/100")
        print(f"    quasi-drug correct: {quasi_ok}/{n}")
    print("=" * 70 + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score scanner extraction against data/ground_truth.json."
    )
    parser.add_argument(
        "--model", choices=["flash", "pro", "both"], default="flash",
        help="Which scanner to evaluate (default: flash).",
    )
    parser.add_argument(
        "--threshold", type=int, default=INGREDIENT_MATCH_THRESHOLD,
        help=f"Fuzzy match cutoff for ingredients (default: {INGREDIENT_MATCH_THRESHOLD}).",
    )
    parser.add_argument(
        "--id", action="append", dest="ids",
        help="Only evaluate these ground-truth id(s). Repeatable.",
    )
    parser.add_argument(
        "--save", metavar="PATH", help="Write full results as JSON to PATH.",
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

    with open(GROUND_TRUTH_PATH, "r", encoding="utf-8") as f:
        entries = json.load(f)

    if args.ids:
        wanted = set(args.ids)
        entries = [e for e in entries if e["id"] in wanted]

    models = ["flash", "pro"] if args.model == "both" else [args.model]

    results: list[dict] = []
    for model in models:
        for entry in entries:
            logging.info("Evaluating %s with %s scanner...", entry["id"], model)
            res = evaluate_one(model, entry, args.threshold)
            if res is not None:
                results.append(res)

    print_report(results)

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"Results written to {args.save}")


if __name__ == "__main__":
    main()
