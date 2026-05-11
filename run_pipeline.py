# Run a test of the app; poetry run python run_pipeline.py data/golden_set/prod_001.jpg 
import argparse
import logging
from dotenv import load_dotenv
from src.graph import app

load_dotenv()
logging.basicConfig(level=logging.INFO)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the skincare coach pipeline on an image.")
    parser.add_argument("image_path", help="Path to the product image (e.g. data/golden_set/prod_001.jpg)")
    parser.add_argument("--image-type", choices=["front", "back"], default="back", help="Side of the product label (default: back)")
    return parser.parse_args()


def main():
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
    logging.info(f"Registry Match:   {final_state.get('is_ready_for_logic')}")
    logging.info(f"Correction Loops: {final_state.get('correction_attempts', 0)}")

    if final_state.get("extracted_data"):
        data = final_state["extracted_data"]
        logging.info(f"Product:  {data.brand} - {data.product_name}")
        logging.info(f"Status:   {data.system_status}")
        logging.info(f"Trace ID: {final_state.get('trace_id')}")

    if final_state.get("standardized_ingredients"):
        logging.info("Verified Ingredients (from Registry):")
        for ing in final_state["standardized_ingredients"]:
            logging.info(f"  - {ing}")

    if final_state.get("retake_requested"):
        logging.warning(f"RETAKE REQUESTED: {final_state.get('coach_advice')}")


if __name__ == "__main__":
    main()
