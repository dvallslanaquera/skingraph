# Core scan orchestration, decoupled from HTTP.
#
# ``run_scan`` mirrors the input-assembly and post-scan routine save from
# run_pipeline.py, but returns a typed ScanResponse instead of logging. Keeping
# it here (not in the route handler) lets the graph be driven from tests or a
# worker without a request object.
from typing import Optional

from src.api.schemas import ScanResponse, ScanStatus
from src.graph import app as graph_app
from src.state import build_initial_state
from src.user_store import (UserNotFoundError, load_user_context,
                            save_scanned_product)


def _status_of(final_state: dict) -> ScanStatus:
    ready = final_state.get("is_ready_for_logic", False)
    advice = final_state.get("coach_advice")
    if ready and advice:
        return "complete"
    if final_state.get("retake_requested"):
        return "retake_required"
    if advice:  # confirm_identity / search_failed graceful exits
        return "action_needed"
    return "incomplete"


def _to_response(final_state: dict, added_product_id: Optional[str]) -> ScanResponse:
    return ScanResponse(
        status=_status_of(final_state),
        trace_id=final_state.get("trace_id"),
        model_used=final_state.get("model_used"),
        inference_confidence=final_state.get("inference_confidence"),
        registry_matched=final_state.get("registry_matched"),
        ingredient_source=final_state.get("ingredient_source"),
        detected_language=final_state.get("detected_language"),
        product=final_state.get("extracted_data"),
        standardized_ingredients=final_state.get("standardized_ingredients") or [],
        unmatched_ingredients=final_state.get("unmatched_ingredients") or [],
        safety_report=final_state.get("safety_report"),
        routine_fit=final_state.get("routine_fit"),
        coach_advice=final_state.get("coach_advice"),
        routine_recommendations=final_state.get("routine_recommendations") or [],
        web_sources=final_state.get("web_sources") or [],
        added_product_id=added_product_id,
    )


def run_scan(
    image_path: str,
    image_type: Optional[str] = None,
    user_id: Optional[str] = None,
    add_to_routine: bool = False,
) -> ScanResponse:
    """Run the full pipeline on an image and return a serialisable result.

    When ``user_id`` is given, the user's profile, name, and saved routine are
    loaded so the coach can personalise and evaluate cross-product fit. Raises
    UserNotFoundError if the id is unknown.
    """
    user_profile = user_name = routine_products = None
    if user_id:
        user_profile, user_name, routine_products = load_user_context(user_id)

    final_state = graph_app.invoke(
        build_initial_state(
            image_path,
            image_type,
            user_profile=user_profile,
            user_name=user_name,
            routine_products=routine_products,
        )
    )

    added_product_id = None
    if add_to_routine and user_id:
        added_product_id = save_scanned_product(user_id, final_state)

    return _to_response(final_state, added_product_id)
