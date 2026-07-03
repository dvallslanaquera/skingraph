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
from src.render import render_coach_cards  # noqa: E402
from src.state import build_initial_state  # noqa: E402


def _user_label(name: str | None, uid: str, p) -> str:
    """Build a one-line menu label with the most distinctive profile traits."""
    parts = []
    if p.skin_type:
        parts.append(p.skin_type)
    if p.age:
        suffix = "F" if p.gender == "female" else "M" if p.gender == "male" else ""
        parts.append(f"{p.age}{suffix}")
    if p.goals:
        parts.append("/".join(p.goals))
    if p.is_pregnant:
        parts.append("pregnant")
    if p.skin_conditions:
        parts.append(", ".join(p.skin_conditions))
    desc = " · ".join(parts) if parts else "no profile data"
    return f"{name or '(unnamed)'}  [{uid[:8]}…]  — {desc}"


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

    users = user_store.list_users_with_profiles()
    print("\n=== Choose a user ===")
    if not users:
        print("  (no saved users — run scripts/manage_users.py seed)")
    labels = [_user_label(name, uid, p) for uid, name, p in users]
    user_idx = _pick("User #:", labels, allow_none=True) if users else None

    profile = None
    uname = None
    if user_idx is not None:
        uid, uname, profile = users[user_idx]
        goals_str = ", ".join(profile.goals) or "none"
        print(f"\nUsing profile: {uname}  (goals: {goals_str})")
    else:
        print("\nUsing no profile (generic advice).")

    print(f"\nRunning pipeline on {Path(image_path).name} … (this calls the API)\n")
    final_state = app.invoke(
        build_initial_state(image_path, "back", user_profile=profile, user_name=uname)
    )

    _print_results(final_state)


def _print_results(state):
    data = state.get("extracted_data")
    print("=" * 60)
    if data:
        print(f"PRODUCT : {data.brand} — {data.product_name}")
        lang = (data.source_language or "").strip().upper() or None
        model = state.get("model_used")
        print(f"LANGUAGE: {lang}  |  MODEL: {model}")
    if state.get("ingredient_source"):
        print(f"SOURCE  : {state.get('ingredient_source')}")
    if state.get("web_sources"):
        print(f"WEB SRC : {', '.join(state['web_sources'])}")

    notice = state.get("notice")
    if not state.get("is_ready_for_logic"):
        # Graceful exit: retake, identity, or search miss. CLI prints English.
        if notice:
            print(f"\nACTION NEEDED: {notice.en}")
        print("=" * 60)
        return

    report = state.get("safety_report")
    if report:
        print(f"\nSAFETY SCORE: {report.safety_score:.2f} / 1.00")
        for w in report.warnings:
            print(f"  {w}")

    cards = state.get("coach_cards")
    if cards:
        print("\n" + "-" * 60)
        print("COACH ADVICE")
        print("-" * 60)
        print(render_coach_cards(cards))
    print("=" * 60)


if __name__ == "__main__":
    main()
