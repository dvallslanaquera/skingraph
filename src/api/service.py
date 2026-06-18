# Core scan orchestration, decoupled from HTTP.
#
# ``run_scan`` mirrors the input-assembly and post-scan routine save from
# run_pipeline.py, but returns a typed ScanResponse instead of logging. Keeping
# it here (not in the route handler) lets the graph be driven from tests or a
# worker without a request object.
import asyncio
import json
import logging
from typing import AsyncIterator, Optional

from src.api.schemas import ScanResponse, ScanStatus
from src.graph import app as graph_app
from src.observability import scan_run_config
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
        coach_advice_ja=final_state.get("coach_advice_ja"),
        coach_advice_en=final_state.get("coach_advice_en"),
        recommendation_score=final_state.get("recommendation_score"),
        recommendation_rationale_ja=final_state.get("recommendation_rationale_ja"),
        recommendation_rationale_en=final_state.get("recommendation_rationale_en"),
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
        ),
        scan_run_config(
            entrypoint="api",
            image_type=image_type,
            user_id=user_id,
            has_routine=bool(routine_products),
        ),
    )

    added_product_id = None
    if add_to_routine and user_id:
        added_product_id = save_scanned_product(user_id, final_state)

    return _to_response(final_state, added_product_id)


# --- streaming scan ----------------------------------------------------------
#
# The single-shot /scan runs the whole LangGraph pipeline in one blocking POST.
# On the deployed stack that request exceeds the platform's connection ceiling
# (the coach is the slowest step), the proxy drops it, and the browser reports a
# generic "backend not running" network error. run_scan_stream() instead drives
# the graph with graph_app.stream(...) and emits Server-Sent Events as each node
# finishes, so bytes flow continuously (no idle proxy timeout) and the UI can show
# real per-stage progress plus a typewriter reveal of the coach card.
#
# The graph's structured-output coach call cannot be token-streamed as prose (it
# streams JSON, not the rendered card), so the coach card is revealed in small
# slices once the coach node has produced it — a genuine streamed reveal without
# compromising the bilingual structured card the app relies on.

# Graph node -> pipeline step (1..5) for the UI's stage indicator. Matches the
# five pipeline.stepN i18n labels (scan / extract / safety / routine / recommend).
_NODE_STEP = {
    "image_quality_gate": 1, "classify_side": 1, "flash_scanner": 1,
    "early_registry_check": 1, "correction": 1, "pro_scanner": 1,
    "verify_identity": 1, "web_search": 1, "confirm_identity": 1,
    "search_failed": 1, "retake_request": 1,
    "tag_language": 2, "registry_lookup": 2, "normalizer": 2,
    "auditor": 3, "routine_advisor": 4, "coach": 5,
}

# Emit an SSE keepalive comment if no graph event arrives within this window, so
# a long single-node VLM call can never trip an idle proxy timeout.
_KEEPALIVE_S = 15
# Coach typewriter reveal: card slice size (chars) and pacing delay (seconds).
_COACH_CHUNK_CHARS = 6
_COACH_CHUNK_DELAY = 0.02


def _sse(event: dict) -> bytes:
    """Serialise one SSE ``data:`` frame (UTF-8, JSON payload, no ASCII escaping)."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")


def _pick_advice(state: dict, lang: Optional[str]) -> Optional[str]:
    """The coach card to typewriter, in the UI's language; falls back to the
    combined bilingual blob for graceful-exit (retake / search-failed) messages,
    which only populate coach_advice."""
    if lang == "ja":
        return state.get("coach_advice_ja") or state.get("coach_advice")
    return state.get("coach_advice_en") or state.get("coach_advice")


async def run_scan_stream(
    image_path: str,
    image_type: Optional[str] = None,
    user_id: Optional[str] = None,
    add_to_routine: bool = False,
    lang: Optional[str] = None,
) -> AsyncIterator[bytes]:
    """Run the pipeline, yielding SSE frames as each node completes.

    Frames (one ``data:`` line each, JSON with an ``event`` field):
      stage       — {node, step}                 per node (drives real progress)
      partial     — {data: partial ScanResponse} per node (fields known so far)
      coach_delta — {text}                       typewriter slices of the coach card
      complete    — {data: full ScanResponse}    final
      error       — {message}                    on failure
    """
    user_profile = user_name = routine_products = None
    if user_id:
        user_profile, user_name, routine_products = load_user_context(user_id)

    initial_state = build_initial_state(
        image_path,
        image_type,
        user_profile=user_profile,
        user_name=user_name,
        routine_products=routine_products,
    )
    config = scan_run_config(
        entrypoint="api-stream",
        image_type=image_type,
        user_id=user_id,
        has_routine=bool(routine_products),
    )

    # The graph stream is synchronous and blocking (VLM calls per node), so it
    # runs in a worker thread that pushes (mode, chunk) tuples onto an
    # asyncio.Queue via the loop. The async generator below drains the queue with
    # a timeout so it can emit keepalive pings during long single-node calls.
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    sentinel = object()

    async def producer() -> None:
        def _run() -> None:
            try:
                for chunk in graph_app.stream(
                    initial_state, config, stream_mode=["updates", "values"]
                ):
                    loop.call_soon_threadsafe(queue.put_nowait, chunk)
            except Exception as exc:  # noqa: BLE001 — surfaced to the client
                loop.call_soon_threadsafe(queue.put_nowait, ("__error__", exc))
                return
            loop.call_soon_threadsafe(queue.put_nowait, sentinel)

        await loop.run_in_executor(None, _run)

    task = asyncio.create_task(producer())
    last_state: dict = initial_state
    prev_advice: Optional[str] = None
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=_KEEPALIVE_S)
            except asyncio.TimeoutError:
                yield b": ping\n\n"
                continue
            if item is sentinel:
                break

            mode, data = item  # type: ignore[misc]
            if mode == "__error__":
                yield _sse({"event": "error", "message": str(data)})
                return
            if mode == "updates":
                # data is {node_name: update_dict}
                for node_name in data.keys():
                    step = _NODE_STEP.get(node_name)
                    if step is not None:
                        yield _sse({"event": "stage", "node": node_name, "step": step})
            elif mode == "values":
                # data is the full accumulated state after a superstep
                last_state = data
                yield _sse({
                    "event": "partial",
                    "data": _to_response(data, None).model_dump(mode="json"),
                })
                advice = _pick_advice(data, lang)
                if advice and advice != prev_advice:
                    prev_advice = advice
                    for i in range(0, len(advice), _COACH_CHUNK_CHARS):
                        yield _sse({
                            "event": "coach_delta",
                            "text": advice[i:i + _COACH_CHUNK_CHARS],
                        })
                        await asyncio.sleep(_COACH_CHUNK_DELAY)

        # The graph finished; persist to the routine if asked, then send the
        # final, complete ScanResponse (same shape as the /scan endpoint).
        added_product_id = None
        if add_to_routine and user_id:
            try:
                added_product_id = save_scanned_product(user_id, last_state)
            except Exception:  # noqa: BLE001 — don't lose the result over a save failure
                logging.exception("save_scanned_product failed during stream")
        yield _sse({
            "event": "complete",
            "data": _to_response(last_state, added_product_id).model_dump(mode="json"),
        })
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except Exception:  # noqa: BLE001
                pass
