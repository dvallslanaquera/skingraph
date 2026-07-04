# Rejection flywheel (opt-in): persist frames the pipeline bounces so the OOD
# gates can be measured and improved instead of guessed at.
#
# Every retake exit can capture the offending image plus a JSON sidecar with the
# reason and the scores that drove the decision. Hand-label these into
# data/vision_eval_set.json (see eval/vision_eval.py) and the Tier-1/Tier-2
# thresholds stop being magic numbers.
#
# Privacy: OFF by default (config.REJECTION_STORE_ENABLED). User photos can
# contain faces, hands, and homes — persisting them is a deliberate,
# environment-level decision, the store is capped (oldest pruned), and the
# directory is gitignored. See docs/ARCHITECTURE.md "Image data handling".
import json
import logging
import os
import shutil
import time
import uuid

from src import config


def record_rejection(image_path: str, reason: str, details: dict | None = None) -> str | None:
    """Copy a bounced frame + metadata into the rejection store.

    Best-effort: any failure is logged and swallowed — capturing a sample must
    never break the user-facing retake path. Returns the capture id, or None
    when disabled/failed.
    """
    if not config.REJECTION_STORE_ENABLED:
        return None
    try:
        os.makedirs(config.REJECTION_STORE_PATH, exist_ok=True)
        # Fixed-width nanosecond component keeps ids lexicographically ordered
        # by capture time (the prune below drops the oldest *names* first).
        nanos = time.time_ns() % 1_000_000_000
        capture_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{nanos:09d}-{uuid.uuid4().hex[:6]}"
        ext = os.path.splitext(image_path)[1] or ".jpg"
        shutil.copyfile(
            image_path, os.path.join(config.REJECTION_STORE_PATH, f"{capture_id}{ext}")
        )
        sidecar = {
            "id": capture_id,
            "reason": reason,
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            **(details or {}),
        }
        with open(
            os.path.join(config.REJECTION_STORE_PATH, f"{capture_id}.json"),
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(sidecar, f, ensure_ascii=False, indent=2)
        _prune()
        logging.info("Rejection captured: %s (reason: %s)", capture_id, reason)
        return capture_id
    except Exception:  # noqa: BLE001 — never let telemetry break the scan
        logging.exception("Failed to record rejection sample")
        return None


def _prune() -> None:
    """Keep the store bounded: drop the oldest captures beyond the cap."""
    entries = sorted(
        (e for e in os.scandir(config.REJECTION_STORE_PATH) if e.is_file()),
        key=lambda e: e.name,
    )
    # Each capture is an image + a JSON sidecar → 2 files per capture.
    excess = len(entries) - config.REJECTION_STORE_MAX * 2
    for entry in entries[: max(0, excess)]:
        try:
            os.remove(entry.path)
        except OSError:
            pass
