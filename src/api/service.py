# Core scan orchestration, decoupled from HTTP.
#
# ``run_scan`` mirrors the input-assembly and post-scan routine save from
# run_pipeline.py, but returns a typed ScanResponse instead of logging. Keeping
# it here (not in the route handler) lets the graph be driven from tests or a
# worker without a request object.
import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Iterator
from typing import Any

from langchain_core.runnables import RunnableConfig

from src import metrics
from src.api.schemas import FollowupRequest, FollowupResponse, ScanResponse, ScanStatus, ScanUsage
from src.followup import answer_followup
from src.graph import app as graph_app
from src.metrics import ScanUsageCallback
from src.observability import scan_run_config
from src.state import AgentState, build_initial_state
from src.user_store import load_user_context, save_scanned_product


def _status_of(final_state: dict) -> ScanStatus:
    if final_state.get("is_ready_for_logic", False) and final_state.get("coach_cards"):
        return "complete"
    if final_state.get("retake_requested"):
        return "retake_required"
    if final_state.get("notice"):  # confirm_identity / search_failed exits
        return "action_needed"
    return "incomplete"


def _detected_language(final_state: dict) -> str | None:
    """The label language, read straight off the extraction (uppercased)."""
    data = final_state.get("extracted_data")
    lang = (data.source_language or "").strip().upper() if data else ""
    return lang or None


def _to_response(
    final_state: dict, added_product_id: str | None, usage: ScanUsage | None = None
) -> ScanResponse:
    return ScanResponse(
        status=_status_of(final_state),
        trace_id=final_state.get("trace_id"),
        model_used=final_state.get("model_used"),
        inference_confidence=final_state.get("inference_confidence"),
        registry_matched=final_state.get("registry_matched"),
        ingredient_source=final_state.get("ingredient_source"),
        detected_language=_detected_language(final_state),
        product=final_state.get("extracted_data"),
        standardized_ingredients=final_state.get("standardized_ingredients") or [],
        unmatched_ingredients=final_state.get("unmatched_ingredients") or [],
        safety_report=final_state.get("safety_report"),
        routine_fit=final_state.get("routine_fit"),
        coach=final_state.get("coach_cards"),
        notice=final_state.get("notice"),
        web_sources=final_state.get("web_sources") or [],
        usage=usage,
        added_product_id=added_product_id,
    )


def _usage_of(cb: ScanUsageCallback) -> ScanUsage | None:
    """Fold the callback's per-model token counts into one response block."""
    if not cb.usage_metadata:
        return None
    counts = cb.usage_metadata
    return ScanUsage(
        input_tokens=sum(u.get("input_tokens", 0) for u in counts.values()),
        output_tokens=sum(u.get("output_tokens", 0) for u in counts.values()),
        model_calls=cb.model_calls,
        estimated_cost_usd=round(
            sum(
                metrics.estimate_cost_usd(m, u.get("input_tokens", 0), u.get("output_tokens", 0))
                for m, u in counts.items()
            ),
            6,
        ),
    )


def _drive_scan(initial_state: AgentState, config: RunnableConfig) -> Iterator[tuple[str, Any]]:
    """Drive one graph run, yielding ("node", name) and ("state", full_state) events.

    The single instrumented execution path shared by the blocking /scan and the
    SSE /scan/stream: node wall-times are recorded here as the deltas between
    consecutive "updates" frames (the graph runs its nodes sequentially).
    """
    started = time.perf_counter()
    for mode, data in graph_app.stream(initial_state, config, stream_mode=["updates", "values"]):
        if mode == "updates":  # {node_name: update_dict}
            now = time.perf_counter()
            for node_name in data:
                metrics.observe_node(node_name, now - started)
                yield ("node", node_name)
            started = now
        elif mode == "values":  # full accumulated state after a superstep
            yield ("state", data)


