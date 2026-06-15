# Core scan orchestration, decoupled from HTTP.
#
# ``run_scan`` mirrors the input-assembly and post-scan routine save from
# run_pipeline.py, but returns a typed ScanResponse instead of logging. Keeping
# it here (not in the route handler) lets the graph be driven from tests or a
# worker without a request object.
from typing import List, Optional

from src.api.schemas import ScanResponse, ScanStatus
from src.graph import app as graph_app
from src.user_store import (add_routine_product, get_routine, get_user,
                            get_user_name)


class UserNotFoundError(Exception):
    """Raised when a scan/routine call references an unknown user_id."""

    def __init__(self, user_id: str):
        self.user_id = user_id
        super().__init__(f"No user found with id: {user_id}")


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


def _save_to_routine(user_id: str, final_state: dict) -> Optional[str]:
    """Persist the scanned product to the user's shelf; returns its product_id.

    Skips silently (returns None) when the scan didn't yield a usable product,
    matching the CLI's --add-to-routine behaviour.
    """
    data = final_state.get("extracted_data")
    if not final_state.get("is_ready_for_logic") or data is None:
        return None
    inci = [
        ing.get("name_standardized")
        for ing in (final_state.get("standardized_ingredients") or [])
        if ing.get("name_standardized")
    ]
    return add_routine_product(
        user_id, data.brand, data.product_name, inci, data.is_quasi_drug
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
    user_profile = None
    user_name = None
    routine_products = None
    if user_id:
        user_profile = get_user(user_id)
        if user_profile is None:
            raise UserNotFoundError(user_id)
        user_name = get_user_name(user_id)
        routine_products = get_routine(user_id)

    inputs = {
        "image_path": image_path,
        "image_type": image_type,
        "extracted_data": None,
        "inference_confidence": 0.0,
        "correction_attempts": 0,
        "correction_feedback": None,
        "retake_requested": False,
        "is_ready_for_logic": False,
        "user_profile": user_profile,
        "user_name": user_name,
        "routine_products": routine_products,
    }

    final_state = graph_app.invoke(inputs)

    added_product_id = None
    if add_to_routine and user_id:
        added_product_id = _save_to_routine(user_id, final_state)

    return _to_response(final_state, added_product_id)
