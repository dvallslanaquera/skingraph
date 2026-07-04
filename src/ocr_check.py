# Opt-in OCR cross-check (advisory): a grounded second opinion on the VLM's
# back-label read, produced by a *local* OCR engine (YomiToku) instead of
# another LLM self-report.
#
# Disabled by default (config.OCR_CROSS_CHECK_ENABLED): YomiToku pulls in torch,
# which the deployed API image deliberately excludes. When enabled on a machine
# that has it, each back-label scan also records what fraction of the VLM's
# ingredient names appear in the OCR text — VLM↔OCR agreement is a strong
# hallucination detector that neither model can fake alone.
import logging
from functools import lru_cache
from typing import Any

from rapidfuzz import fuzz

from src.config import OCR_AGREEMENT_FUZZ_THRESHOLD

_ANALYZER: Any = None
_ANALYZER_FAILED = False


def _get_analyzer() -> Any:
    """Lazily construct the YomiToku DocumentAnalyzer; None when unavailable."""
    global _ANALYZER, _ANALYZER_FAILED
    if _ANALYZER is None and not _ANALYZER_FAILED:
        try:
            from yomitoku import DocumentAnalyzer  # noqa: PLC0415 — heavy optional dep

            _ANALYZER = DocumentAnalyzer(visualize=False, device="cpu")
        except Exception:  # noqa: BLE001 — missing/broken optional dep is expected
            logging.warning("OCR cross-check requested but yomitoku is unavailable.")
            _ANALYZER_FAILED = True
    return _ANALYZER


@lru_cache(maxsize=4)
def _ocr_text(image_path: str) -> str | None:
    """Raw OCR text for one image (cached — the pro fallback rescans the same file)."""
    analyzer = _get_analyzer()
    if analyzer is None:
        return None
    try:
        from yomitoku.data.functions import load_image  # noqa: PLC0415

        texts: list[str] = []
        for page in load_image(image_path):
            results, *_ = analyzer(page)
            texts.extend(w.content for w in results.words if w.content)
        return "\n".join(texts)
    except Exception:  # noqa: BLE001 — advisory check must never break a scan
        logging.exception("OCR cross-check failed on %s", image_path)
        return None


def ocr_agreement(image_path: str, names: list[str]) -> float | None:
    """Fraction of extracted ingredient names the OCR pass also saw (0.0-1.0).

    Fuzzy containment (partial_ratio) absorbs the small spelling drift between
    the two readers. Returns None when there is nothing to check or OCR is
    unavailable — callers treat None as "no signal", never as disagreement.
    """
    if not names:
        return None
    text = _ocr_text(image_path)
    if not text:
        return None
    haystack = text.lower()
    seen = sum(
        1
        for n in names
        if fuzz.partial_ratio(n.lower(), haystack) >= OCR_AGREEMENT_FUZZ_THRESHOLD
    )
    return seen / len(names)
