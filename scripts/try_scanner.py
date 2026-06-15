"""Manual smoke test for the Gemini scanner nodes (makes live API calls).

    poetry run python scripts/try_scanner.py

Runs the Flash and Pro scanners against a single golden-set image and prints the
extracted JSON. Needs GOOGLE_API_KEY in .env. Not a pytest test — the automated,
fully-mocked coverage lives in tests/test_scanner.py.
"""
import os
import sys

# Make `src` importable no matter where this script is launched from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

from src.nodes.scanner import flash_scanner_node, pro_scanner_node  # noqa: E402

load_dotenv()


def run_test():
    image_path = "data/golden_set/prod_001.jpg"

    if not os.path.exists(image_path):
        print(f"Error: Could not find image at {image_path}")
        return

    initial_state = {
        "image_path": image_path,
        "image_type": "back",
        "extracted_data": None,
        "inference_confidence": 0.0,
        "model_used": "none",
    }

    print("\n--- TEST 1: GEMINI FLASH (Lightweight) ---")
    try:
        flash_result = flash_scanner_node(initial_state)
        print(f"Confidence: {flash_result['inference_confidence']}")
        print("Extracted JSON:")
        print(flash_result["extracted_data"].model_dump_json(indent=2))
    except Exception as e:
        print(f"Flash Node Failed: {e}")

    print("\n--- TEST 2: GEMINI PRO (Heavyweight) ---")
    try:
        pro_result = pro_scanner_node(initial_state)
        print(f"Confidence: {pro_result['inference_confidence']}")
        print("Extracted JSON:")
        print(pro_result["extracted_data"].model_dump_json(indent=2))
    except Exception as e:
        print(f"Pro Node Failed: {e}")


if __name__ == "__main__":
    run_test()
