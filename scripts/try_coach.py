"""Interactive end-to-end test: pick an image, pick a user, see the advice.

    poetry run python scripts/try_coach.py

Lists the golden-set images and the saved user profiles, lets you choose one of
each, runs the full pipeline, and prints the product analysis, safety report,
and personalised coach advice.

Create users first with:  poetry run python scripts/manage_users.py seed
This makes live Gemini API calls (needs GOOGLE_API_KEY in .env).
"""
import logging
import os
import sys
from pathlib import Path

# Make `src` importable no matter where this script is launched from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv  # noqa: E402

from src import user_store  # noqa: E402
from src.graph import app  # noqa: E402

GOLDEN_SET = Path("data/golden_set")

# Keep the pipeline's own INFO logs quiet so the menu stays readable.
logging.basicConfig(level=logging.WARNING)


def _pick(prompt, options, allow_none=False):
    """Show a numbered menu and return the chosen index (or None)."""
    for i, label in enumerate(options, 1):
        print(f"  {i}. {label}")
    if allow_none:
        print("  0. (no profile — generic advice)")
    while True:
        raw = input(f"{prompt} ").strip()
        if allow_none and raw == "0":
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        print("  Invalid choice, try again.")


def main():
    load_dotenv()

    images = sorted(GOLDEN_SET.glob("*.jpg"))
    if not images:
        print(f"No images found in {GOLDEN_SET}/")
        sys.exit(1)

    print("\n=== Choose a product image ===")
    img_idx = _pick("Image #:", [p.name for p in images])
    image_path = str(images[img_idx])

    users = user_store.list_users()
    print("\n=== Choose a user ===")
    if not users:
        print("  (no saved users — run scripts/manage_users.py seed)")
    labels = [f"{name or '(unnamed)'}  [{uid[:8]}…]" for uid, name in users]
    user_idx = _pick("User #:", labels, allow_none=True) if users else None

    profile = None
    if user_idx is not None:
        uid = users[user_idx][0]
        profile = user_store.get_user(uid)
        print(f"\nUsing profile: {users[user_idx][1]}  (goals: {', '.join(profile.goals) or 'none'})")
    else:
        print("\nUsing no profile (generic advice).")

    print(f"\nRunning pipeline on {Path(image_path).name} … (this calls the API)\n")
    final_state = app.invoke({
        "image_path": image_path,
        "image_type": "back",
        "extracted_data": None,
        "inference_confidence": 0.0,
        "correction_attempts": 0,
        "correction_feedback": None,
        "retake_requested": False,
        "is_ready_for_logic": False,
        "user_profile": profile,
    })

    _print_results(final_state)


def _print_results(state):
    data = state.get("extracted_data")
    print("=" * 60)
    if data:
        print(f"PRODUCT : {data.brand} — {data.product_name}")
        print(f"LANGUAGE: {state.get('detected_language')}  |  MODEL: {state.get('model_used')}")

    if state.get("retake_requested"):
        print(f"\nRETAKE REQUESTED: {state.get('coach_advice')}")
        return
    if state.get("language_supported") is False:
        print(f"\nUNSUPPORTED LANGUAGE: {state.get('coach_advice')}")
        return

    report = state.get("safety_report")
    if report:
        print(f"\nSAFETY SCORE: {report.safety_score:.2f} / 1.00")
        for w in report.warnings:
            print(f"  {w}")

    advice = state.get("coach_advice")
    if advice:
        print("\n" + "-" * 60)
        print("COACH ADVICE")
        print("-" * 60)
        print(advice)
    print("=" * 60)


if __name__ == "__main__":
    main()
