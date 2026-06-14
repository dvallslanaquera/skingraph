# Run a test of the app; poetry run python run_pipeline.py data/golden_set/prod_001.jpg
import argparse
import json
import logging
import os
import sys
from dotenv import load_dotenv
from src.graph import app
from src.config import REGISTRY_CANDIDATES_PATH

load_dotenv()
logging.basicConfig(level=logging.INFO)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the skincare coach pipeline on an image.")
    parser.add_argument("image_path", help="Path to the product image (e.g. data/golden_set/prod_001.jpg)")
    parser.add_argument("--image-type", choices=["front", "back"], default="back", help="Side of the product label (default: back)")
    return parser.parse_args()


def record_registry_candidate(final_state: dict) -> None:
    """Persist an un-registered product so it can be added to the registry later."""
    data = final_state.get("extracted_data")
    if data is None:
        return

    candidates = []
    if os.path.exists(REGISTRY_CANDIDATES_PATH):
        with open(REGISTRY_CANDIDATES_PATH, "r", encoding="utf-8") as f:
            candidates = json.load(f)

    key = (data.brand.strip().lower(), data.product_name.strip().lower())
    for existing in candidates:
        seen = (existing.get("brand", "").strip().lower(),
                existing.get("product_name", "").strip().lower())
        if seen == key:
            return  # already logged

    candidates.append({
        "brand": data.brand,
        "product_name": data.product_name,
        "jan_code": data.jan_code,
        "source_language": final_state.get("detected_language"),
        "ingredients_raw": [ing.name_raw for ing in data.ingredients],
        "trace_id": final_state.get("trace_id"),
    })
    with open(REGISTRY_CANDIDATES_PATH, "w", encoding="utf-8") as f:
        json.dump(candidates, f, ensure_ascii=False, indent=2)


def main():
    # Windows consoles default to a legacy code page; force UTF-8 so Japanese
    # ingredient names render instead of mojibake.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    args = parse_args()
    inputs = {
        "image_path": args.image_path,
        "image_type": args.image_type,
        "extracted_data": None,
        "inference_confidence": 0.0,
        "correction_attempts": 0,
        "correction_feedback": None,
        "retake_requested": False,
        "is_ready_for_logic": False,
    }

    logging.info("--- STARTING FULL PIPELINE INVOCATION ---")
    final_state = app.invoke(inputs)

    logging.info("--- FINAL STATE SUMMARY ---")
    logging.info(f"Model Used:       {final_state.get('model_used')}")
    logging.info(f"Confidence:       {final_state.get('inference_confidence'):.2f}")
    logging.info(f"Registry Matched: {final_state.get('registry_matched')}")
    logging.info(f"Ready for Logic:  {final_state.get('is_ready_for_logic')}")
    logging.info(f"Correction Loops: {final_state.get('correction_attempts', 0)}")

    if final_state.get("extracted_data"):
        data = final_state["extracted_data"]
        logging.info(f"Product:  {data.brand} - {data.product_name}")
        logging.info(f"Status:   {data.system_status}")
        logging.info(f"Language: {final_state.get('detected_language')}")
        logging.info(f"Trace ID: {final_state.get('trace_id')}")

    if final_state.get("standardized_ingredients"):
        source = "Registry" if final_state.get("registry_matched") else "VLM extraction"
        logging.info(f"Normalized Ingredients (source: {source}):")
        for ing in final_state["standardized_ingredients"]:
            inci = ing.get("name_standardized") or "??? (unmapped)"
            logging.info(f"  - {ing.get('name_raw')}  ->  {inci}")

    unmatched = final_state.get("unmatched_ingredients")
    if unmatched:
        logging.warning(f"{len(unmatched)} ingredient(s) had no INCI mapping: {', '.join(unmatched)}")

    report = final_state.get("safety_report")
    if report is not None:
        logging.info(f"Safety Score:     {report.safety_score:.2f}")
        if report.ingredient_conflicts:
            logging.info(f"Ingredient Conflicts ({len(report.ingredient_conflicts)}):")
            for conflict in report.ingredient_conflicts:
                logging.info(f"  - {conflict}")
        if report.risk_ingredients:
            logging.info(f"Risk Ingredients: {', '.join(report.risk_ingredients)}")
        for warning in report.warnings:
            logging.info(f"  {warning}")

    if final_state.get("retake_requested"):
        logging.warning(f"RETAKE REQUESTED: {final_state.get('coach_advice')}")
    elif final_state.get("language_supported") is False:
        logging.warning(f"UNSUPPORTED LANGUAGE: {final_state.get('coach_advice')}")
    elif final_state.get("registry_matched") is False:
        data = final_state.get("extracted_data")
        if data is not None:
            record_registry_candidate(final_state)
            logging.warning(
                f"NOT IN REGISTRY: {data.brand} - {data.product_name} "
                f"saved to {REGISTRY_CANDIDATES_PATH} for later addition."
            )


if __name__ == "__main__":
    main()
