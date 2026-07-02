# Run a test of the app; poetry run python run_pipeline.py data/golden_set/prod_001.jpg
import argparse
import json
import logging
import os
import sys

from dotenv import load_dotenv

from src.config import REGISTRY_CANDIDATES_PATH
from src.graph import app
from src.observability import log_tracing_status, scan_run_config
from src.render import render_coach_cards
from src.state import UserProfile, build_initial_state
from src.user_store import (UserNotFoundError, load_user_context,
                            save_scanned_product, save_user)

load_dotenv()
logging.basicConfig(level=logging.INFO)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the skincare coach pipeline on an image.")
    parser.add_argument("image_path", help="Path to the product image (e.g. data/golden_set/prod_001.jpg)")
    parser.add_argument("--image-type", choices=["front", "back"], default=None, help="Override the side of the product label; omit to auto-detect from the image")
    parser.add_argument("--user-profile", default=None, help="Path to a user profile JSON file (e.g. data/user_profile_sample.json)")
    parser.add_argument("--user-id", default=None, help="Load a saved user profile from the database by id")
    parser.add_argument("--save-user", nargs="?", const="", default=None, help="Save the --user-profile to the database (optionally with a name) and print its id")
    parser.add_argument("--add-to-routine", action="store_true", help="After a successful scan, save this product into the user's routine (requires --user-id)")
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
        "source_language": (data.source_language or "").strip().upper() or None,
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

    if args.add_to_routine and not args.user_id:
        logging.error("--add-to-routine requires --user-id (a routine belongs to a saved user).")
        sys.exit(1)

    user_profile = None
    user_name = None
    routine_products = None
    if args.user_id:
        try:
            user_profile, user_name, routine_products = load_user_context(
                args.user_id
            )
        except UserNotFoundError as exc:
            logging.error(str(exc))
            sys.exit(1)
        logging.info(
            "Loaded user profile from DB: %s (%d routine product(s))",
            args.user_id,
            len(routine_products),
        )
    elif args.user_profile:
        with open(args.user_profile, "r", encoding="utf-8") as f:
            user_profile = UserProfile.model_validate(json.load(f))
        logging.info("Loaded user profile: %s", args.user_profile)
        if args.save_user is not None:
            new_id = save_user(user_profile, name=args.save_user or None)
            logging.info("Saved user profile to DB with id: %s", new_id)

    log_tracing_status()
    logging.info("--- STARTING FULL PIPELINE INVOCATION ---")
    final_state = app.invoke(
        build_initial_state(
            args.image_path,
            args.image_type,
            user_profile=user_profile,
            user_name=user_name,
            routine_products=routine_products,
        ),
        scan_run_config(
            entrypoint="cli",
            image_type=args.image_type,
            user_id=args.user_id,
            has_routine=bool(routine_products),
        ),
    )

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
        lang = (data.source_language or "").strip().upper() or None
        logging.info(f"Language: {lang}")
        logging.info(f"Trace ID: {final_state.get('trace_id')}")

    if final_state.get("standardized_ingredients"):
        source = final_state.get("ingredient_source") or "unknown"
        logging.info(f"Normalized Ingredients (source: {source}):")
        for ing in final_state["standardized_ingredients"]:
            inci = ing.get("name_standardized") or "??? (unmapped)"
            logging.info(f"  - {ing.get('name_raw')}  ->  {inci}")

    web_sources = final_state.get("web_sources")
    if web_sources:
        logging.info(f"Web sources: {', '.join(web_sources)}")

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

    ready = final_state.get("is_ready_for_logic")
    cards = final_state.get("coach_cards")
    if cards and ready:
        logging.info("--- COACH ADVICE ---")
        for line in render_coach_cards(cards).splitlines():
            logging.info(line)
    elif final_state.get("notice"):
        # Graceful exit: retake, identity, or search miss. CLI prints English.
        logging.warning(f"ACTION NEEDED: {final_state['notice'].en}")

    # Log un-registered products only when we proceeded with a usable list.
    if final_state.get("registry_matched") is False and ready:
        data = final_state.get("extracted_data")
        if data is not None:
            record_registry_candidate(final_state)
            logging.warning(
                f"NOT IN REGISTRY: {data.brand} - {data.product_name} "
                f"saved to {REGISTRY_CANDIDATES_PATH} for later addition."
            )

    # Save this product into the user's routine when explicitly requested.
    if args.add_to_routine:
        product_id = save_scanned_product(args.user_id, final_state)
        if product_id:
            data = final_state["extracted_data"]
            logging.info(
                "Added to routine: %s - %s [product_id=%s]",
                data.brand, data.product_name, product_id,
            )
        else:
            logging.warning(
                "--add-to-routine skipped: no usable product from this scan."
            )


if __name__ == "__main__":
    main()