def run_scan(
    image_path: str,
    image_type: str | None = None,
    user_id: str | None = None,
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

    initial_state = build_initial_state(
        image_path,
        image_type,
        user_profile=user_profile,
        user_name=user_name,
        routine_products=routine_products,
    )
    usage_cb = ScanUsageCallback()
    config = scan_run_config(
        entrypoint="api",
        image_type=image_type,
        user_id=user_id,
        has_routine=bool(routine_products),
        callbacks=[usage_cb],
    )

    final_state: dict = dict(initial_state)
    for kind, payload in _drive_scan(initial_state, config):
        if kind == "state":
            final_state = payload

    added_product_id = None
    if add_to_routine and user_id:
        added_product_id = save_scanned_product(user_id, final_state)

    response = _to_response(final_state, added_product_id, _usage_of(usage_cb))
    metrics.observe_scan(
        status=response.status,
        entrypoint="api",
        final_state=final_state,
        usage=usage_cb.usage_metadata,
    )
    return response


def run_followup(req: FollowupRequest) -> FollowupResponse:
    """Answer one follow-up question about a completed scan.

    Stateless: the request carries the grounding the client already received
    from /scan. When ``user_id`` is given, the profile and saved routine are
    reloaded so the answer stays personalised. Raises UserNotFoundError.
    """
    profile = user_name = routine_products = None
    if req.user_id:
        profile, user_name, routine_products = load_user_context(req.user_id)

    answer = answer_followup(
        brand=req.brand,
        product_name=req.product_name,
        standardized_ingredients=[i.model_dump() for i in req.standardized_ingredients],
        safety_report=req.safety_report,
        routine_fit=req.routine_fit,
        question=req.question,
        lang=req.lang,
        profile=profile,
        user_name=user_name,
        routine_products=routine_products,
    )
    return FollowupResponse(answer=answer)


# --- streaming scan ----------------------------------------------------------
#
# The single-shot /scan runs the whole LangGraph pipeline in one blocking POST.
# On the deployed stack that request exceeds the platform's connection ceiling
# (the coach is the slowest step), the proxy drops it, and the browser reports a
# generic "backend not running" network error. run_scan_stream() instead drives
# the graph with graph_app.stream(...) and emits Server-Sent Events as each node
# finishes, so bytes flow continuously (no idle proxy timeout) and the UI can
# show real per-stage progress before the final structured response arrives.

# Graph node -> pipeline step (1..5) for the UI's stage indicator. Matches the
# five pipeline.stepN i18n labels (scan / extract / safety / routine / recommend).
_NODE_STEP = {
    "image_quality_gate": 1,
    "classify_side": 1,
    "flash_scanner": 1,
    "early_registry_check": 1,
    "correction": 1,
    "pro_scanner": 1,
    "web_search": 1,
    "confirm_identity": 1,
    "search_failed": 1,
    "retake_request": 1,
    "registry_lookup": 2,
    "normalizer": 2,
    "auditor": 3,
    "routine_advisor": 4,
    "coach": 5,
}

# Emit an SSE keepalive comment if no graph event arrives within this window, so
# a long single-node VLM call can never trip an idle proxy timeout.
_KEEPALIVE_S = 15


def _sse(event: dict) -> bytes:
    """Serialise one SSE ``data:`` frame (UTF-8, JSON payload, no ASCII escaping)."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode()


async def run_scan_stream(
    image_path: str,
    image_type: str | None = None,
    user_id: str | None = None,
    add_to_routine: bool = False,
) -> AsyncIterator[bytes]:
    """Run the pipeline, yielding SSE frames as each node completes.

    Frames (one ``data:`` line each, JSON with an ``event`` field):
      stage    — {node, step}              per node (drives real progress)
      complete — {data: full ScanResponse} final
      error    — {message}                 on any failure
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
    usage_cb = ScanUsageCallback()
    config = scan_run_config(
        entrypoint="api-stream",
        image_type=image_type,
        user_id=user_id,
        has_routine=bool(routine_products),
        callbacks=[usage_cb],
    )

    # The graph stream is synchronous and blocking (VLM calls per node), so
    # _drive_scan runs in a worker thread that pushes its events onto an
    # asyncio.Queue via the loop. The async generator below drains the queue with
    # a timeout so it can emit keepalive pings during long single-node calls.
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    sentinel = object()

    def _run() -> None:
        try:
            for event in _drive_scan(initial_state, config):
                loop.call_soon_threadsafe(queue.put_nowait, event)
        except BaseException as exc:  # noqa: BLE001 — surface it, never end silently
            loop.call_soon_threadsafe(queue.put_nowait, ("__error__", exc))
            return
        loop.call_soon_threadsafe(queue.put_nowait, sentinel)

    task = asyncio.create_task(asyncio.to_thread(_run))
    last_state: dict = dict(initial_state)
    try:
        # Drain per-node events, emitting a `stage` frame for progress. The full
        # accumulated state arrives on "state" events; we keep the latest to
        # build the final response (intermediate states aren't serialised — the
        # UI only needs progress, the coach reveal, and the final result).
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=_KEEPALIVE_S)
            except asyncio.TimeoutError:
                yield b": ping\n\n"
                continue
            if item is sentinel:
                break

            kind, data = item  # type: ignore[misc]
            if kind == "__error__":
                yield _sse({"event": "error", "message": str(data)})
                return
            if kind == "node":
                step = _NODE_STEP.get(data)
                if step is not None:
                    yield _sse({"event": "stage", "node": data, "step": step})
            elif kind == "state":
                last_state = data

        # The graph finished. Persist to the routine if asked, then send the
        # final ScanResponse (same shape as /scan); the UI renders the coach
        # card from it. The coach is the last node, so it lives on `last_state`.
        added_product_id = None
        if add_to_routine and user_id:
            try:
                added_product_id = save_scanned_product(user_id, last_state)
            except Exception:  # noqa: BLE001 — don't lose the result over a save failure
                logging.exception("save_scanned_product failed during stream")
        response = _to_response(last_state, added_product_id, _usage_of(usage_cb))
        metrics.observe_scan(
            status=response.status,
            entrypoint="api-stream",
            final_state=last_state,
            usage=usage_cb.usage_metadata,
        )
        yield _sse({"event": "complete", "data": response.model_dump(mode="json")})
    except Exception as exc:  # noqa: BLE001 — a failure here must not end silently
        logging.exception("scan stream failed")
        yield _sse({"event": "error", "message": str(exc)})
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except BaseException:  # noqa: BLE001, S110 — task is being torn down
                pass
